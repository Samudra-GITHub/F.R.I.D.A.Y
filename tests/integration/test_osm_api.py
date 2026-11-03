"""Integration tests for OSM Location Endpoints with Mocked External Responses."""

import pytest
import httpx
from httpx import AsyncClient, ASGITransport

from backend.friday.api.app import app
from backend.friday.config import settings
from backend.friday.location.enrichment import (
    OpenStreetMapLocationEnricher,
    NominatimRateLimiter,
)
import backend.friday.api.location_router as location_router


@pytest.mark.asyncio
async def test_osm_geocode_api_endpoint(monkeypatch):
    """Smoke test /location/geocode returning OSM address details via mocked Nominatim."""
    osm_payload = {
        "place_id": 12345,
        "osm_type": "way",
        "osm_id": 67890,
        "display_name": "Connaught Place, New Delhi, Delhi, 110001, India",
        "address": {
            "road": "Connaught Place",
            "city": "New Delhi",
            "state": "Delhi",
            "country": "India",
            "postcode": "110001",
        },
    }

    def mock_osm_transport(request: httpx.Request):
        return httpx.Response(200, json=osm_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_osm_transport))
    test_enricher = OpenStreetMapLocationEnricher(
        client=mock_client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    monkeypatch.setattr(location_router, "get_location_enricher", lambda: test_enricher)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.get("/location/geocode?lat=28.6315&lng=77.2167")
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "success"
        assert data["provider"] == "OpenStreetMap"
        assert data["osm_uri"] == "https://www.openstreetmap.org/way/67890"
        assert data["attribution"] == "© OpenStreetMap contributors"
        assert data["address"]["locality"] == "New Delhi"
        assert data["address"]["formatted_address"] == "Connaught Place, New Delhi, Delhi, 110001, India"


@pytest.mark.asyncio
async def test_osm_nearby_api_endpoint(monkeypatch):
    """Smoke test /location/nearby returning OSM POIs via mocked Overpass."""
    overpass_payload = {
        "elements": [
            {
                "type": "node",
                "id": 111,
                "lat": 28.6320,
                "lon": 77.2170,
                "tags": {
                    "name": "Barista Cafe CP",
                    "amenity": "cafe",
                    "addr:street": "Radial Road 1",
                },
            },
            {
                "type": "way",
                "id": 222,
                "center": {"lat": 28.6330, "lon": 77.2180},
                "tags": {
                    "name": "Cafe Coffee Day",
                    "amenity": "cafe",
                },
            },
        ]
    }

    def mock_osm_transport(request: httpx.Request):
        return httpx.Response(200, json=overpass_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_osm_transport))
    test_enricher = OpenStreetMapLocationEnricher(
        client=mock_client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    monkeypatch.setattr(location_router, "get_location_enricher", lambda: test_enricher)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        payload = {
            "latitude": 28.6315,
            "longitude": 77.2167,
            "category": "cafe",
            "radius_m": 1000,
            "limit": 5,
        }
        res = await client.post("/location/nearby", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "success"
        assert data["provider"] == "OpenStreetMap"
        assert data["attribution"] == "© OpenStreetMap contributors"
        assert len(data["places"]) == 2
        assert data["places"][0]["name"] == "Barista Cafe CP"
        assert data["places"][0]["osm_uri"] == "https://www.openstreetmap.org/node/111"
        assert data["places"][0]["rating"] is None  # Honest: no fabricated rating
