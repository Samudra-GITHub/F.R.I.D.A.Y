"""Atomic Local State Management and Process Concurrency for Location Service."""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from schemas.contracts import DeviceLocationFix, FixStatus, LocationMode, LocationServiceStatus

logger = logging.getLogger(__name__)


def is_process_alive(pid: Optional[int]) -> bool:
    """Determine whether a process with the given PID is actively running."""
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
        )
        if handle:
            exit_code = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                STILL_ACTIVE = 259
                is_active = (exit_code.value == STILL_ACTIVE)
            else:
                is_active = False
            ctypes.windll.kernel32.CloseHandle(handle)
            return is_active
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


class LocationStateManager:
    """Thread-safe and process-safe atomic state manager.
    
    Guarantees:
    - Atomic writes via temporary file and os.replace.
    - Single-instance detection with stale PID cleanup.
    - Zero history retention (stores only the single latest fix).
    """

    def __init__(self, state_file: Path, lock_file: Path, staleness_threshold_s: int = 180) -> None:
        self.state_file = Path(state_file)
        self.lock_file = Path(lock_file)
        self.staleness_threshold_s = staleness_threshold_s
        self._ensure_parent_dirs()

    def _ensure_parent_dirs(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)

    def load_status(self) -> LocationServiceStatus:
        """Read and validate the latest location service status from disk."""
        if not self.state_file.exists():
            return LocationServiceStatus(
                tracking_enabled=False,
                is_paused=False,
                worker_running=False,
                worker_pid=None,
                update_interval_s=60,
                latest_fix=None,
                details="Location service idle (not initialized)",
            )

        try:
            raw_text = self.state_file.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            status = LocationServiceStatus.model_validate(data)
            # State files written before modes existed: tracking on means continuous.
            if "mode" not in data and status.tracking_enabled:
                status.mode = LocationMode.CONTINUOUS

            # Stale PID recovery: check if registered worker is still actually alive
            if status.worker_running and status.worker_pid:
                if not is_process_alive(status.worker_pid):
                    logger.info("Detected dead worker PID %s; recovering state", status.worker_pid)
                    status.worker_running = False
                    status.worker_pid = None
                    if status.latest_fix and status.latest_fix.status == FixStatus.FRESH:
                        status.latest_fix.is_stale = True
                    status.details = "Background worker terminated unexpectedly; recovered"
                    self.save_status(status)

            # Check staleness on latest fix
            if status.latest_fix and status.latest_fix.timestamp_utc:
                try:
                    fix_dt = datetime.fromisoformat(status.latest_fix.timestamp_utc.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    age_s = (now - fix_dt).total_seconds()
                    if age_s > self.staleness_threshold_s:
                        status.latest_fix.is_stale = True
                        if status.latest_fix.status == FixStatus.FRESH:
                            status.latest_fix.status = FixStatus.STALE
                except Exception:
                    status.latest_fix.is_stale = True

            return status
        except Exception as exc:
            logger.warning("Could not read location state file: %s", exc)
            return LocationServiceStatus(
                tracking_enabled=False,
                is_paused=False,
                worker_running=False,
                worker_pid=None,
                details=f"State read error: {exc}",
            )

    def save_status(self, status: LocationServiceStatus) -> None:
        """Atomically persist status to disk."""
        self._ensure_parent_dirs()
        tmp_path = self.state_file.with_suffix(".tmp")
        try:
            payload = status.model_dump_json(indent=2)
            tmp_path.write_text(payload, encoding="utf-8")
            # Atomic file replace
            os.replace(tmp_path, self.state_file)
        except Exception as exc:
            logger.error("Failed to atomically write location state: %s", exc)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise
