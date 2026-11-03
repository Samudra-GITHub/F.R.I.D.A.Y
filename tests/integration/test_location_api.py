"""Integration tests for Location REST API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.friday.api.app import app


@pytest.mark.asyncio
async def test_location_status_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Check direct path
        res = await client.get("/location/status")
        assert res.status_code == 200
        data = res.json()
        assert "tracking_enabled" in data
        assert "is_paused" in data

        # Check proxied /api path
        res_api = await client.get("/api/location/status")
        assert res_api.status_code == 200
        assert res_api.json()["tracking_enabled"] == data["tracking_enabled"]


@pytest.mark.asyncio
async def test_location_pause_resume_disable_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # Pause
        pause_res = await client.post("/location/pause")
        assert pause_res.status_code == 200
        assert pause_res.json()["is_paused"] is True

        # Resume
        resume_res = await client.post("/location/resume")
        assert resume_res.status_code == 200
        assert resume_res.json()["is_paused"] is False

        # Disable
        disable_res = await client.post("/location/disable")
        assert disable_res.status_code == 200
        assert disable_res.json()["tracking_enabled"] is False
        assert disable_res.json()["worker_running"] is False
