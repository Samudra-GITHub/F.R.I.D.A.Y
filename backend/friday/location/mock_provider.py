"""Mock Location Provider for hermetic testing and CI verification."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from schemas.contracts import DeviceLocationFix, FixStatus, WindowsLocationStatus
from backend.friday.location.base import BaseLocationProvider


class MockLocationProvider(BaseLocationProvider):
    """Programmable location provider for automated tests.
    
    Prevents leaking user coordinates in test logs and allows simulating all
    hardware, permission, and network failure modes deterministically.
    """

    def __init__(
        self,
        status: FixStatus = FixStatus.FRESH,
        latitude: Optional[float] = 37.7749,
        longitude: Optional[float] = -122.4194,
        accuracy_m: Optional[float] = 15.0,
        age_seconds: int = 0,
        windows_status: str = WindowsLocationStatus.READY.value,
        details: Optional[str] = "Mock provider fix",
    ) -> None:
        self.status = status
        self.latitude = latitude
        self.longitude = longitude
        self.accuracy_m = accuracy_m
        self.age_seconds = age_seconds
        self.windows_status = windows_status
        self.details = details

    def set_state(
        self,
        status: FixStatus,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        accuracy_m: Optional[float] = None,
        age_seconds: int = 0,
        windows_status: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Dynamically reconfigure mock provider state."""
        self.status = status
        if latitude is not None:
            self.latitude = latitude
        if longitude is not None:
            self.longitude = longitude
        if accuracy_m is not None:
            self.accuracy_m = accuracy_m
        self.age_seconds = age_seconds
        if windows_status is not None:
            self.windows_status = windows_status
        if details is not None:
            self.details = details

    async def get_current_location(self) -> DeviceLocationFix:
        """Return configured mock fix."""
        fix_time = datetime.now(timezone.utc) - timedelta(seconds=self.age_seconds)
        ts_utc = fix_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        if self.status == FixStatus.FRESH:
            return DeviceLocationFix(
                latitude=self.latitude,
                longitude=self.longitude,
                accuracy_m=self.accuracy_m,
                timestamp_utc=ts_utc,
                status=FixStatus.FRESH,
                windows_status=self.windows_status,
                provider="MockLocationProvider",
                is_stale=False,
                details=self.details,
            )
        elif self.status == FixStatus.STALE:
            return DeviceLocationFix(
                latitude=self.latitude,
                longitude=self.longitude,
                accuracy_m=self.accuracy_m,
                timestamp_utc=ts_utc,
                status=FixStatus.STALE,
                windows_status=self.windows_status,
                provider="MockLocationProvider",
                is_stale=True,
                details="Mock fix is stale",
            )
        elif self.status == FixStatus.DENIED:
            return DeviceLocationFix(
                status=FixStatus.DENIED,
                windows_status=WindowsLocationStatus.DISABLED.value,
                provider="MockLocationProvider",
                is_stale=False,
                details="Location access denied by policy or Windows Settings",
            )
        elif self.status == FixStatus.UNAVAILABLE:
            return DeviceLocationFix(
                status=FixStatus.UNAVAILABLE,
                windows_status=self.windows_status or WindowsLocationStatus.NO_DATA.value,
                provider="MockLocationProvider",
                is_stale=False,
                details="Location signal unavailable",
            )
        else:
            return DeviceLocationFix(
                status=FixStatus.ERROR,
                windows_status=WindowsLocationStatus.ERROR.value,
                provider="MockLocationProvider",
                is_stale=False,
                details=self.details or "Mock provider simulated error",
            )

    async def check_provider_status(self) -> str:
        return self.windows_status
