"""Unit tests for GDACSDisasterProvider with GeoJSON and GeoRSS XML mocks."""

import httpx
import pytest

from schemas.contracts import ProviderStatus
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.gdacs_disasters import GDACSDisasterProvider

SAMPLE_GDACS_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": 10001,
            "properties": {
                "eventid": "10001",
                "eventtype": "TC",
                "name": "Tropical Cyclone BEJISA-14",
                "alertlevel": "Red",
                "country": "Madagascar",
                "link": "https://www.gdacs.org/report.aspx?eventtype=TC&eventid=10001",
                "fromdate": "2026-10-27T06:00:00Z",
                "severitydata": {"severitytext": "Category 4 Cyclone"},
            },
            "geometry": {
                "type": "Point",
                "coordinates": [48.5, -18.2],
            },
        },
        {
            "type": "Feature",
            "id": 10002,
            "properties": {
                "eventid": "10002",
                "eventtype": "FL",
                "name": "Flood in Central Valley",
                "alertlevel": "Orange",
                "country": "Vietnam",
                "link": "https://www.gdacs.org/report.aspx?eventtype=FL&eventid=10002",
                "fromdate": "2026-10-26T12:00:00Z",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [105.8, 21.0],
            },
        },
    ],
}

SAMPLE_GDACS_GEORSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:georss="http://www.georss.org/georss" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#" xmlns:gdacs="http://www.gdacs.org">
  <channel>
    <title>GDACS Alerts</title>
    <item>
      <title>Green Alert for Earthquake M 5.2 in Japan</title>
      <link>https://www.gdacs.org/report.aspx?eventtype=EQ&amp;eventid=20001</link>
      <pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate>
      <georss:point>36.5 139.8</georss:point>
      <gdacs:alertlevel>Green</gdacs:alertlevel>
      <gdacs:eventtype>EQ</gdacs:eventtype>
      <gdacs:country>Japan</gdacs:country>
      <guid>20001</guid>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_gdacs_primary_geojson_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_GDACS_GEOJSON)

    transport = httpx.MockTransport(handler)
    provider = GDACSDisasterProvider(transport=transport, cache=WorldDataCache())

    res = await provider.get_disasters()
    assert res.status == ProviderStatus.OK
    assert res.count == 2
    assert res.is_stale is False

    tc = res.disasters[0]
    assert tc.event_type == "TC"
    assert tc.alert_level == "Red"
    assert tc.country == "Madagascar"
    assert tc.latitude == -18.2
    assert tc.longitude == 48.5
    assert tc.severity == "Category 4 Cyclone"
    assert "https://www.gdacs.org" in (tc.url or "")


@pytest.mark.asyncio
async def test_gdacs_xml_fallback():
    # Primary GeoJSON returns 500, secondary RSS XML returns 200
    def handler(request: httpx.Request) -> httpx.Response:
        if "geteventlist" in str(request.url):
            return httpx.Response(500, text="GeoJSON API down")
        return httpx.Response(200, text=SAMPLE_GDACS_GEORSS_XML)

    transport = httpx.MockTransport(handler)
    provider = GDACSDisasterProvider(transport=transport, cache=WorldDataCache())

    res = await provider.get_disasters()
    assert res.status == ProviderStatus.OK
    assert res.count == 1
    quake = res.disasters[0]
    assert quake.event_type == "EQ"
    assert quake.alert_level == "Green"
    assert quake.country == "Japan"
    assert quake.latitude == 36.5
    assert quake.longitude == 139.8


@pytest.mark.asyncio
async def test_gdacs_alert_level_filter():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_GDACS_GEOJSON)

    transport = httpx.MockTransport(handler)
    provider = GDACSDisasterProvider(transport=transport, cache=WorldDataCache())

    # Filter Red alerts only
    red_res = await provider.get_disasters(alert_level="Red")
    assert red_res.count == 1
    assert red_res.disasters[0].alert_level == "Red"
    assert red_res.disasters[0].event_type == "TC"
