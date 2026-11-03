"""Real-Time World Intelligence Tools for Capability-Broker Governed Execution.

Exposes read-only tools to the AI assistant for querying earthquakes, weather,
natural events, disaster alerts, and provider status.
Requires user-authorized PermissionType.WORLD_READ.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from schemas.contracts import PermissionType
from backend.friday.tools.base import BaseTool
from backend.friday.world.service import WorldIntelligenceService

logger = logging.getLogger("friday.tools.world")


class GetEarthquakesTool(BaseTool):
    """Queries recent earthquakes from official USGS summary feeds."""

    name = "get_earthquakes"
    description = (
        "Query recent global earthquakes from official USGS GeoJSON summary feeds. "
        "Returns magnitude, place name, depth, epicenter coordinates, and USGS links. "
        "Requires world:read permission."
    )
    required_permission = PermissionType.WORLD_READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "min_magnitude": {
                "type": "number",
                "description": "Optional minimum magnitude threshold (e.g. 4.5). Defaults to 0.0.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of earthquakes to return (1-50). Defaults to 10.",
            },
        },
        "additionalProperties": False,
    }

    def __init__(self, world_service: Optional[WorldIntelligenceService] = None) -> None:
        self.world_service = world_service or WorldIntelligenceService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        min_mag = float(arguments.get("min_magnitude", 0.0))
        limit = min(int(arguments.get("limit", 10)), 50)

        res = await self.world_service.get_earthquakes(min_magnitude=min_mag, limit=limit)
        return {
            "ok": res.status in ("ok", "stale", "empty"),
            "status": res.status.value,
            "count": res.count,
            "earthquakes": [eq.model_dump() for eq in res.earthquakes],
            "provider": res.provider,
            "attribution": res.attribution,
            "retrieved_at": res.retrieved_at,
            "is_stale": res.is_stale,
            "details": res.details,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        if not raw_output.get("ok"):
            return False, f"Earthquake lookup failed: {raw_output.get('details', 'Unknown failure')}"
        count = raw_output.get("count", 0)
        stale_note = " (cached snapshot)" if raw_output.get("is_stale") else ""
        return True, f"Verified {count} USGS earthquake records{stale_note}"


class GetWeatherTool(BaseTool):
    """Queries atmospheric weather for specific coordinates from Open-Meteo."""

    name = "get_weather"
    description = (
        "Query current atmospheric weather telemetry and 3-day forecast from Open-Meteo. "
        "Requires explicit latitude and longitude coordinates. "
        "Requires world:read permission."
    )
    required_permission = PermissionType.WORLD_READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number",
                "description": "Latitude (-90 to 90) of the target location.",
            },
            "longitude": {
                "type": "number",
                "description": "Longitude (-180 to 180) of the target location.",
            },
            "location_name": {
                "type": "string",
                "description": "Optional human-readable city or place name for context.",
            },
        },
        "required": ["latitude", "longitude"],
        "additionalProperties": False,
    }

    def __init__(self, world_service: Optional[WorldIntelligenceService] = None) -> None:
        self.world_service = world_service or WorldIntelligenceService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        lat = float(arguments["latitude"])
        lng = float(arguments["longitude"])
        name = arguments.get("location_name")

        res = await self.world_service.get_weather(latitude=lat, longitude=lng, location_name=name)
        return {
            "ok": res.status in ("ok", "stale"),
            "status": res.status.value,
            "weather": res.weather.model_dump() if res.weather else None,
            "provider": res.provider,
            "attribution": res.attribution,
            "retrieved_at": res.retrieved_at,
            "is_stale": res.is_stale,
            "details": res.details,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        if not raw_output.get("ok"):
            return False, f"Weather lookup failed: {raw_output.get('details', 'Unknown failure')}"
        w = raw_output.get("weather")
        if not w:
            return False, "Missing weather record in output"
        stale_note = " (cached snapshot)" if raw_output.get("is_stale") else ""
        return True, f"Verified weather: {w.get('temperature_c')}°C {w.get('condition')}{stale_note}"


class GetNaturalEventsTool(BaseTool):
    """Queries active natural events from NASA EONET v3."""

    name = "get_natural_events"
    description = (
        "Query active natural events (wildfires, severe storms, volcanoes, etc.) from NASA EONET v3. "
        "Returns event title, category, coordinates, observation time, and NASA links. "
        "Requires world:read permission."
    )
    required_permission = PermissionType.WORLD_READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Lookback window in days (1 to 60). Defaults to 30.",
            },
            "category": {
                "type": "string",
                "description": "Optional category filter (e.g. 'wildfires', 'severeStorms', 'volcanoes').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return (1-50). Defaults to 10.",
            },
        },
        "additionalProperties": False,
    }

    def __init__(self, world_service: Optional[WorldIntelligenceService] = None) -> None:
        self.world_service = world_service or WorldIntelligenceService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        days = int(arguments.get("days", 30))
        cat = arguments.get("category")
        limit = min(int(arguments.get("limit", 10)), 50)

        res = await self.world_service.get_events(days=days, category=cat, limit=limit)
        return {
            "ok": res.status in ("ok", "stale", "empty"),
            "status": res.status.value,
            "count": res.count,
            "events": [evt.model_dump() for evt in res.events],
            "provider": res.provider,
            "attribution": res.attribution,
            "retrieved_at": res.retrieved_at,
            "is_stale": res.is_stale,
            "details": res.details,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        if not raw_output.get("ok"):
            return False, f"Natural events lookup failed: {raw_output.get('details', 'Unknown failure')}"
        count = raw_output.get("count", 0)
        stale_note = " (cached snapshot)" if raw_output.get("is_stale") else ""
        return True, f"Verified {count} NASA EONET events{stale_note}"


class GetDisasterAlertsTool(BaseTool):
    """Queries active disaster alerts from GDACS."""

    name = "get_disaster_alerts"
    description = (
        "Query active disaster alerts from the Global Disaster Alert and Coordination System (GDACS). "
        "Returns disaster type, alert level (Green, Orange, Red), coordinates, and report links. "
        "Requires world:read permission."
    )
    required_permission = PermissionType.WORLD_READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "alert_level": {
                "type": "string",
                "enum": ["Green", "Orange", "Red"],
                "description": "Optional alert level filter ('Green', 'Orange', 'Red').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum alerts to return (1-50). Defaults to 10.",
            },
        },
        "additionalProperties": False,
    }

    def __init__(self, world_service: Optional[WorldIntelligenceService] = None) -> None:
        self.world_service = world_service or WorldIntelligenceService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        level = arguments.get("alert_level")
        limit = min(int(arguments.get("limit", 10)), 50)

        res = await self.world_service.get_disasters(alert_level=level, limit=limit)
        return {
            "ok": res.status in ("ok", "stale", "empty"),
            "status": res.status.value,
            "count": res.count,
            "disasters": [d.model_dump() for d in res.disasters],
            "provider": res.provider,
            "attribution": res.attribution,
            "retrieved_at": res.retrieved_at,
            "is_stale": res.is_stale,
            "details": res.details,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        if not raw_output.get("ok"):
            return False, f"Disaster alerts lookup failed: {raw_output.get('details', 'Unknown failure')}"
        count = raw_output.get("count", 0)
        stale_note = " (cached snapshot)" if raw_output.get("is_stale") else ""
        return True, f"Verified {count} GDACS disaster alerts{stale_note}"


class GetWorldStatusTool(BaseTool):
    """Queries aggregated operational status and health across all world intelligence providers."""

    name = "get_world_status"
    description = (
        "Query operational health, cache status, and freshness telemetry across all "
        "W.E.D.N.E.S.D.A.Y. world intelligence providers (USGS, Open-Meteo, NASA EONET, GDACS, News). "
        "Requires world:read permission."
    )
    required_permission = PermissionType.WORLD_READ
    parameters_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self, world_service: Optional[WorldIntelligenceService] = None) -> None:
        self.world_service = world_service or WorldIntelligenceService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        res = await self.world_service.get_status()
        return {
            "ok": True,
            "status": res.status,
            "providers": {k: v.model_dump() for k, v in res.providers.items()},
            "retrieved_at": res.retrieved_at,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        return True, f"World status verified: {raw_output.get('status', 'unknown')}"
