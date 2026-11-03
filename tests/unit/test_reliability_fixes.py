"""Regression tests: .env loading, model timeout reporting, and Stop aborting the model call."""

import asyncio
import os
import time

import httpx
import pytest

from backend.friday.config import load_dotenv
from backend.friday.conversation.orchestrator import ConversationOrchestrator
from backend.friday.models.base import ModelResponse
from backend.friday.models.ollama_adapter import ModelTimeoutError, OllamaAdapter
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from schemas.contracts import ChatMessage, ChatRole, ConversationRequest, SessionPolicy


def test_dotenv_loads_values_without_overriding_the_real_environment(tmp_path, monkeypatch):
    for k in ("FRI_A", "FRI_B", "FRI_C", "FRI_D", "FRI_E", "FRI_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FRI_B", "from-shell")
    env = tmp_path / ".env"
    env.write_text(
        '# a comment\n\nFRI_A=plain\nFRI_B=from-file\nFRI_C="quoted value"\nexport FRI_D=exported\n'
        "not a setting\nFRI_E=\nFRI_KEY=your_google_maps_api_key_here\n",
        encoding="utf-8",
    )
    load_dotenv(env)
    assert os.environ["FRI_A"] == "plain"
    assert os.environ["FRI_B"] == "from-shell", "a real environment variable wins"
    assert os.environ["FRI_C"] == "quoted value"
    assert os.environ["FRI_D"] == "exported"
    assert "FRI_E" not in os.environ
    assert "FRI_KEY" not in os.environ, "template placeholders must not pass for credentials"


def test_missing_dotenv_is_fine(tmp_path):
    load_dotenv(tmp_path / "absent.env")


@pytest.mark.asyncio
async def test_model_timeout_is_a_timeout_not_an_outage(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "backend.friday.models.ollama_adapter.httpx.AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    adapter = OllamaAdapter(base_url="http://127.0.0.1:11434", model_name="m", timeout=7)
    with pytest.raises(ModelTimeoutError, match="7 s"):
        await adapter.chat([ChatMessage(role=ChatRole.USER, content="hi")])


class HangingModel:
    model_name = "hanging"

    def __init__(self):
        self.started = asyncio.Event()
        self.aborted = False

    async def chat(self, messages, tools=None):
        self.started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.aborted = True
            raise
        return ModelResponse(content="too late")


def orchestrator(model):
    registry = ToolRegistry()
    return ConversationOrchestrator(model, registry, CapabilityBroker(registry, SessionPolicy(allowed_workspace_root=".")))


@pytest.mark.asyncio
async def test_stop_aborts_the_model_call_in_flight():
    model = HangingModel()
    orch = orchestrator(model)
    turn = asyncio.create_task(orch.execute_turn(ConversationRequest(message="hello", request_id="r1", conversation_id="c")))
    await model.started.wait()
    started = time.perf_counter()
    orch.cancel("r1")
    res = await asyncio.wait_for(turn, timeout=5)
    assert res.status == "cancelled"
    assert model.aborted is True
    assert time.perf_counter() - started < 2
    assert orch.get_history("c") == [], "a stopped turn leaves nothing in the history"


@pytest.mark.asyncio
async def test_model_errors_still_propagate_through_the_cancel_wrapper():
    class Broken:
        model_name = "broken"

        async def chat(self, messages, tools=None):
            raise ModelTimeoutError("took too long")

    res = await orchestrator(Broken()).execute_turn(ConversationRequest(message="hello", request_id="r2"))
    assert res.status == "error" and "took too long" in res.error
