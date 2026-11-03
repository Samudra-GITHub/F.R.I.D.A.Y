"""GDACS (Global Disaster Alert and Coordination System) provider.

Fetches and normalizes disaster alerts from GDACS (joint initiative of UN and European Commission).
Supports primary GeoJSON endpoint with fallback to GeoRSS XML parsing.
Never equates GDACS alerts with local government emergency orders; preserves source alert levels.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from schemas.contracts import DisasterRecord, DisastersResponse, ProviderStatus
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache

logger = logging.getLogger(__name__)

# XML Namespaces used in GDACS GeoRSS feed
NAMESPACES = {
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "georss": "http://www.georss.org/georss",
    "gdacs": "http://www.gdacs.org",
}


class GDACSDisasterProvider:
    """Disaster alert provider using official GDACS GeoJSON and GeoRSS feeds."""

    def __init__(
        self,
        cache: Optional[WorldDataCache] = None,
        geojson_url: Optional[str] = None,
        feed_url: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.cache = cache or WorldDataCache()
        self.geojson_url = geojson_url or settings.gdacs_geojson_url
        self.feed_url = feed_url or settings.gdacs_feed_url
        self.cache_ttl = cache_ttl_seconds if cache_ttl_seconds is not None else settings.gdacs_cache_ttl_seconds
        self.timeout = timeout_seconds if timeout_seconds is not None else settings.world_http_timeout_seconds
        self.transport = transport

    def _parse_geojson_feature(self, feature: Dict[str, Any]) -> Optional[DisasterRecord]:
        """Parse a single GeoJSON feature from the GDACS API."""
        try:
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates")
            if not coords or len(coords) < 2:
                return None

            lng = float(coords[0])
            lat = float(coords[1])
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
                return None

            props = feature.get("properties") or {}
            event_id = str(props.get("eventid") or props.get("episodeid") or feature.get("id") or "").strip()
            if not event_id:
                return None

            title = str(props.get("name") or props.get("eventname") or props.get("title") or "Disaster Alert").strip()
            event_type = str(props.get("eventtype") or "Unknown").strip()
            alert_level = str(props.get("alertlevel") or props.get("alertscore") or "Green").capitalize()
            if alert_level not in ("Green", "Orange", "Red"):
                # Normalize if string has formatting
                if "red" in alert_level.lower():
                    alert_level = "Red"
                elif "orange" in alert_level.lower():
                    alert_level = "Orange"
                else:
                    alert_level = "Green"

            country = props.get("country")
            url = props.get("link") or props.get("url")
            date_str = props.get("fromdate") or props.get("todate") or datetime.now(timezone.utc).isoformat()

            severity = None
            sev_data = props.get("severitydata")
            if isinstance(sev_data, dict):
                severity = sev_data.get("severitytext") or str(sev_data.get("severity", ""))
            elif props.get("severity"):
                severity = str(props.get("severity"))

            return DisasterRecord(
                id=f"gdacs_{event_id}",
                title=title,
                event_type=event_type,
                alert_level=alert_level,
                severity=severity,
                latitude=round(lat, 4),
                longitude=round(lng, 4),
                country=str(country) if country else None,
                timestamp_utc=str(date_str),
                url=url,
                details=props.get("description"),
            )
        except Exception as exc:
            logger.debug(f"Skipping malformed GDACS GeoJSON feature: {exc}")
            return None

    def _parse_xml_feed(self, xml_text: str) -> List[DisasterRecord]:
        """Parse GeoRSS XML feed items from GDACS."""
        records: List[DisasterRecord] = []
        try:
            root = ET.fromstring(xml_text)
            channel = root.find("channel")
            if channel is None:
                return records

            for item in channel.findall("item"):
                try:
                    title_elem = item.find("title")
                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Disaster Alert"

                    link_elem = item.find("link")
                    url = link_elem.text.strip() if link_elem is not None and link_elem.text else None

                    pubdate_elem = item.find("pubDate")
                    timestamp = pubdate_elem.text.strip() if pubdate_elem is not None and pubdate_elem.text else datetime.now(timezone.utc).isoformat()

                    # Extract coordinates via georss:point or geo:lat/geo:long
                    lat: Optional[float] = None
                    lng: Optional[float] = None

                    point_elem = item.find("georss:point", NAMESPACES)
                    if point_elem is not None and point_elem.text:
                        parts = point_elem.text.strip().split()
                        if len(parts) >= 2:
                            lat = float(parts[0])
                            lng = float(parts[1])

                    if lat is None or lng is None:
                        lat_elem = item.find("geo:lat", NAMESPACES)
                        lng_elem = item.find("geo:long", NAMESPACES)
                        if lat_elem is not None and lng_elem is not None and lat_elem.text and lng_elem.text:
                            lat = float(lat_elem.text.strip())
                            lng = float(lng_elem.text.strip())

                    if lat is None or lng is None:
                        continue
                    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
                        continue

                    alert_elem = item.find("gdacs:alertlevel", NAMESPACES)
                    alert_level = alert_elem.text.strip().capitalize() if alert_elem is not None and alert_elem.text else "Green"
                    if alert_level not in ("Green", "Orange", "Red"):
                        alert_level = "Green"

                    type_elem = item.find("gdacs:eventtype", NAMESPACES)
                    event_type = type_elem.text.strip() if type_elem is not None and type_elem.text else "General"

                    country_elem = item.find("gdacs:country", NAMESPACES)
                    country = country_elem.text.strip() if country_elem is not None and country_elem.text else None

                    guid_elem = item.find("guid")
                    event_id = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else str(abs(hash(title + str(lat))))

                    desc_elem = item.find("description")
                    desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None

                    records.append(
                        DisasterRecord(
                            id=f"gdacs_rss_{event_id}",
                            title=title,
                            event_type=event_type,
                            alert_level=alert_level,
                            severity=None,
                            latitude=round(lat, 4),
                            longitude=round(lng, 4),
                            country=country,
                            timestamp_utc=timestamp,
                            url=url,
                            details=desc,
                        )
                    )
                except Exception as item_exc:
                    logger.debug(f"Error parsing GDACS XML item: {item_exc}")
                    continue

        except Exception as exc:
            logger.error(f"Failed to parse GDACS XML feed: {exc}")

        return records

    async def get_disasters(
        self,
        alert_level: Optional[str] = None,
        limit: int = 50,
        force_refresh: bool = False,
    ) -> DisastersResponse:
        """Fetch and return active disaster alerts from GDACS."""
        cache_key = "gdacs_disasters_raw"

        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                records, is_stale, retrieved_at = cached
                filtered = self._filter_disasters(records, alert_level, limit)
                return DisastersResponse(
                    status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                    count=len(filtered),
                    disasters=filtered,
                    retrieved_at=retrieved_at,
                    is_stale=is_stale,
                )

        lock = await self.cache.get_lock(cache_key)
        async with lock:
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached:
                    records, is_stale, retrieved_at = cached
                    filtered = self._filter_disasters(records, alert_level, limit)
                    return DisastersResponse(
                        status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                        count=len(filtered),
                        disasters=filtered,
                        retrieved_at=retrieved_at,
                        is_stale=is_stale,
                    )

            records: List[DisasterRecord] = []
            retrieved_at: Optional[str] = None
            headers = {"User-Agent": settings.osm_user_agent, "Accept": "application/json, application/xml, text/xml"}

            # 1. Try primary GeoJSON endpoint
            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                    resp = await client.get(self.geojson_url, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    features = data.get("features", [])
                    seen_ids = set()
                    for f in features:
                        rec = self._parse_geojson_feature(f)
                        if rec and rec.id not in seen_ids:
                            seen_ids.add(rec.id)
                            records.append(rec)

            except Exception as geojson_exc:
                logger.warning(f"GDACS GeoJSON endpoint failed: {geojson_exc}; attempting GeoRSS XML fallback")

            # 2. If GeoJSON yielded no records or failed, try GeoRSS XML fallback
            if not records:
                try:
                    async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                        xml_resp = await client.get(self.feed_url, headers=headers)

                    if xml_resp.status_code == 200:
                        records = self._parse_xml_feed(xml_resp.text)
                except Exception as xml_exc:
                    logger.error(f"GDACS GeoRSS XML fallback also failed: {xml_exc}")

            if records:
                retrieved_at = self.cache.set(cache_key, records, self.cache_ttl)
                filtered = self._filter_disasters(records, alert_level, limit)
                return DisastersResponse(
                    status=ProviderStatus.OK if filtered else ProviderStatus.EMPTY,
                    count=len(filtered),
                    disasters=filtered,
                    retrieved_at=retrieved_at,
                    is_stale=False,
                )

            return self._fallback_or_error(cache_key, ProviderStatus.PROVIDER_ERROR, "Unable to reach GDACS endpoints", alert_level, limit)

    def _filter_disasters(
        self,
        records: List[DisasterRecord],
        alert_level: Optional[str],
        limit: int,
    ) -> List[DisasterRecord]:
        """Filter records by alert level and limit."""
        if not alert_level:
            return records[:limit]
        level_clean = alert_level.strip().capitalize()
        return [r for r in records if r.alert_level == level_clean][:limit]

    def _fallback_or_error(
        self,
        cache_key: str,
        status: ProviderStatus,
        details: str,
        alert_level: Optional[str],
        limit: int,
    ) -> DisastersResponse:
        """Serve last successful snapshot if available, or error payload."""
        snapshot = self.cache.get_last_successful(cache_key)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if snapshot:
            records, retrieved_at = snapshot
            filtered = self._filter_disasters(records, alert_level, limit)
            return DisastersResponse(
                status=ProviderStatus.STALE,
                count=len(filtered),
                disasters=filtered,
                retrieved_at=retrieved_at,
                is_stale=True,
                details=f"Serving cached snapshot: {details}",
            )

        return DisastersResponse(
            status=status,
            count=0,
            disasters=[],
            retrieved_at=now_iso,
            is_stale=False,
            details=details,
        )
