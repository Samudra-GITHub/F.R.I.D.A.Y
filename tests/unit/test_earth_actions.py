"""Ask the Earth: the action contract, the tools, and what a turn sends to the Earth screen."""

from datetime import date

import httpx
import pytest

from backend.friday.earth.actions import MAX_ACTIONS, actions_for_tool_result, unmatched_record_mentions, validate_action
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.earth_tools import ControlEarthTool
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.time_tool import GetLocalTimeTool
from backend.friday.conversation.orchestrator import ConversationOrchestrator
from backend.friday.models.base import BaseModelAdapter, ModelResponse
from backend.friday.world.history import (
    HistoryRangeError,
    HistoryResult,
    HistoryService,
    bbox_around,
    earthquake_records,
    eonet_records,
    km_between,
    validate_range,
)
from schemas.contracts import ConversationRequest, PermissionType, SessionPolicy


# ---- The contract -------------------------------------------------------------

@pytest.mark.parametrize(
    "action",
    [
        {"type": "run_script", "code": "alert(1)"},
        {"type": "focus", "latitude": 95, "longitude": 0},
        {"type": "focus", "latitude": 0, "longitude": 0, "url": "https://example.com"},
        {"type": "set_layer", "layer": "everything", "enabled": True},
        {"type": "set_preset", "preset": "moon"},
        {"type": "select_aircraft", "query": "<script>"},
        {"type": "select_satellite", "query": "javascript:alert(1)"},
        {"type": "show_records", "records": [{"id": "x", "category": "earthquake", "latitude": 0, "longitude": 0,
                                              "title": "t", "source": "s", "onclick": "x"}]},
    ],
)
def test_anything_outside_the_contract_is_refused(action):
    with pytest.raises(ValueError):
        validate_action(action)


def test_valid_actions_pass_unchanged():
    assert validate_action({"type": "return_global"}) == {"type": "return_global"}
    assert validate_action({"type": "focus", "latitude": 28.6, "longitude": 77.2})["preset"] == "regional"
    assert validate_action({"type": "select_satellite", "query": "ISS (ZARYA)"})["query"] == "ISS (ZARYA)"


def test_control_earth_builds_only_the_fields_its_action_uses():
    tool = ControlEarthTool()
    assert tool.build_action({"action": "set_preset", "preset": "continent", "latitude": 3}) == {
        "type": "set_preset", "preset": "continent"}
    assert tool.build_action({"action": "focus_user"}) == {"type": "focus_user"}
    with pytest.raises(ValueError):
        tool.build_action({"action": "focus"})
    with pytest.raises(ValueError):
        tool.build_action({"action": "self_destruct"})


@pytest.mark.asyncio
async def test_control_earth_never_claims_the_screen_changed():
    tool = ControlEarthTool()
    out = await tool.execute({"action": "return_global"})
    verified, details = await tool.verify({"action": "return_global"}, out)
    assert out["requested"] == {"type": "return_global"}
    assert verified is False
    assert "confirms" in details


# ---- What a tool result sends to the globe ------------------------------------

QUAKES = {
    "ok": True,
    "earthquakes": [
        {"id": "us1", "title": "M 4.8 - 10 km S of X", "magnitude": 4.8, "latitude": 10.0, "longitude": 20.0,
         "time_utc": "2026-11-03T10:00:00Z", "url": "https://earthquake.usgs.gov/1"},
        {"id": "us2", "title": "M 4.1 - Y", "magnitude": 4.1, "latitude": 200.0, "longitude": 20.0,
         "time_utc": "2026-11-03T11:00:00Z"},
    ],
}


def test_earthquake_results_turn_the_layer_on_and_show_only_real_records():
    actions = actions_for_tool_result("get_earthquakes", {"min_magnitude": 4}, QUAKES)
    assert actions[0] == {"type": "set_layer", "layer": "earthquakes", "enabled": True}
    records = actions[1]["records"]
    assert [r["id"] for r in records] == ["usgs:us1"], "a record with an impossible position is dropped"
    assert records[0]["source"] == "USGS"


def test_failed_or_empty_results_send_nothing():
    assert actions_for_tool_result("get_earthquakes", {}, {"ok": False}) == []
    assert actions_for_tool_result("get_earthquakes", {}, None) == []
    assert actions_for_tool_result("get_local_time", {}, {"ok": True}) == []


def test_a_single_result_is_selected_and_weather_is_focused():
    one = {"ok": True, "earthquakes": QUAKES["earthquakes"][:1]}
    assert actions_for_tool_result("get_earthquakes", {}, one)[-1] == {"type": "select_record", "id": "usgs:us1"}
    weather = {"ok": True, "weather": {"latitude": 51.5, "longitude": -0.1, "condition": "Rain", "temperature_c": 9}}
    actions = actions_for_tool_result("get_weather", {}, weather)
    assert actions[-1]["type"] == "focus" and actions[-1]["preset"] == "local"


def test_an_answer_naming_a_record_no_tool_returned_is_flagged():
    # Titles from a live run, and the record the local model invented in its answer.
    shown = [{"type": "show_records", "records": [
        {"title": "M 4.9 - 9 km N of Delta, B.C., MX"}, {"title": "M 5.2 - Mid-Indian Ridge"},
    ]}]
    answer = (
        "1. **M 5.2 - 14 km W of Pisco, Peru**\n   - Felt Reports: 284\n"
        "2. **M 5.2 - Mid-Indian Ridge**\n"
        "3. M 4.9 – 9 km N of Delta, B.C., MX"
    )
    assert unmatched_record_mentions(answer, shown) == ["M 5.2 - 14 km W of Pisco, Peru"]
    assert unmatched_record_mentions("M 5.2 - Mid-Indian Ridge", []) == [], "nothing to check against"
    assert unmatched_record_mentions("Two earthquakes, both small.", shown) == []


# ---- A whole turn ---------------------------------------------------------------

class Scripted(BaseModelAdapter):
    def __init__(self, responses):
        self.responses = list(responses)

    async def is_available(self):
        return True

    async def chat(self, messages, tools=None):
        return self.responses.pop(0) if self.responses else ModelResponse(content="Done.")


def _orchestrator(responses, permissions):
    registry = ToolRegistry()
    registry.register(GetLocalTimeTool())
    registry.register(ControlEarthTool())
    broker = CapabilityBroker(registry=registry, session_policy=SessionPolicy(allowed_permissions=permissions, allowed_workspace_root="."))
    return ConversationOrchestrator(model_adapter=Scripted(responses), registry=registry, broker=broker)


def _call(name, args):
    return ModelResponse(content="", tool_calls=[{"function": {"name": name, "arguments": args}}])


@pytest.mark.asyncio
async def test_a_turn_returns_the_validated_earth_request():
    orch = _orchestrator(
        [_call("control_earth", {"action": "focus", "latitude": 20.6, "longitude": 78.9, "preset": "continent"}),
         ModelResponse(content="I asked the Earth screen to show India.")],
        {PermissionType.EARTH_VIEW},
    )
    resp = await orch.execute_turn(ConversationRequest(message="Show me India"))
    assert resp.earth_actions == [{"type": "focus", "latitude": 20.6, "longitude": 78.9, "preset": "continent"}]
    assert resp.tool_calls[0].arguments["action"] == "focus"


@pytest.mark.asyncio
async def test_an_out_of_schema_request_never_reaches_the_screen():
    orch = _orchestrator(
        [_call("control_earth", {"action": "set_layer", "layer": "everything", "enabled": True}),
         ModelResponse(content="Done.")],
        {PermissionType.EARTH_VIEW},
    )
    resp = await orch.execute_turn(ConversationRequest(message="Show everything"))
    assert resp.earth_actions == []
    assert resp.tool_calls[0].allowed is False


@pytest.mark.asyncio
async def test_without_the_permission_nothing_is_requested():
    orch = _orchestrator(
        [_call("control_earth", {"action": "return_global"}), ModelResponse(content="Ok.")],
        {PermissionType.SYSTEM_TIME},
    )
    resp = await orch.execute_turn(ConversationRequest(message="Global"))
    assert resp.earth_actions == []


@pytest.mark.asyncio
async def test_actions_are_capped_per_turn():
    calls = [_call("control_earth", {"action": "return_global"}) for _ in range(MAX_ACTIONS + 3)]
    orch = _orchestrator(calls + [ModelResponse(content="Ok.")], {PermissionType.EARTH_VIEW})
    orch.max_calls_per_turn = 50
    orch.max_turns = 50
    resp = await orch.execute_turn(ConversationRequest(message="spin"))
    assert len(resp.earth_actions) <= MAX_ACTIONS


# ---- History --------------------------------------------------------------------

def test_date_ranges_are_checked_against_what_archives_hold():
    today = date(2026, 11, 4)
    assert validate_range(date(2026, 10, 1), date(2026, 10, 31), today)
    for start, end in [
        (date(2026, 11, 5), date(2026, 11, 6)),
        (date(2026, 10, 2), date(2026, 10, 1)),
        (date(1899, 12, 31), date(1900, 1, 1)),
        (date(2026, 1, 1), date(2026, 6, 1)),
    ]:
        with pytest.raises(HistoryRangeError):
            validate_range(start, end, today)


def test_usgs_features_without_position_magnitude_or_time_are_dropped():
    features = [
        {"id": "a", "geometry": {"coordinates": [20, 10, 5]}, "properties": {"mag": 5.1, "time": 1762160000000, "title": "M 5.1"}},
        {"id": "b", "geometry": {"coordinates": [20, 10]}, "properties": {"mag": None, "time": 1762160000000}},
        {"id": "c", "geometry": {}, "properties": {"mag": 4, "time": 1762160000000}},
        {"id": "d", "geometry": {"coordinates": [20, 10]}, "properties": {"mag": 4}},
    ]
    records = earthquake_records(features)
    assert [r["id"] for r in records] == ["usgs:a"]
    assert records[0]["time_utc"].startswith("2025-11-03")


def test_eonet_events_are_placed_only_at_observations_inside_the_range():
    events = [
        {"id": "E1", "title": "Fire", "categories": [{"title": "Wildfires"}], "geometry": [
            {"date": "2026-10-01T00:00:00Z", "type": "Point", "coordinates": [10, 20]},
            {"date": "2026-10-05T00:00:00Z", "type": "Point", "coordinates": [11, 21]},
            {"date": "2026-10-20T00:00:00Z", "type": "Point", "coordinates": [12, 22]},
        ]},
        {"id": "E2", "title": "Storm", "geometry": [{"date": "2026-09-01T00:00:00Z", "type": "Point", "coordinates": [0, 0]}]},
    ]
    records = eonet_records(events, date(2026, 10, 1), date(2026, 10, 10))
    assert len(records) == 1
    assert records[0]["latitude"] == 21 and records[0]["time_utc"].startswith("2026-10-05")


def test_distance_and_box_geometry():
    assert km_between(0, 0, 0, 1) == pytest.approx(111.2, rel=0.01)
    west, north, east, south = bbox_around(10, 20, 111)
    assert north == pytest.approx(11, abs=0.01) and south == pytest.approx(9, abs=0.01)
    assert west < 20 < east


@pytest.mark.asyncio
async def test_an_unreachable_archive_is_reported_missing_not_empty():
    def boom(request):
        raise httpx.ConnectError("offline")

    svc = HistoryService(transport=httpx.MockTransport(boom))
    result = HistoryResult()
    await svc.earthquakes(date(2026, 10, 1), date(2026, 10, 2), 4.5, result)
    await svc.events(date(2026, 10, 1), date(2026, 10, 2), result)
    assert result.records == []
    assert {m["provider"] for m in result.missing} == {"USGS", "NASA EONET"}


@pytest.mark.asyncio
async def test_history_asks_usgs_for_the_exact_range_and_area():
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"features": []})

    svc = HistoryService(transport=httpx.MockTransport(handler))
    await svc.earthquakes(date(2026, 10, 1), date(2026, 10, 3), 4.0, HistoryResult(), center=(10, 20), radius_km=300)
    assert seen["starttime"] == "2026-10-01"
    assert seen["endtime"] == "2026-10-04", "the end day is included"
    assert seen["maxradiuskm"] == "300" and seen["minmagnitude"] == "4.0"
