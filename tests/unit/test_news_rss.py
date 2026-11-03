"""Unit tests for NewsRSSProvider with SSRF defense and deduplication."""

import httpx
import pytest

from schemas.contracts import ProviderStatus
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.news_rss import NewsRSSProvider, is_safe_feed_url

SAMPLE_BBC_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>BBC News - World</title>
    <link>https://www.bbc.co.uk/news/world</link>
    <item>
      <title>Global Climate Summit Concludes in Geneva</title>
      <description>&lt;p&gt;World leaders have signed an international framework on climate standards.&lt;/p&gt;</description>
      <link>https://www.bbc.co.uk/news/world-12345678</link>
      <pubDate>Tue, 27 Oct 2026 14:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Autonomous Maritime Drone Completes Pacific Crossing</title>
      <description>Solar-powered research vessel arrives in Honolulu after 4,000 nautical miles.</description>
      <link>https://www.bbc.co.uk/news/technology-87654321</link>
      <pubDate>Tue, 27 Oct 2026 12:30:00 GMT</pubDate>
    </item>
    <item>
      # Duplicate link should be deduplicated
      <title>Global Climate Summit Framework Signed</title>
      <description>Duplicate article test</description>
      <link>https://www.bbc.co.uk/news/world-12345678</link>
      <pubDate>Tue, 27 Oct 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_ssrf_allowlist_defense():
    # Allowed domains
    assert is_safe_feed_url("https://feeds.bbci.co.uk/news/world/rss.xml") is True
    assert is_safe_feed_url("https://rss.nytimes.com/services/xml/rss/nyt/World.xml") is True

    # Blocked domains
    assert is_safe_feed_url("https://evil-hacker.com/feed.xml") is False
    assert is_safe_feed_url("http://localhost:8000/feed.xml") is False
    assert is_safe_feed_url("http://127.0.0.1:8000/internal") is False
    assert is_safe_feed_url("http://169.254.169.254/latest/meta-data") is False
    assert is_safe_feed_url("file:///etc/passwd") is False


@pytest.mark.asyncio
async def test_news_parsing_and_deduplication():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SAMPLE_BBC_RSS)

    transport = httpx.MockTransport(handler)
    provider = NewsRSSProvider(
        feed_urls=["https://feeds.bbci.co.uk/news/world/rss.xml"],
        transport=transport,
        cache=WorldDataCache(),
    )

    res = await provider.get_news()
    assert res.status == ProviderStatus.OK
    # 3 items in feed, but 1 is a duplicate link, so count should be 2
    assert res.count == 2
    assert len(res.articles) == 2

    art1 = res.articles[0]
    assert art1.title == "Global Climate Summit Concludes in Geneva"
    assert art1.publisher == "BBC News - World"
    assert "<p>" not in (art1.summary or "")  # HTML stripped
    assert "Geneva" in art1.title
    assert "climate" in (art1.summary or "").lower()
    assert art1.url == "https://www.bbc.co.uk/news/world-12345678"
