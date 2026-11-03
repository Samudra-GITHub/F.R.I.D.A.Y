"""Places and Geocoding Tools for Capability-Broker Governed External Location Intelligence.

Enforces PermissionType.PLACES_SEARCH independently from device location acquisition.
Does NOT fabricate places or addresses when the provider is unconfigured.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from schemas.contracts import PermissionType, FixStatus
from backend.friday.tools.base import BaseTool
from backend.friday.location.service import LocationService
from backend.friday.location.enrichment import BaseLocationEnricher, get_location_enricher, validate_coordinates

logger = logging.getLogger("friday.tools.places")


class ReverseGeocodeTool(BaseTool):
    """Resolves coordinates or the verified device location into a human-readable address."""

    name = "reverse_geocode"
    description = (
        "Resolve geographic coordinates (latitude and longitude) into a human-readable street address "
        "and locality using Google Maps Geocoding. If coordinates are omitted, resolves the current "
        "verified device location. Requires user-authorized places:search permission."
    )
    required_permission = PermissionType.PLACES_SEARCH
    parameters_schema = {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number",
                "description": "Optional latitude (-90 to 90). If omitted, uses current device fix.",
            },
            "longitude": {
                "type": "number",
                "description": "Optional longitude (-180 to 180). If omitted, uses current device fix.",
            },
        },
        "additionalProperties": False,
    }

    def __init__(
        self,
        enricher: Optional[BaseLocationEnricher] = None,
        location_service: Optional[LocationService] = None,
    ) -> None:
        self.enricher = enricher or get_location_enricher()
        self.location_service = location_service or LocationService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute reverse geocoding after Capability Broker authorization."""
        lat = arguments.get("latitude")
        lng = arguments.get("longitude")

        # If coordinates are omitted, resolve from device location
        if lat is None or lng is None:
            loc_status = self.location_service.get_status()
            fix = loc_status.latest_fix
            if fix is None or fix.status != FixStatus.ACQUIRED or fix.latitude is None or fix.longitude is None:
                fix = await self.location_service.poll_once()

            if fix is None or fix.status != FixStatus.ACQUIRED or fix.latitude is None or fix.longitude is None:
                return {
                    "ok": False,
                    "status": "no_fix",
                    "provider": self.enricher.provider_name,
                    "message": "No verified device location fix available to resolve. Supply explicit coordinates or enable device tracking.",
                }
            lat = fix.latitude
            lng = fix.longitude

        is_valid, err_msg = validate_coordinates(lat, lng)
        if not is_valid:
            return {
                "ok": False,
                "status": "invalid_coordinates",
                "provider": self.enricher.provider_name,
                "message": err_msg,
            }

        response = await self.enricher.reverse_geocode(float(lat), float(lng))
        return {
            "ok": response.status == "success",
            "status": response.status,
            "latitude": float(lat),
            "longitude": float(lng),
            "formatted_address": response.address.formatted_address if response.address else None,
            "address": response.address.model_dump() if response.address else None,
            "provider": response.provider,
            "details": response.details,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        """Verify geocoding execution outcome."""
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        status = raw_output.get("status")
        if status == "provider_not_configured":
            # Correctly unconfigured; must NOT return a fabricated address
            if raw_output.get("formatted_address") is not None:
                return False, "Fabricated address returned when provider is not configured"
            return True, "Provider not configured as expected; no fabrication detected"
        if status == "success":
            addr = raw_output.get("formatted_address")
            if not addr:
                return False, "Success status returned without formatted address"
            return True, f"Verified address resolution: {addr[:40]}..."
        if status in ("no_fix", "zero_results", "error", "rate_limited", "invalid_coordinates"):
            return True, f"Handled non-success status correctly: {status}"
        return False, f"Unknown status: {status}"


class SearchNearbyPlacesTool(BaseTool):
    """Searches for points of interest near coordinates or the device location."""

    name = "search_nearby_places"
    description = (
        "Search for points of interest (e.g., pharmacy, hospital, gas_station, cafe, restaurant, supermarket) "
        "near geographic coordinates or the current verified device location via Google Places API (New). "
        "Requires user-authorized places:search permission."
    )
    required_permission = PermissionType.PLACES_SEARCH
    parameters_schema = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Category or type: hospital, pharmacy, gas_station, cafe, restaurant, supermarket, etc.",
            },
            "keyword": {
                "type": "string",
                "description": "Free-text search keyword (e.g., 'urgent care', 'espresso')",
            },
            "radius_m": {
                "type": "integer",
                "description": "Search radius in metres (100 to 10000). Default is 1500m.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of places to return (1 to 20). Default is 10.",
            },
            "latitude": {
                "type": "number",
                "description": "Optional center latitude (-90 to 90). If omitted, uses current device fix.",
            },
            "longitude": {
                "type": "number",
                "description": "Optional center longitude (-180 to 180). If omitted, uses current device fix.",
            },
        },
        "additionalProperties": False,
    }

    def __init__(
        self,
        enricher: Optional[BaseLocationEnricher] = None,
        location_service: Optional[LocationService] = None,
    ) -> None:
        self.enricher = enricher or get_location_enricher()
        self.location_service = location_service or LocationService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute nearby search after Capability Broker authorization."""
        lat = arguments.get("latitude")
        lng = arguments.get("longitude")
        category = arguments.get("category")
        keyword = arguments.get("keyword")
        radius_m = arguments.get("radius_m", 1500)
        limit = arguments.get("limit", 10)

        # If coordinates are omitted, resolve from device location
        if lat is None or lng is None:
            loc_status = self.location_service.get_status()
            fix = loc_status.latest_fix
            if fix is None or fix.status != FixStatus.ACQUIRED or fix.latitude is None or fix.longitude is None:
                fix = await self.location_service.poll_once()

            if fix is None or fix.status != FixStatus.ACQUIRED or fix.latitude is None or fix.longitude is None:
                return {
                    "ok": False,
                    "status": "no_fix",
                    "places": [],
                    "provider": self.enricher.provider_name,
                    "message": "No verified device location fix available to search around. Supply explicit coordinates or enable device tracking.",
                }
            lat = fix.latitude
            lng = fix.longitude

        is_valid, err_msg = validate_coordinates(lat, lng)
        if not is_valid:
            return {
                "ok": False,
                "status": "invalid_coordinates",
                "places": [],
                "provider": self.enricher.provider_name,
                "message": err_msg,
            }

        response = await self.enricher.search_nearby(
            lat=float(lat),
            lng=float(lng),
            category=category,
            keyword=keyword,
            radius_m=radius_m,
            limit=limit,
        )

        return {
            "ok": response.status in ("success", "empty"),
            "status": response.status,
            "center_lat": response.center_lat,
            "center_lng": response.center_lng,
            "radius_m": response.radius_m,
            "category": response.category,
            "query": response.query,
            "places": [p.model_dump() for p in response.places],
            "places_count": len(response.places),
            "provider": response.provider,
            "details": response.details,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        """Verify nearby places search execution outcome."""
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        status = raw_output.get("status")
        places = raw_output.get("places", [])
        if status == "provider_not_configured":
            if places:
                return False, "Fabricated places returned when provider is not configured"
            return True, "Provider not configured as expected; no fabrication detected"
        if status == "success":
            return True, f"Found {len(places)} verified places"
        if status in ("empty", "no_fix", "error", "rate_limited", "invalid_coordinates"):
            return True, f"Handled non-success status correctly: {status}"
        return False, f"Unknown status: {status}"
