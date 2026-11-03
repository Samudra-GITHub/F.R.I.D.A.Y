"""Unit tests for Capability Broker policy enforcement on location tools."""

import pytest
from pathlib import Path

from schemas.contracts import (
    PermissionType,
    SessionPolicy,
    ToolCallProposal,
)
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.location_tool import GetDeviceLocationTool
from backend.friday.location.service import LocationService
from backend.friday.location.mock_provider import MockLocationProvider
from backend.friday.location.state import LocationStateManager


@pytest.fixture
def broker_setup(tmp_path: Path):
    registry = ToolRegistry()
    mock_prov = MockLocationProvider()
    state_mgr = LocationStateManager(
        state_file=tmp_path / "loc_state.json",
        lock_file=tmp_path / "loc.lock",
    )
    loc_service = LocationService(provider=mock_prov, state_manager=state_mgr)
    loc_tool = GetDeviceLocationTool(location_service=loc_service)
    registry.register(loc_tool)

    policy = SessionPolicy(
        allowed_permissions={PermissionType.SYSTEM_TIME, PermissionType.WORKSPACE_READ},
        location_read_enabled=False,
        location_control_enabled=False,
        allowed_workspace_root=str(tmp_path),
    )
    broker = CapabilityBroker(registry=registry, session_policy=policy)
    return broker, policy, loc_tool


def test_broker_rejects_location_when_permission_missing(broker_setup):
    broker, policy, _ = broker_setup
    proposal = ToolCallProposal(tool_name="get_device_location", arguments={})
    verdict = broker.evaluate(proposal)

    assert verdict.allowed is False
    assert "lacks required permission 'location:read'" in verdict.reason


def test_broker_rejects_location_when_policy_flag_disabled(broker_setup):
    broker, policy, _ = broker_setup
    policy.allowed_permissions.add(PermissionType.LOCATION_READ)
    policy.location_read_enabled = False

    proposal = ToolCallProposal(tool_name="get_device_location", arguments={})
    verdict = broker.evaluate(proposal)

    assert verdict.allowed is False
    assert "disabled for this session" in verdict.reason


def test_broker_allows_location_when_explicitly_granted(broker_setup):
    broker, policy, _ = broker_setup
    policy.allowed_permissions.add(PermissionType.LOCATION_READ)
    policy.location_read_enabled = True

    proposal = ToolCallProposal(tool_name="get_device_location", arguments={})
    verdict = broker.evaluate(proposal)

    assert verdict.allowed is True
    assert "Authorized" in verdict.reason


def test_broker_rejects_unexpected_arguments(broker_setup):
    broker, policy, _ = broker_setup
    policy.allowed_permissions.add(PermissionType.LOCATION_READ)
    policy.location_read_enabled = True

    # Schema specifies additionalProperties: false
    proposal = ToolCallProposal(tool_name="get_device_location", arguments={"enable": True})
    verdict = broker.evaluate(proposal)

    assert verdict.allowed is False
    assert "Unexpected parameter 'enable'" in verdict.reason


@pytest.mark.asyncio
async def test_location_tool_execution(broker_setup):
    _, _, tool = broker_setup
    result = await tool.execute({})
    assert result["ok"] is True
    assert "latitude" in result
    assert "longitude" in result

    verified, details = await tool.verify({}, result)
    assert verified is True
