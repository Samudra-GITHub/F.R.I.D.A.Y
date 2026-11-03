"""Location Tool for Capability-Broker Governed Device Coordinate Retrieval."""

from typing import Any, Dict, Optional, Tuple
from schemas.contracts import PermissionType, FixStatus
from backend.friday.tools.base import BaseTool
from backend.friday.location.service import LocationService


class GetDeviceLocationTool(BaseTool):
    """Retrieves current verified device coordinates from Windows Location Services."""

    name = "get_device_location"
    description = (
        "Retrieve the latest verified device coordinates, accuracy radius, and fix status "
        "from the local Windows Location Service. Requires user-authorized location:read permission."
    )
    required_permission = PermissionType.LOCATION_READ
    parameters_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self, location_service: Optional[LocationService] = None) -> None:
        self.location_service = location_service or LocationService()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch the latest fix from the location service."""
        status = self.location_service.get_status()
        
        # If tracking is disabled, try an ad-hoc single poll
        if not status.tracking_enabled or not status.latest_fix:
            fix = await self.location_service.poll_once()
        else:
            fix = status.latest_fix

        if fix is None or fix.status == FixStatus.DISABLED:
            return {
                "ok": False,
                "status": "disabled",
                "message": "Windows location service is disabled. Tracking consent required.",
            }

        if fix.status in (FixStatus.DENIED, FixStatus.UNAVAILABLE, FixStatus.ERROR):
            return {
                "ok": False,
                "status": fix.status.value,
                "windows_status": fix.windows_status,
                "message": fix.details or "Unable to acquire location fix from Windows sensor",
            }

        return {
            "ok": True,
            "latitude": fix.latitude,
            "longitude": fix.longitude,
            "accuracy_m": fix.accuracy_m,
            "timestamp_utc": fix.timestamp_utc,
            "status": fix.status.value,
            "is_stale": fix.is_stale,
            "provider": fix.provider,
            "windows_status": fix.windows_status,
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        """Verify whether a valid, non-stale fix was obtained."""
        if not isinstance(raw_output, dict):
            return False, "Output was not a valid dictionary"
        if not raw_output.get("ok"):
            return False, f"Fix unverified: {raw_output.get('message', 'Unknown failure')}"
        if raw_output.get("is_stale"):
            return False, "Fix acquired but marked stale"
        if raw_output.get("latitude") is None or raw_output.get("longitude") is None:
            return False, "Missing coordinate pairs in verified output"
        return True, f"Valid device fix confirmed (accuracy ~{raw_output.get('accuracy_m', 'unknown')}m)"
