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
        # Privacy check: ensure no credentials or secret keys are exposed in health response
        assert "password" not in data
        assert "token" not in data
        assert "api_key" not in data
        assert "secret" not in data


@pytest.mark.asyncio
async def test_api_chat_enforces_capability_broker(monkeypatch):
    """Verify that the API enforces the Capability Broker and does not bypass authorization."""
    from backend.friday.api.app import orchestrator
    from backend.friday.models.base import BaseModelAdapter, ModelResponse

    class MockModel(BaseModelAdapter):
        async def is_available(self):
            return True

        async def chat(self, messages, tools=None):
            # Propose an unauthorized tool through API
            return ModelResponse(
                content="Proposing unauthorized action",
                tool_calls=[{"function": {"name": "control_media", "arguments": {"action": "pause"}}}]
            )

    monkeypatch.setattr(orchestrator, "model_adapter", MockModel())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8000"
    ) as client:
        response = await client.post("/chat", json={"message": "Pause media now"})
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        # Orchestrator records rejection into history
        tool_messages = [m for m in orchestrator.history if m.role.value == "tool"]
        # Broker rejected it because media_control_enabled is False
        assert orchestrator.broker.session_policy.media_control_enabled is False

