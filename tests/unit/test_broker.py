"""Unit tests for the Capability Broker."""

import pytest
from pathlib import Path
from schemas.contracts import PermissionType, SessionPolicy, ToolCallProposal
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.time_tool import GetLocalTimeTool
from backend.friday.tools.workspace_tool import ListWorkspaceTool
from backend.friday.tools.media_tool import ControlMediaTool


@pytest.fixture
def test_setup(temp_workspace: Path):
    registry = ToolRegistry()
    registry.register(GetLocalTimeTool())
    registry.register(ListWorkspaceTool(workspace_root=temp_workspace))
    registry.register(ControlMediaTool())

    policy = SessionPolicy(
        allowed_permissions={PermissionType.SYSTEM_TIME, PermissionType.WORKSPACE_READ},
        media_control_enabled=False,
        allowed_workspace_root=str(temp_workspace),
    )
    broker = CapabilityBroker(registry=registry, session_policy=policy)
    return broker, registry, policy


def test_reject_unknown_tool(test_setup):
    broker, _, _ = test_setup
    proposal = ToolCallProposal(tool_name="execute_powershell", arguments={"command": "dir"})
    verdict = broker.evaluate(proposal)
    assert verdict.allowed is False
    assert "does not exist in the fixed registry" in verdict.reason


def test_reject_invalid_arguments_schema(test_setup):
    broker, _, _ = test_setup
    # control_media requires 'action', provide wrong property
    proposal = ToolCallProposal(tool_name="control_media", arguments={"bogus": "value"})
    verdict = broker.evaluate(proposal)
    assert verdict.allowed is False
    assert "failed schema validation" in verdict.reason


def test_reject_invalid_enum_argument(test_setup):
    broker, _, _ = test_setup
    proposal = ToolCallProposal(tool_name="control_media", arguments={"action": "explode"})
    verdict = broker.evaluate(proposal)
    assert verdict.allowed is False
    assert "not in allowed enum" in verdict.reason


def test_reject_unauthorized_permission(test_setup):
    broker, _, _ = test_setup
    # control_media requires MEDIA_CONTROL which is not granted in test_setup
    proposal = ToolCallProposal(tool_name="control_media", arguments={"action": "pause"})
    verdict = broker.evaluate(proposal)
    assert verdict.allowed is False
    assert "lacks required permission" in verdict.reason or "Media control is disabled" in verdict.reason


def test_allow_valid_request(test_setup):
    broker, _, _ = test_setup
    proposal = ToolCallProposal(tool_name="get_local_time", arguments={})
    verdict = broker.evaluate(proposal)
    assert verdict.allowed is True
    assert "Authorized by Capability Broker" in verdict.reason
