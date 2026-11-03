"""Unit tests for NASAEonetProvider with mocked HTTP transport."""

import httpx
import pytest

from schemas.contracts import ProviderStatus
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.nasa_eonet import NASAEonetProvider

SAMPLE_EONET_JSON = {
    "title": "EONET Events",
    "description": "Natural events from EONET",
    "link": "https://eonet.gsfc.nasa.gov/api/v3/events",
    "events": [
        {
            "id": "EONET_6432",
            "title": "Wildfire - Sierra National Forest",
            "description": "Active forest fire in Fresno County",
            "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_6432",
            "categories": [{"id": "wildfires", "title": "Wildfires"}],
            "sources": [{"id": "InciWeb", "url": "https://inciweb.wildfire.gov/incident-information/casnf-fire"}],
            "geometry": [
                {
                    "magnitudeValue": None,
                    "magnitudeUnit": None,
                    "date": "2026-10-25T12:00:00Z",
                    "type": "Point",
                    "coordinates": [-119.25, 37.15],
                },
                {
                    # Later observation
                    "magnitudeValue": None,
                    "magnitudeUnit": None,
                    "date": "2026-10-27T14:30:00Z",
                    "type": "Point",
                    "coordinates": [-119.30, 37.20],
                },
            ],
        },
        {
            "id": "EONET_6433",
            "title": "Severe Storm - South Pacific",
            "description": None,
            "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_6433",
            "categories": [{"id": "severeStorms", "title": "Severe Storms"}],
            "sources": [],
            "geometry": [
                {
                    "date": "2026-10-26T00:00:00Z",
                    "type": "Polygon",
                    "coordinates": [[
                        [160.0, -15.0],
                        [162.0, -15.0],
                        [162.0, -17.0],
                        [160.0, -17.0],
                    ]],
                }
            ],
        },
        {
            # Event without usable geometry should be safely omitted without fabricating coordinates
            "id": "EONET_6434",
            "title": "Event without coordinates",
            "categories": [{"id": "floods", "title": "Floods"}],
            "geometry": [],
        },
    ],
}


@pytest.mark.asyncio
async def test_nasa_eonet_parsing_and_multi_geometry():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_EONET_JSON)

    transport = httpx.MockTransport(handler)
    provider = NASAEonetProvider(transport=transport, cache=WorldDataCache())

    res = await provider.get_events()
    assert res.status == ProviderStatus.OK
    # The event with empty geometry was omitted, so 2 valid events
    assert res.count == 2
    assert len(res.events) == 2

    # Check Sierra Wildfire: must use the latest observation coordinates (-119.30, 37.20)
    wf = res.events[0]
    assert wf.id == "EONET_6432"
    assert wf.category == "wildfires"
    assert wf.category_title == "Wildfires"
    assert wf.latitude == 37.20
    assert wf.longitude == -119.30
    assert "2026-10-27" in wf.timestamp_utc
    assert "inciweb" in (wf.source_url or "")

    # Check Severe Storm polygon centroid
    storm = res.events[1]
    assert storm.id == "EONET_6433"
    assert storm.category == "severeStorms"
    assert storm.latitude == -16.0
    assert storm.longitude == 161.0
    assert storm.geometry_type == "Polygon"


@pytest.mark.asyncio
async def test_nasa_eonet_category_filtering():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_EONET_JSON)

    transport = httpx.MockTransport(handler)
    provider = NASAEonetProvider(transport=transport, cache=WorldDataCache())

    # Filter for wildfires only
    wf_res = await provider.get_events(category="wildfires")
    assert wf_res.count == 1
    assert wf_res.events[0].category == "wildfires"

    # Filter for severeStorms
    storm_res = await provider.get_events(category="storms")
    assert storm_res.count == 1
    assert storm_res.events[0].category == "severeStorms"
