"""Regression tests for the 29 Oct 2026 overhaul: broker hardening, memory, dedup, cancel, DSP."""

import array
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.friday.memory import MemoryStore
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.base import BaseTool
from backend.friday.voice import audio_dsp
from backend.friday.conversation.orchestrator import ConversationOrchestrator
from backend.friday.models.base import ModelResponse
from schemas.contracts import ConversationRequest, PermissionType, SessionPolicy, ToolCallProposal


class CountingTool(BaseTool):
    name = "count_it"
    description = "test tool"
    required_permission = PermissionType.SYSTEM_TIME
    parameters_schema = {
        "type": "object",
        "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 5}},
        "required": ["n"],
        "additionalProperties": False,
    }

    def __init__(self):
        self.calls = 0

    async def execute(self, arguments):
        self.calls += 1
        return {"n": arguments["n"], "calls": self.calls}

    async def verify(self, arguments, raw_output):
        return True, "counted"


def make_broker():
    registry = ToolRegistry()
    tool = CountingTool()
    registry.register(tool)
    return registry, tool, CapabilityBroker(registry, SessionPolicy(allowed_workspace_root="."))


def test_broker_rejects_bool_as_integer_and_out_of_range():
    _, _, broker = make_broker()
    assert not broker.evaluate(ToolCallProposal(tool_name="count_it", arguments={"n": True})).allowed
    assert not broker.evaluate(ToolCallProposal(tool_name="count_it", arguments={"n": 9})).allowed
    assert broker.evaluate(ToolCallProposal(tool_name="count_it", arguments={"n": 3})).allowed


def test_broker_audit_is_redacted():
    _, _, broker = make_broker()
    broker.evaluate(ToolCallProposal(tool_name="count_it", arguments={"n": 2}))
    event = broker.audit_events()[0]
    assert event["outcome"] == "allowed" and event["args_digest"]
    assert "2" not in str(event.get("reason")) or "n" not in event  # values are not stored
    assert "arguments" not in event


def test_consent_toggles_permission():
    _, _, broker = make_broker()
    assert broker.consents()["media_control"] is False
    broker.set_consent("media_control", True)
    assert PermissionType.MEDIA_CONTROL in broker.session_policy.allowed_permissions
    broker.set_consent("media_control", False)
    assert PermissionType.MEDIA_CONTROL not in broker.session_policy.allowed_permissions
    with pytest.raises(KeyError):
        broker.set_consent("shell", True)


class ScriptedModel:
    model_name = "scripted"

    def __init__(self, responses):
        self.responses = list(responses)

    async def chat(self, messages, tools=None):
        return self.responses.pop(0)

    async def is_available(self):
        return True


@pytest.mark.asyncio
async def test_duplicate_calls_in_one_turn_run_once():
    registry, tool, broker = make_broker()
    call = {"function": {"name": "count_it", "arguments": {"n": 1}}}
    model = ScriptedModel([
        ModelResponse(content="", tool_calls=[call, call]),
        ModelResponse(content="done", tool_calls=None),
    ])
    orch = ConversationOrchestrator(model, registry, broker)
    res = await orch.execute_turn(ConversationRequest(message="go"))
    assert tool.calls == 1
    assert len(res.tool_calls) == 2
    assert "reused" in (res.tool_calls[1].details or "")


@pytest.mark.asyncio
async def test_cancel_before_dispatch_runs_no_tools():
    registry, tool, broker = make_broker()
    model = ScriptedModel([ModelResponse(content="", tool_calls=[{"function": {"name": "count_it", "arguments": {"n": 1}}}])])
    orch = ConversationOrchestrator(model, registry, broker)
    orch.cancel("req-1")
    res = await orch.execute_turn(ConversationRequest(message="go", request_id="req-1"))
    assert res.status == "cancelled"
    assert tool.calls == 0


def test_memory_store_crud_search_and_tombstone(tmp_path: Path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    rec = store.create("preference", "Prefers concise answers about earthquakes")
    assert rec["source_kind"] == "explicit_user_statement"
    assert store.search("earthquakes")[0]["id"] == rec["id"]
    updated = store.update(rec["id"], content="Prefers detailed answers")
    assert updated["source_kind"] == "user_correction"
    assert store.search("earthquakes") == []
    assert store.delete(rec["id"])
    assert store.list() == []
    tomb = store.get(rec["id"])
    assert tomb["status"] == "deleted" and tomb["content"] == ""
    assert store.search("detailed") == []
    with pytest.raises(ValueError):
        store.create("secret_kind", "x")
    store.close()


def test_memory_context_includes_preferences(tmp_path: Path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    store.create("preference", "Use metric units")
    store.create("project", "FRIDAY uses globe.gl for the Earth view")
    ctx = store.context_for("how does the globe work")
    kinds = {m["kind"] for m in ctx}
    assert kinds == {"preference", "project"}
    store.close()


def _tone(rate, seconds, amp=0.5):
    n = int(rate * seconds)
    return array.array("h", (int(amp * 32767 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(n)))


def test_dsp_resample_wav_roundtrip_and_metrics():
    tone = _tone(48000, 0.5)
    out = audio_dsp.resample(tone, 48000, 16000)
    assert abs(len(out) - 8000) <= 1
    clip = audio_dsp.decode_wav(audio_dsp.encode_wav(out, 16000))
    assert clip.sample_rate == 16000 and clip.source_channels == 1
    m = audio_dsp.measure(clip.samples)
    assert 0.4 < m.peak < 0.55 and m.clipped_ratio == 0


def test_dsp_trim_keeps_speech_and_drops_silence():
    silence = array.array("h", [0] * 16000)
    clip = silence + _tone(16000, 0.5) + silence
    trimmed = audio_dsp.trim_silence(clip, 16000)
    assert 0.5 <= len(trimmed) / 16000 < 1.2


def test_api_rejects_foreign_host_and_serves_memory():
    from backend.friday.api.app import app
    client = TestClient(app)
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
    created = client.post("/api/memories", json={"kind": "preference", "content": "Call me Sam"})
    assert created.status_code == 200
    mem_id = created.json()["memory"]["id"]
    assert any(m["id"] == mem_id for m in client.get("/api/memories").json()["memories"])
    assert client.delete(f"/api/memories/{mem_id}").status_code == 200
    assert client.delete(f"/api/memories/{mem_id}").status_code == 404
    caps = client.get("/api/capabilities").json()
    assert {"tools", "consents"} <= caps.keys()
    assert client.post("/api/policy/consent", json={"consent": "shell", "enabled": True}).status_code == 422
