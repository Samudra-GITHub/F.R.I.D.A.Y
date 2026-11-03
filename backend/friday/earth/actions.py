"""Earth actions: the only way the assistant can change what the Earth screen shows.

Every action is a fixed, typed shape with bounded values. Nothing here carries code,
URLs, or free-form commands, and the frontend validates each action again before
running it. An action is a request: the Earth screen reports whether it applied it,
and only that report may be described as done.

Records are the shared model for anything drawn on the globe from real data:
earthquakes, natural events, disaster alerts, aircraft, and the like.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

Preset = Literal["global", "continent", "regional", "local", "street"]
Layer = Literal["earthquakes", "flights", "satellites", "military", "vessels", "fires", "cyclones", "weather"]
RecordCategory = Literal["earthquake", "event", "disaster", "aircraft", "weather", "place"]

MAX_RECORDS = 500
MAX_ACTIONS = 12


class EarthRecord(BaseModel):
    """One real thing at one place, as the globe draws it. Built only from provider data."""

    model_config = {"extra": "forbid"}

    id: str = Field(..., min_length=1, max_length=120)
    category: RecordCategory
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    title: str = Field(..., max_length=200)
    time_utc: Optional[str] = Field(default=None, max_length=40)
    magnitude: Optional[float] = Field(default=None, ge=-2, le=11)
    source: str = Field(..., max_length=80)
    url: Optional[str] = Field(default=None, max_length=500)


class _Action(BaseModel):
    model_config = {"extra": "forbid"}


class SetPreset(_Action):
    type: Literal["set_preset"]
    preset: Preset


class FocusOn(_Action):
    type: Literal["focus"]
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    preset: Preset = "regional"
    label: Optional[str] = Field(default=None, max_length=120)


class FocusUser(_Action):
    """Fly to the user's own position, using the location mode they chose. The model never sees it."""

    type: Literal["focus_user"]


class ReturnGlobal(_Action):
    type: Literal["return_global"]


class SetLayer(_Action):
    type: Literal["set_layer"]
    layer: Layer
    enabled: bool


class ShowRecords(_Action):
    """Draw these records, replacing what the same group drew before. An empty list clears the group."""

    type: Literal["show_records"]
    records: List[EarthRecord] = Field(..., max_length=MAX_RECORDS)
    group: Literal["ask", "time", "compare", "investigate", "pulse"] = "ask"
    label: Optional[str] = Field(default=None, max_length=120)


class SelectRecord(_Action):
    type: Literal["select_record"]
    id: str = Field(..., min_length=1, max_length=120)


class SelectTracked(_Action):
    """Follow an aircraft or satellite the Earth screen is already tracking from its own feeds."""

    type: Literal["select_aircraft", "select_satellite"]
    query: str = Field(..., min_length=1, max_length=40, pattern=r"^[A-Za-z0-9 ()/.\-]+$")


class ClearSelection(_Action):
    type: Literal["clear_selection"]


EarthAction = Annotated[
    Union[SetPreset, FocusOn, FocusUser, ReturnGlobal, SetLayer, ShowRecords, SelectRecord, SelectTracked, ClearSelection],
    Field(discriminator="type"),
]
_ADAPTER = TypeAdapter(EarthAction)


def validate_action(data: Any) -> Dict[str, Any]:
    """Validate one action, returning its plain dict form. Raises ValueError if it isn't allowed."""
    try:
        return _ADAPTER.validate_python(data).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise ValueError(f"Not a valid Earth action: {exc.errors()[0].get('msg', 'invalid')}") from exc


def _record(**fields: Any) -> Optional[Dict[str, Any]]:
    try:
        return EarthRecord(**fields).model_dump(exclude_none=True)
    except (ValidationError, TypeError):
        return None


def _records_from_output(tool_name: str, output: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Optional[Dict[str, Any]]] = []
    if tool_name == "get_earthquakes":
        for q in output.get("earthquakes", []):
            out.append(_record(
                id=f"usgs:{q.get('id')}", category="earthquake", latitude=q.get("latitude"),
                longitude=q.get("longitude"), title=q.get("title") or q.get("place") or "Earthquake",
                time_utc=q.get("time_utc"), magnitude=q.get("magnitude"), source="USGS", url=q.get("url"),
            ))
    elif tool_name == "get_natural_events":
        for e in output.get("events", []):
            out.append(_record(
                id=f"eonet:{e.get('id')}", category="event", latitude=e.get("latitude"),
                longitude=e.get("longitude"), title=e.get("title") or "Natural event",
                time_utc=e.get("timestamp_utc"), source="NASA EONET", url=e.get("source_url"),
            ))
    elif tool_name == "get_disaster_alerts":
        for d in output.get("disasters", []):
            out.append(_record(
                id=f"gdacs:{d.get('id')}", category="disaster", latitude=d.get("latitude"),
                longitude=d.get("longitude"), title=d.get("title") or "Disaster alert",
                time_utc=d.get("timestamp_utc"), source="GDACS", url=d.get("url"),
            ))
    elif tool_name == "get_aircraft_nearby":
        for f in output.get("flights", []):
            label = (f.get("callsign") or f.get("registration") or f.get("hex") or "").strip()
            out.append(_record(
                id=f"adsb:{f.get('hex')}", category="aircraft", latitude=f.get("latitude"),
                longitude=f.get("longitude"), title=label or "Aircraft", source="adsb.lol",
            ))
    elif tool_name == "get_weather":
        w = output.get("weather") or {}
        out.append(_record(
            id=f"weather:{w.get('latitude')},{w.get('longitude')}", category="weather",
            latitude=w.get("latitude"), longitude=w.get("longitude"),
            title=" · ".join(str(x) for x in [w.get("location_name"), w.get("condition"),
                             f"{w.get('temperature_c')} °C" if w.get("temperature_c") is not None else None] if x),
            time_utc=w.get("source_time_utc"), source="Open-Meteo",
        ))
    return [r for r in out if r][:MAX_RECORDS]


_LAYER_FOR_TOOL = {"get_earthquakes": "earthquakes", "get_aircraft_nearby": "flights"}


def actions_for_tool_result(tool_name: str, arguments: Dict[str, Any], output: Any) -> List[Dict[str, Any]]:
    """The globe's response to a successful read tool, built only from the records it returned."""
    if not isinstance(output, dict) or not output.get("ok"):
        return []
    actions: List[Dict[str, Any]] = []
    layer = _LAYER_FOR_TOOL.get(tool_name)
    if layer:
        actions.append({"type": "set_layer", "layer": layer, "enabled": True})
    records = _records_from_output(tool_name, output)
    if records:
        actions.append({"type": "show_records", "records": records, "label": tool_name.replace("_", " ")})
        if tool_name in ("get_weather", "get_aircraft_nearby"):
            first = records[0]
            preset = "local" if tool_name == "get_weather" else "regional"
            actions.append({"type": "focus", "latitude": first["latitude"], "longitude": first["longitude"], "preset": preset})
        elif len(records) == 1:
            actions.append({"type": "select_record", "id": records[0]["id"]})
    valid = []
    for action in actions:
        try:
            valid.append(validate_action(action))
        except ValueError:
            continue
    return valid


# "M 5.2 - 14 km W of Pisco, Peru", as USGS titles and model answers write an earthquake.
_QUAKE_MENTION = re.compile(r"\bM\s?(\d{1,2}(?:\.\d)?)\s*[-\u2013\u2014]\s*([^\n*|\]\[]+)")


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", text.lower()).strip()


def unmatched_record_mentions(answer: str, actions: List[Dict[str, Any]]) -> List[str]:
    """Earthquakes the answer names that are not among the records the tools returned.

    A small local model can write a convincing record that no source gave it. This
    check is deterministic: a mention counts only if its magnitude and place match a
    record's title.
    """
    titles = [
        _plain(r.get("title", ""))
        for a in actions
        if a.get("type") == "show_records"
        for r in a.get("records", [])
    ]
    if not titles:
        return []
    unmatched: List[str] = []
    for magnitude, place in _QUAKE_MENTION.findall(answer):
        mention = f"M {magnitude} - {place.strip()}"
        plain = _plain(mention)
        if not any(plain in title or title in plain for title in titles) and mention not in unmatched:
            unmatched.append(mention)
    return unmatched
