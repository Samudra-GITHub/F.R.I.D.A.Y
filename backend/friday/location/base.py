"""Abstract Base Class for Device Location Providers."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional
from schemas.contracts import DeviceLocationFix, FixStatus


class BaseLocationProvider(ABC):
    """Abstract interface for location telemetry sources.
    
    Guarantees:
    - Never fabricates coordinates if fix is unavailable.
    - Accurately captures status, accuracy, timestamp, and staleness.
    - Decoupled from geocoding or cloud map APIs.
    """

    @abstractmethod
    async def get_current_location(self) -> DeviceLocationFix:
        """Query the underlying platform for the current device location."""
        pass

    @abstractmethod
    async def check_provider_status(self) -> str:
        """Check hardware, platform, or permission availability."""
        pass

    @staticmethod
    def calculate_is_stale(timestamp_utc_str: Optional[str], threshold_seconds: int = 180) -> bool:
        """Determine if a fix exceeds the staleness threshold."""
        if not timestamp_utc_str:
            return True
        try:
            fix_time = datetime.fromisoformat(timestamp_utc_str)
            now = datetime.now(timezone.utc)
            delta = (now - fix_time).total_seconds()
            return delta > threshold_seconds
        except Exception:
            return True
