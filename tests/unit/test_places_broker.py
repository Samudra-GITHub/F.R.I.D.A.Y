"""Unit tests for Places and Geocoding Capability Broker authorization."""

import pytest
from schemas.contracts import (
    PermissionType,
    SessionPolicy,
    ToolCallProposal,
)
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.places_tool import ReverseGeocodeTool, SearchNearbyPlacesTool
from backend.friday.location.enrichment import NoOpLocationEnricher


@pytest.fixture
def places_registry():
    registry = ToolRegistry()
    registry.register(ReverseGeocodeTool(enricher=NoOpLocationEnricher()))
    registry.register(SearchNearbyPlacesTool(enricher=NoOpLocationEnricher()))
    return registry


def test_broker_rejects_places_search_when_permission_missing(places_registry):
    # Session without PLACES_SEARCH permission
    policy = SessionPolicy(
        allowed_permissions={PermissionType.SYSTEM_TIME},
        places_search_enabled=True,
        allowed_workspace_root="/tmp",
    )
    broker = CapabilityBroker(registry=places_registry, session_policy=policy)

    proposal = ToolCallProposal(
        tool_name="reverse_geocode",
        arguments={"latitude": 28.6139, "longitude": 77.2090},
    )
    decision = broker.evaluate(proposal)
    assert decision.allowed is False
    assert "lacks required permission 'places:search'" in decision.reason


def test_broker_rejects_places_search_when_policy_flag_disabled(places_registry):
    # Permission in set, but flag explicitly disabled
    policy = SessionPolicy(
        allowed_permissions={PermissionType.PLACES_SEARCH},
        places_search_enabled=False,
        allowed_workspace_root="/tmp",
    )
    broker = CapabilityBroker(registry=places_registry, session_policy=policy)

    proposal = ToolCallProposal(
        tool_name="reverse_geocode",
        arguments={"latitude": 28.6139, "longitude": 77.2090},
    )
    decision = broker.evaluate(proposal)
    assert decision.allowed is False
    assert "Places search and geocoding is disabled" in decision.reason


def test_broker_allows_places_search_when_properly_authorized(places_registry):
    policy = SessionPolicy(
        allowed_permissions={PermissionType.PLACES_SEARCH},
        places_search_enabled=True,
        allowed_workspace_root="/tmp",
    )
    broker = CapabilityBroker(registry=places_registry, session_policy=policy)

    # 1. Reverse geocode valid
    decision1 = broker.evaluate(
        ToolCallProposal(
            tool_name="reverse_geocode",
            arguments={"latitude": 28.6139, "longitude": 77.2090},
        )
    )
    assert decision1.allowed is True
    assert "Authorized" in decision1.reason

    # 2. Search nearby valid
    decision2 = broker.evaluate(
        ToolCallProposal(
            tool_name="search_nearby_places",
            arguments={"category": "pharmacy", "radius_m": 1500},
        )
    )
    assert decision2.allowed is True


def test_broker_rejects_unexpected_extra_arguments(places_registry):
    policy = SessionPolicy(
        allowed_permissions={PermissionType.PLACES_SEARCH},
        places_search_enabled=True,
        allowed_workspace_root="/tmp",
    )
    broker = CapabilityBroker(registry=places_registry, session_policy=policy)

    proposal = ToolCallProposal(
        tool_name="reverse_geocode",
        arguments={"latitude": 28.6139, "longitude": 77.2090, "unauthorized_flag": True},
    )
    decision = broker.evaluate(proposal)
    assert decision.allowed is False
    assert "Unexpected parameter 'unauthorized_flag'" in decision.reason


def test_broker_rejects_non_numeric_coordinates(places_registry):
    policy = SessionPolicy(
        allowed_permissions={PermissionType.PLACES_SEARCH},
        places_search_enabled=True,
        allowed_workspace_root="/tmp",
    )
    broker = CapabilityBroker(registry=places_registry, session_policy=policy)

    proposal = ToolCallProposal(
        tool_name="reverse_geocode",
        arguments={"latitude": "twenty-eight-point-six", "longitude": 77.2090},
    )
    decision = broker.evaluate(proposal)
    assert decision.allowed is False
    assert "expected number" in decision.reason


@pytest.mark.asyncio
async def test_places_tool_execution_and_honest_verification():
    enricher = NoOpLocationEnricher()
    tool = ReverseGeocodeTool(enricher=enricher)

    output = await tool.execute({"latitude": 28.6139, "longitude": 77.2090})
    assert output["ok"] is False
    assert output["status"] == "provider_not_configured"
    assert output["formatted_address"] is None

    # Independent verification confirms unconfigured honesty
    is_verified, reason = await tool.verify({"latitude": 28.6139, "longitude": 77.2090}, output)
    assert is_verified is True
    assert "no fabrication detected" in reason

    # Check that verification detects and fails if a fabricated address is reported
    fabricated_output = {
        "ok": False,
        "status": "provider_not_configured",
        "formatted_address": "Fake Street 123, Hallucinated City",
    }
    is_verified_fab, reason_fab = await tool.verify({}, fabricated_output)
    assert is_verified_fab is False
    assert "Fabricated address returned" in reason_fab
