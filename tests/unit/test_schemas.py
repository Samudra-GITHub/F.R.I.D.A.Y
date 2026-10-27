"""Unit tests for typed Pydantic contracts."""

import pytest
from pydantic import ValidationError
from schemas.contracts import (
    ChatMessage,
    ChatRole,
    PermissionType,
    PolicyDecision,
    SessionPolicy,
    ToolCallProposal,
    ToolExecutionResult,
)


def test_tool_call_proposal_valid():
    proposal = ToolCallProposal(tool_name="get_local_time", arguments={})
    assert proposal.tool_name == "get_local_time"
    assert proposal.arguments == {}


def test_tool_call_proposal_missing_name():
    with pytest.raises(ValidationError):
        ToolCallProposal()  # type: ignore


def test_policy_decision():
    verdict = PolicyDecision(allowed=False, reason="Tool rejected")
    assert not verdict.allowed
    assert verdict.reason == "Tool rejected"
    assert not verdict.requires_approval


def test_tool_execution_result_defaults():
    res = ToolExecutionResult(tool_name="list_workspace", ok=True, output={"entries": []})
    assert res.tool_name == "list_workspace"
    assert res.ok is True
    assert res.is_untrusted_content is True
    assert res.verified is False
    assert res.verification_details is None


def test_session_policy_defaults():
    policy = SessionPolicy(allowed_workspace_root="C:\\workspace")
    assert PermissionType.SYSTEM_TIME in policy.allowed_permissions
    assert PermissionType.WORKSPACE_READ in policy.allowed_permissions
    assert PermissionType.MEDIA_CONTROL not in policy.allowed_permissions
    assert policy.media_control_enabled is False


def test_chat_message():
    msg = ChatMessage(role=ChatRole.USER, content="Hello Friday")
    assert msg.role == ChatRole.USER
    assert msg.content == "Hello Friday"
