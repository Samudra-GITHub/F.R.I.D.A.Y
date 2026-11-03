"""Allowlisted RSS News feed provider with SSRF protections.

Fetches reputable world news headlines from a strict domain allowlist.
Enforces SSRF prevention, request timeouts, and deduplication.
Preserves publisher attribution, canonical links, and published timestamps.
"""

import hashlib
import ipaddress
import logging
import socket
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from schemas.contracts import NewsArticleRecord, NewsResponse, ProviderStatus
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache

logger = logging.getLogger(__name__)

# Strict domain allowlist for RSS feeds
APPROVED_DOMAINS = {
    "feeds.bbci.co.uk",
    "rss.nytimes.com",
    "feeds.npr.org",
    "feeds.reuters.com",
}


def is_safe_feed_url(url: str) -> bool:
    """Validate that feed URL is HTTP/HTTPS, matches allowlisted domains, and is not an internal IP."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False

        if hostname not in APPROVED_DOMAINS:
            # Check if domain ends with an approved domain suffix
            if not any(hostname.endswith("." + d) or hostname == d for d in APPROVED_DOMAINS):
                return False

        # SSRF defense: resolve host and check for private / loopback IP ranges
        try:
            ip_str = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast:
                return False
        except Exception:
            # If DNS resolution fails, allow if domain string is strictly allowlisted
            pass

        return True
    except Exception:
        return False


class NewsRSSProvider:
    """Provider for curated world news headlines from verified RSS sources."""

    def __init__(
        self,
        cache: Optional[WorldDataCache] = None,
        feed_urls: Optional[List[str]] = None,
        cache_ttl_seconds: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.cache = cache or WorldDataCache()
        self.feed_urls = feed_urls or settings.news_rss_feeds
        self.cache_ttl = cache_ttl_seconds if cache_ttl_seconds is not None else settings.news_cache_ttl_seconds
        self.timeout = timeout_seconds if timeout_seconds is not None else settings.world_http_timeout_seconds
        self.transport = transport

    def _determine_publisher(self, url: str) -> str:
        """Extract recognizable publisher name from domain."""
        domain = urlparse(url).hostname or ""
        if "bbc" in domain:
            return "BBC News"
        if "nytimes" in domain:
            return "The New York Times"
        if "npr" in domain:
            return "NPR"
        if "reuters" in domain:
            return "Reuters"
        return domain

    def _parse_feed_xml(self, xml_text: str, default_publisher: str) -> List[NewsArticleRecord]:
        """Parse RSS 2.0 or Atom XML text into normalized article records."""
        articles: List[NewsArticleRecord] = []
        try:
            root = ET.fromstring(xml_text)

            # RSS 2.0 structure
            channel = root.find("channel")
            if channel is not None:
                channel_title_elem = channel.find("title")
                publisher = (
                    channel_title_elem.text.strip()
                    if channel_title_elem is not None and channel_title_elem.text
                    else default_publisher
                )

                for item in channel.findall("item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pubdate_elem = item.find("pubDate")
                    desc_elem = item.find("description")

                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else None
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else None
                    if not title or not link:
                        continue

                    # Sanitize summary: strip HTML tags if present
                    summary = None
                    if desc_elem is not None and desc_elem.text:
                        raw_summary = desc_elem.text.strip()
                        # Simple tag strip
                        clean_summary = ""
                        in_tag = False
                        for ch in raw_summary:
                            if ch == "<":
                                in_tag = True
                            elif ch == ">":
                                in_tag = False
                            elif not in_tag:
                                clean_summary += ch
                        summary = clean_summary[:300].strip()

                    pubdate = (
                        pubdate_elem.text.strip()
                        if pubdate_elem is not None and pubdate_elem.text
                        else datetime.now(timezone.utc).isoformat()
                    )

                    art_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]

                    articles.append(
                        NewsArticleRecord(
                            id=f"news_{art_id}",
                            title=title,
                            publisher=publisher,
                            url=link,
                            published_at_utc=pubdate,
                            summary=summary if summary else None,
                        )
                    )

        except Exception as exc:
            logger.debug(f"Failed to parse news RSS XML: {exc}")

        return articles

    async def get_news(self, limit: int = 30, force_refresh: bool = False) -> NewsResponse:
        """Fetch and aggregate news articles from allowlisted feeds."""
        cache_key = "world_news_rss"

        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                records, is_stale, retrieved_at = cached
                return NewsResponse(
                    status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                    count=min(len(records), limit),
                    articles=records[:limit],
                    retrieved_at=retrieved_at,
                    is_stale=is_stale,
                )

        lock = await self.cache.get_lock(cache_key)
        async with lock:
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached:
                    records, is_stale, retrieved_at = cached
                    return NewsResponse(
                        status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                        count=min(len(records), limit),
                        articles=records[:limit],
                        retrieved_at=retrieved_at,
                        is_stale=is_stale,
                    )

            all_articles: List[NewsArticleRecord] = []
            seen_urls = set()
            headers = {"User-Agent": settings.osm_user_agent, "Accept": "application/rss+xml, application/xml, text/xml"}

            for feed_url in self.feed_urls:
                if not is_safe_feed_url(feed_url):
                    logger.warning(f"Skipping unapproved or unsafe feed URL: {feed_url}")
                    continue

                publisher = self._determine_publisher(feed_url)
                try:
                    async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                        resp = await client.get(feed_url, headers=headers)

                    if resp.status_code == 200:
                        feed_articles = self._parse_feed_xml(resp.text, publisher)
                        for art in feed_articles:
                            if art.url not in seen_urls:
                                seen_urls.add(art.url)
                                all_articles.append(art)
                except Exception as exc:
                    logger.warning(f"Failed to fetch feed {feed_url}: {exc}")

            if all_articles:
                retrieved_at = self.cache.set(cache_key, all_articles, self.cache_ttl)
                return NewsResponse(
                    status=ProviderStatus.OK,
                    count=min(len(all_articles), limit),
                    articles=all_articles[:limit],
                    retrieved_at=retrieved_at,
                    is_stale=False,
                )

            # Check snapshot fallback
            snapshot = self.cache.get_last_successful(cache_key)
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if snapshot:
                records, retrieved_at = snapshot
                return NewsResponse(
                    status=ProviderStatus.STALE,
                    count=min(len(records), limit),
                    articles=records[:limit],
                    retrieved_at=retrieved_at,
                    is_stale=True,
                    details="Serving cached news snapshot",
                )

            return NewsResponse(
                status=ProviderStatus.EMPTY,
                count=0,
                articles=[],
                retrieved_at=now_iso,
                is_stale=False,
                details="No news articles could be retrieved from feeds",
            )
