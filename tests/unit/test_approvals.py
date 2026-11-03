"""Argument-bound, single-use approvals for side-effecting tools (Journey D)."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from schemas.contracts import ConversationRequest, PermissionType, SessionPolicy, ToolCallProposal
from backend.friday.conversation.orchestrator import ConversationOrchestrator
from backend.friday.models.base import ModelResponse
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.base import BaseTool
from backend.friday.tools.registry import ToolRegistry


class FakeMedia(BaseTool):
    """Stands in for control_media so tests never press real media keys."""

    name = "control_media"
    description = "fake"
    required_permission = PermissionType.MEDIA_CONTROL
    parameters_schema = {
        "type": "object",
        "properties": {"action": {"type": "string", "enum": ["play", "pause"]}},
        "required": ["action"],
        "additionalProperties": False,
    }

    def __init__(self, fail: Optional[Exception] = None):
        self.calls = []
        self.fail = fail

    async def execute(self, arguments: Dict[str, Any]) -> Any:
        if self.fail:
            raise self.fail
        self.calls.append(dict(arguments))
        return {"dispatched": True, "action": arguments["action"]}

    async def verify(self, arguments, raw_output) -> Tuple[bool, Optional[str]]:
        return False, "Dispatch only; playback state not observable"


def setup(fail=None):
    tool = FakeMedia(fail)
    registry = ToolRegistry()
    registry.register(tool)
    broker = CapabilityBroker(registry, SessionPolicy(allowed_workspace_root="."))
    return tool, broker


class Scripted:
    model_name = "scripted"

    def __init__(self, responses):
        self.responses = list(responses)

    async def chat(self, messages, tools=None):
        return self.responses.pop(0)

    async def is_available(self):
        return True


def test_denied_side_effect_offers_approval_but_never_runs():
    tool, broker = setup()
    verdict = broker.evaluate(ToolCallProposal(tool_name="control_media", arguments={"action": "pause"}))
    assert verdict.allowed is False and verdict.requires_approval is True
    assert tool.calls == []


@pytest.mark.asyncio
async def test_orchestrator_returns_pending_approval_and_tells_model_nothing_ran():
    tool, broker = setup()
    call = {"function": {"name": "control_media", "arguments": {"action": "pause"}}}
    model = Scripted([ModelResponse(content="", tool_calls=[call, call]), ModelResponse(content="It needs your approval.")])
    res = await ConversationOrchestrator(model, broker.registry, broker).execute_turn(ConversationRequest(message="pause", conversation_id="c1"))
    assert tool.calls == []
    assert len(res.approvals) == 1, "identical repeated proposals share one approval"
    a = res.approvals[0]
    assert a.status == "pending" and a.arguments == {"action": "pause"} and a.conversation_id == "c1"
    assert all(not t.allowed for t in res.tool_calls)


@pytest.mark.asyncio
async def test_approve_runs_exactly_once_and_replay_is_rejected():
    tool, broker = setup()
    a = broker.request_approval(ToolCallProposal(tool_name="control_media", arguments={"action": "play"}), "c1", "needs approval")
    done = await broker.decide(a["approval_id"], approve=True)
    assert done["status"] == "succeeded"
    assert done["result"]["verified"] is False, "dispatch-only tools stay unverified"
    assert tool.calls == [{"action": "play"}]
    with pytest.raises(ValueError):
        await broker.decide(a["approval_id"], approve=True)
    assert len(tool.calls) == 1
    kinds = [(e["kind"], e["outcome"]) for e in broker.audit_events()]
    assert ("approval", "approved") in kinds and ("execution", "dispatched_unverified") in kinds
    assert all("'action'" not in str(e) and e["args_digest"] for e in broker.audit_events() if e["kind"] != "consent"), "only digests, never argument values, are audited"


@pytest.mark.asyncio
async def test_deny_and_expiry_never_execute():
    tool, broker = setup()
    a = broker.request_approval(ToolCallProposal(tool_name="control_media", arguments={"action": "play"}), "c1", "r")
    assert (await broker.decide(a["approval_id"], approve=False))["status"] == "denied"
    b = broker.request_approval(ToolCallProposal(tool_name="control_media", arguments={"action": "pause"}), "c1", "r")
    broker._approvals[b["approval_id"]]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    with pytest.raises(ValueError):
        await broker.decide(b["approval_id"], approve=True)
    assert tool.calls == []


@pytest.mark.asyncio
async def test_tampered_arguments_invalidate_the_approval():
    tool, broker = setup()
    a = broker.request_approval(ToolCallProposal(tool_name="control_media", arguments={"action": "play"}), "c1", "r")
    broker._approvals[a["approval_id"]]["arguments"] = {"action": "pause"}  # material change after approval was shown
    res = await broker.decide(a["approval_id"], approve=True)
    assert res["status"] == "failed" and tool.calls == []


@pytest.mark.asyncio
async def test_timeout_after_dispatch_is_outcome_unknown_not_failed():
    tool, broker = setup(fail=TimeoutError("no ack"))
    a = broker.request_approval(ToolCallProposal(tool_name="control_media", arguments={"action": "play"}), "c1", "r")
    res = await broker.decide(a["approval_id"], approve=True)
    assert res["status"] == "outcome_unknown"


def test_api_decision_endpoints():
    import importlib

    app_module = importlib.import_module("backend.friday.api.app")

    client = TestClient(app_module.app)
    assert client.post("/api/approvals/apr_missing/decision", json={"decision": "approve"}).status_code == 404
    rec = app_module.capability_broker.request_approval(
        ToolCallProposal(tool_name="control_media", arguments={"action": "pause"}), "api-test", "r"
    )
    listed = client.get("/api/approvals", params={"conversation_id": "api-test"}).json()["approvals"]
    assert listed[0]["approval_id"] == rec["approval_id"]
    assert client.post(f"/api/approvals/{rec['approval_id']}/decision", json={"decision": "deny"}).json()["approval"]["status"] == "denied"
    assert client.post(f"/api/approvals/{rec['approval_id']}/decision", json={"decision": "approve"}).status_code == 409
    assert client.post(f"/api/approvals/{rec['approval_id']}/decision", json={"decision": "maybe"}).status_code == 422
