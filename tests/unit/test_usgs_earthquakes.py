"""Unit tests for USGSEarthquakeProvider with mocked HTTP transport."""

import json
import httpx
import pytest

from schemas.contracts import ProviderStatus
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.usgs_earthquakes import USGSEarthquakeProvider

SAMPLE_USGS_GEOJSON = {
    "type": "FeatureCollection",
    "metadata": {
        "generated": 1714567890000,
        "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
        "title": "USGS Earthquakes",
        "status": 200,
        "count": 2,
    },
    "features": [
        {
            "type": "Feature",
            "properties": {
                "mag": 5.4,
                "place": "12 km SSW of Volcano, Hawaii",
                "time": 1714560000000,
                "updated": 1714561000000,
                "url": "https://earthquake.usgs.gov/earthquakes/event/hv12345",
                "tsunami": 1,
                "felt": 128,
                "alert": "green",
                "title": "M 5.4 - 12 km SSW of Volcano, Hawaii",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-155.234, 19.382, 8.5],
            },
            "id": "hv12345",
        },
        {
            "type": "Feature",
            "properties": {
                "mag": 2.1,
                "place": "Central Alaska",
                "time": 1714550000000,
                "updated": 1714551000000,
                "url": "https://earthquake.usgs.gov/earthquakes/event/ak67890",
                "tsunami": 0,
                "felt": None,
                "alert": None,
                "title": "M 2.1 - Central Alaska",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-149.500, 64.200, 15.0],
            },
            "id": "ak67890",
        },
        {
            # Malformed feature: invalid coordinates
            "type": "Feature",
            "properties": {"mag": 3.0, "place": "Invalid land"},
            "geometry": {"type": "Point", "coordinates": [999.0, -999.0, 0.0]},
            "id": "invalid_1",
        },
        {
            # Malformed feature: missing magnitude
            "type": "Feature",
            "properties": {"mag": None, "place": "No mag"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 0.0]},
            "id": "invalid_2",
        },
    ],
}


@pytest.mark.asyncio
async def test_usgs_earthquakes_parsing_and_filtering():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_USGS_GEOJSON)

    transport = httpx.MockTransport(handler)
    provider = USGSEarthquakeProvider(transport=transport, cache=WorldDataCache())

    # 1. Fetch all earthquakes
    res = await provider.get_earthquakes(min_magnitude=0.0)
    assert res.status == ProviderStatus.OK
    assert res.count == 2
    assert res.is_stale is False
    assert len(res.earthquakes) == 2

    # Check Hawaiian earthquake
    eq1 = res.earthquakes[0]
    assert eq1.id == "hv12345"
    assert eq1.magnitude == 5.4
    assert eq1.latitude == 19.382
    assert eq1.longitude == -155.234
    assert eq1.depth_km == 8.5
    assert eq1.tsunami_alert is True
    assert eq1.felt_reports == 128
    assert eq1.alert_level == "green"
    assert "https://earthquake.usgs.gov" in (eq1.url or "")

    # 2. Filter by minimum magnitude 4.0
    res_filtered = await provider.get_earthquakes(min_magnitude=4.0)
    assert res_filtered.count == 1
    assert res_filtered.earthquakes[0].id == "hv12345"


@pytest.mark.asyncio
async def test_usgs_earthquakes_stale_fallback_on_500():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=SAMPLE_USGS_GEOJSON)
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    cache = WorldDataCache()
    provider = USGSEarthquakeProvider(transport=transport, cache=cache)

    # Initial success populates snapshot
    res1 = await provider.get_earthquakes()
    assert res1.status == ProviderStatus.OK
    assert res1.count == 2

    # Subsequent error falls back to stale snapshot
    res2 = await provider.get_earthquakes(force_refresh=True)
    assert res2.status == ProviderStatus.STALE
    assert res2.is_stale is True
    assert res2.count == 2
    assert "cached snapshot" in (res2.details or "")


@pytest.mark.asyncio
async def test_usgs_earthquakes_timeout_and_empty():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    transport = httpx.MockTransport(timeout_handler)
    provider = USGSEarthquakeProvider(transport=transport, cache=WorldDataCache())

    res = await provider.get_earthquakes()
    assert res.status == ProviderStatus.TIMEOUT
    assert res.count == 0
    assert res.is_stale is False
