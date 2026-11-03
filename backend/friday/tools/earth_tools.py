"""Tools that let the assistant work with the Earth screen and live aircraft."""

from typing import Any, Dict, Optional, Tuple

from schemas.contracts import PermissionType
from backend.friday.earth.actions import validate_action
from backend.friday.tools.base import BaseTool
from backend.friday.world.flights import FlightProvider


class ControlEarthTool(BaseTool):
    """Request a change to the Earth view. Requests are validated and applied by the Earth screen."""

    name = "control_earth"
    description = (
        "Change what the Earth screen shows. Use it to move the camera (set_preset, focus, focus_user, "
        "return_global), turn a data layer on or off (set_layer), follow a tracked aircraft or satellite by "
        "callsign or name (select_aircraft, select_satellite), or clear the selection. focus_user flies to "
        "the user's own position without revealing it to you. The Earth screen confirms each request; until "
        "it does, say you asked the Earth screen to show it, not that it is shown."
    )
    required_permission = PermissionType.EARTH_VIEW
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "set_preset", "focus", "focus_user", "return_global", "set_layer",
                    "select_aircraft", "select_satellite", "clear_selection",
                ],
            },
            "preset": {"type": "string", "enum": ["global", "continent", "regional", "local", "street"]},
            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
            "layer": {
                "type": "string",
                "enum": ["earthquakes", "flights", "satellites", "military", "vessels", "fires", "cyclones", "weather"],
            },
            "enabled": {"type": "boolean"},
            "query": {"type": "string", "description": "Callsign or satellite name, such as ISS"},
            "label": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    @staticmethod
    def build_action(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Turn tool arguments into one validated action. Raises ValueError if they don't make one."""
        kind = arguments.get("action")
        fields = {k: v for k, v in arguments.items() if k != "action" and v is not None}
        allowed = {
            "set_preset": {"preset"},
            "focus": {"latitude", "longitude", "preset", "label"},
            "focus_user": set(),
            "return_global": set(),
            "set_layer": {"layer", "enabled"},
            "select_aircraft": {"query"},
            "select_satellite": {"query"},
            "clear_selection": set(),
        }.get(kind)
        if allowed is None:
            raise ValueError(f"Unknown Earth action: {kind!r}")
        return validate_action({"type": kind, **{k: v for k, v in fields.items() if k in allowed}})

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        action = self.build_action(arguments)
        return {
            "ok": True,
            "requested": action,
            "note": "Sent to the Earth screen. It reports whether it applied this; it is not confirmed yet.",
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        # The backend can't see the screen, so this is never verified here.
        return False, "Requested; the Earth screen confirms whether it applied it"


class GetAircraftNearbyTool(BaseTool):
    """Live aircraft near a point, from public ADS-B data."""

    name = "get_aircraft_nearby"
    description = (
        "Find live aircraft within a radius of a latitude and longitude, from adsb.lol public ADS-B data. "
        "Returns callsign, position, altitude, speed and track for each aircraft found. Requires world:read."
    )
    required_permission = PermissionType.WORLD_READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
            "radius_nm": {"type": "integer", "minimum": 10, "maximum": 250, "description": "Defaults to 200"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Defaults to 25"},
        },
        "required": ["latitude", "longitude"],
        "additionalProperties": False,
    }

    def __init__(self, provider: Optional[FlightProvider] = None) -> None:
        self.provider = provider or FlightProvider()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        lat = float(arguments["latitude"])
        lng = float(arguments["longitude"])
        radius = int(arguments.get("radius_nm", 200))
        limit = min(int(arguments.get("limit", 25)), 50)
        res = await self.provider.get_flights(lat, lng, radius)
        flights = sorted(res.flights, key=lambda f: (f.on_ground, -(f.altitude_ft or 0)))[:limit]
        return {
            "ok": res.status.value in ("ok", "stale", "empty"),
            "status": res.status.value,
            "count": res.count,
            "returned": len(flights),
            "flights": [f.model_dump(exclude_none=True) for f in flights],
            "provider": res.provider,
            "attribution": res.attribution,
            "retrieved_at": res.retrieved_at,
            "is_stale": res.is_stale,
            "details": res.details,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        if not isinstance(raw_output, dict) or not raw_output.get("ok"):
            return False, f"Aircraft lookup failed: {(raw_output or {}).get('details', 'unknown failure')}"
        return True, f"Verified {raw_output.get('count', 0)} aircraft from adsb.lol"
