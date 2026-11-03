"""Integration tests for World Intelligence REST API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.friday.api.app import app
from backend.friday.api.world_router import world_service


@pytest.mark.asyncio
async def test_world_status_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Direct path
        res = await client.get("/world/status")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "providers" in data
        assert "usgs_earthquakes" in data["providers"]
        assert "open_meteo" in data["providers"]
        assert "nasa_eonet" in data["providers"]
        assert "gdacs_disasters" in data["providers"]

        # Proxied /api path
        res_api = await client.get("/api/world/status")
        assert res_api.status_code == 200
        assert res_api.json()["status"] == data["status"]


@pytest.mark.asyncio
async def test_world_earthquakes_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.get("/world/earthquakes?min_magnitude=3.0&limit=5")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "earthquakes" in data
        assert data["provider"] == "USGS"


@pytest.mark.asyncio
async def test_world_weather_endpoint_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Missing coordinates
        res_missing = await client.get("/world/weather")
        assert res_missing.status_code == 400

        # Out-of-bounds coordinates
        res_bad = await client.get("/world/weather?lat=999.0&lng=0.0")
        assert res_bad.status_code == 400


@pytest.mark.asyncio
async def test_world_events_and_disasters_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # EONET events
        res_events = await client.get("/world/events?days=14&limit=5")
        assert res_events.status_code == 200
        assert "events" in res_events.json()

        # GDACS disasters
        res_disasters = await client.get("/world/disasters?limit=5")
        assert res_disasters.status_code == 200
        assert "disasters" in res_disasters.json()

        # News
        res_news = await client.get("/world/news?limit=5")
        assert res_news.status_code == 200
        assert "articles" in res_news.json()
