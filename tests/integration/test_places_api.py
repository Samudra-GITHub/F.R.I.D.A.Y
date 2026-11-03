"""Integration tests for Places and Geocoding REST API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.friday.api.app import app


@pytest.mark.asyncio
async def test_geocode_endpoint_unconfigured_default():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Direct path with lat/lng
        res = await client.get("/location/geocode?lat=28.6139&lng=77.2090")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "provider_not_configured"
        assert data["address"] is None
        assert data["latitude"] == pytest.approx(28.6139, rel=1e-3)
        assert data["longitude"] == pytest.approx(77.2090, rel=1e-3)

        # Proxied /api path with latitude/longitude alias
        res_api = await client.get("/api/location/geocode?latitude=28.6139&longitude=77.2090")
        assert res_api.status_code == 200
        assert res_api.json()["status"] == "provider_not_configured"


@pytest.mark.asyncio
async def test_geocode_endpoint_invalid_coordinates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.get("/location/geocode?lat=95.0&lng=77.0")
        assert res.status_code == 400
        assert "Latitude" in res.json()["detail"]


@pytest.mark.asyncio
async def test_nearby_endpoint_unconfigured_default():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        payload = {
            "latitude": 28.6139,
            "longitude": 77.2090,
            "category": "pharmacy",
            "radius_m": 1500,
            "limit": 5,
        }
        res = await client.post("/location/nearby", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "provider_not_configured"
        assert data["places"] == []
        assert "Google Maps API key is not configured" in (data["details"] or "")

        # Proxied path
        res_api = await client.post("/api/location/nearby", json=payload)
        assert res_api.status_code == 200
        assert res_api.json()["status"] == "provider_not_configured"


@pytest.mark.asyncio
async def test_nearby_endpoint_invalid_coordinates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        payload = {"latitude": 28.0, "longitude": 200.0}
        res = await client.post("/location/nearby", json=payload)
        assert res.status_code == 400
        assert "Longitude" in res.json()["detail"]
