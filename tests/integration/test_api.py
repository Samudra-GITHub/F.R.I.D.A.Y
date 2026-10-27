"""Integration tests for FastAPI backend endpoints."""

import pytest
import httpx
from backend.friday.api.app import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify that /health responds with valid data contracts and localhost status."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8000"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "model" in data
        assert "workspace_root" in data
        assert "media_control_enabled" in data
        assert isinstance(data["ollama_reachable"], bool)
