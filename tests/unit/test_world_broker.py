"""Unit tests for CapabilityBroker governance over World Intelligence tools."""

from typing import Tuple
import pytest
from schemas.contracts import (
    PermissionType,
    SessionPolicy,
    ToolCallProposal,
)
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.world_tools import (
    GetDisasterAlertsTool,
    GetEarthquakesTool,
    GetNaturalEventsTool,
    GetWeatherTool,
    GetWorldStatusTool,
)
from backend.friday.world.service import WorldIntelligenceService


def build_test_broker(world_read_enabled: bool = True) -> Tuple[CapabilityBroker, ToolRegistry]:
    registry = ToolRegistry()
    service = WorldIntelligenceService()
    registry.register(GetEarthquakesTool(world_service=service))
    registry.register(GetWeatherTool(world_service=service))
    registry.register(GetNaturalEventsTool(world_service=service))
    registry.register(GetDisasterAlertsTool(world_service=service))
    registry.register(GetWorldStatusTool(world_service=service))

    allowed = {PermissionType.SYSTEM_TIME}
    if world_read_enabled:
        allowed.add(PermissionType.WORLD_READ)

    policy = SessionPolicy(
        allowed_permissions=allowed,
        media_control_enabled=False,
        location_read_enabled=False,
        places_search_enabled=False,
        world_read_enabled=world_read_enabled,
        allowed_workspace_root="/test",
    )

    broker = CapabilityBroker(registry=registry, session_policy=policy)
    return broker, registry


def test_broker_authorizes_world_read_tools():
    broker, _ = build_test_broker(world_read_enabled=True)

    # 1. Earthquakes proposal
    p_eq = ToolCallProposal(tool_name="get_earthquakes", arguments={"min_magnitude": 4.5, "limit": 10})
    dec_eq = broker.evaluate(p_eq)
    assert dec_eq.allowed is True

    # 2. Weather proposal with valid coordinates
    p_w = ToolCallProposal(tool_name="get_weather", arguments={"latitude": 35.68, "longitude": 139.76, "location_name": "Tokyo"})
    dec_w = broker.evaluate(p_w)
    assert dec_w.allowed is True

    # 3. Natural events proposal
    p_ev = ToolCallProposal(tool_name="get_natural_events", arguments={"days": 14, "category": "wildfires"})
    dec_ev = broker.evaluate(p_ev)
    assert dec_ev.allowed is True

    # 4. Disaster alerts proposal
    p_dis = ToolCallProposal(tool_name="get_disaster_alerts", arguments={"alert_level": "Red"})
    dec_dis = broker.evaluate(p_dis)
    assert dec_dis.allowed is True

    # 5. World status proposal
    p_st = ToolCallProposal(tool_name="get_world_status", arguments={})
    dec_st = broker.evaluate(p_st)
    assert dec_st.allowed is True


def test_broker_rejects_when_permission_missing():
    broker, _ = build_test_broker(world_read_enabled=False)

    p_eq = ToolCallProposal(tool_name="get_earthquakes", arguments={"min_magnitude": 4.5})
    dec = broker.evaluate(p_eq)
    assert dec.allowed is False
    assert "world:read" in dec.reason


def test_broker_rejects_invalid_coordinates_and_schema():
    broker, _ = build_test_broker(world_read_enabled=True)

    # Weather with out-of-range latitude
    p_bad_lat = ToolCallProposal(tool_name="get_weather", arguments={"latitude": 150.0, "longitude": 10.0})
    dec_lat = broker.evaluate(p_bad_lat)
    assert dec_lat.allowed is False
    assert "out of valid range" in dec_lat.reason

    # Weather missing required coordinates
    p_missing = ToolCallProposal(tool_name="get_weather", arguments={"location_name": "Somewhere"})
    dec_missing = broker.evaluate(p_missing)
    assert dec_missing.allowed is False
    assert "Missing required parameter" in dec_missing.reason

    # Disasters with invalid alert_level enum
    p_bad_enum = ToolCallProposal(tool_name="get_disaster_alerts", arguments={"alert_level": "Catastrophic"})
    dec_enum = broker.evaluate(p_bad_enum)
    assert dec_enum.allowed is False
    assert "not in allowed enum" in dec_enum.reason
