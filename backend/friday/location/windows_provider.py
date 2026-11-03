"""Genuine Windows Location Provider using Windows.Devices.Geolocation via WinRT."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from schemas.contracts import DeviceLocationFix, FixStatus, WindowsLocationStatus
from backend.friday.location.base import BaseLocationProvider

logger = logging.getLogger(__name__)


class WindowsLocationProvider(BaseLocationProvider):
    """Provides genuine device coordinates using Windows.Devices.Geolocation.
    
    Adheres to W.E.D.N.E.S.D.A.Y. security and privacy principles:
    - Never fabricates coordinates or addresses.
    - Accurately captures Windows permission and hardware states.
    - Avoids logging raw coordinates in plaintext log streams.
    """

    def __init__(self, script_path: Optional[Path] = None, timeout_seconds: float = 12.0) -> None:
        if script_path is None:
            self.script_path = Path(__file__).parent / "winrt_locator.ps1"
        else:
            self.script_path = Path(script_path)
        self.timeout_seconds = timeout_seconds

    async def get_current_location(self) -> DeviceLocationFix:
        """Query Windows Geolocation API via isolated PowerShell WinRT helper."""
        if not self.script_path.exists():
            return DeviceLocationFix(
                status=FixStatus.ERROR,
                windows_status=WindowsLocationStatus.ERROR.value,
                details=f"WinRT locator script not found at {self.script_path.name}",
            )

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            "-TimeoutMs",
            str(int((self.timeout_seconds - 2) * 1000)),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Windows location provider query timed out")
            return DeviceLocationFix(
                status=FixStatus.UNAVAILABLE,
                windows_status=WindowsLocationStatus.TIMEOUT.value,
                details=f"Location query timed out after {self.timeout_seconds}s",
            )
        except Exception as exc:
            logger.error("Failed to execute Windows location provider: %s", exc)
            return DeviceLocationFix(
                status=FixStatus.ERROR,
                windows_status=WindowsLocationStatus.ERROR.value,
                details=f"Failed to query Windows location provider: {exc}",
            )

        raw_output = stdout.decode("utf-8", errors="replace").strip()
        if not raw_output:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return DeviceLocationFix(
                status=FixStatus.ERROR,
                windows_status=WindowsLocationStatus.ERROR.value,
                details=f"Empty response from location provider: {err_msg or 'Unknown error'}",
            )

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as jde:
            return DeviceLocationFix(
                status=FixStatus.ERROR,
                windows_status=WindowsLocationStatus.ERROR.value,
                details=f"Failed to parse location JSON output: {jde}",
            )

        is_ok = bool(data.get("ok"))
        win_status = str(data.get("status", "Unknown"))
        err_detail = data.get("error")

        if is_ok and data.get("latitude") is not None and data.get("longitude") is not None:
            ts = data.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return DeviceLocationFix(
                latitude=float(data["latitude"]),
                longitude=float(data["longitude"]),
                accuracy_m=float(data["accuracy"]) if data.get("accuracy") is not None else None,
                timestamp_utc=ts,
                status=FixStatus.FRESH,
                windows_status=win_status,
                provider="Windows.Devices.Geolocation",
                is_stale=False,
                details="Fix acquired from Windows.Devices.Geolocation",
            )

        # Handle specific Windows non-OK status codes accurately
        if win_status == WindowsLocationStatus.DISABLED.value:
            return DeviceLocationFix(
                status=FixStatus.DENIED,
                windows_status=win_status,
                details="Windows Location Services disabled in Windows Settings (Privacy & security > Location)",
            )
        elif win_status == WindowsLocationStatus.NOT_AVAILABLE.value:
            return DeviceLocationFix(
                status=FixStatus.UNAVAILABLE,
                windows_status=win_status,
                details="Location platform or sensor is not available on this Windows device",
            )
        elif win_status == WindowsLocationStatus.NO_DATA.value:
            return DeviceLocationFix(
                status=FixStatus.UNAVAILABLE,
                windows_status=win_status,
                details="No satellite or network geolocation signal available",
            )
        elif win_status == WindowsLocationStatus.TIMEOUT.value:
            return DeviceLocationFix(
                status=FixStatus.UNAVAILABLE,
                windows_status=win_status,
                details="Timed out awaiting Windows location fix",
            )
        elif win_status in (WindowsLocationStatus.INITIALIZING.value, WindowsLocationStatus.NOT_INITIALIZED.value):
            return DeviceLocationFix(
                status=FixStatus.INITIALIZING,
                windows_status=win_status,
                details="Windows location hardware initializing fix",
            )
        else:
            return DeviceLocationFix(
                status=FixStatus.ERROR,
                windows_status=win_status,
                details=err_detail or "Unknown Windows location provider failure",
            )

    async def check_provider_status(self) -> str:
        """Inspect platform status without waiting for a full fix."""
        fix = await self.get_current_location()
        return fix.windows_status or fix.status.value
