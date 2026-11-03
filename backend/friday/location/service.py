"""Location Service Orchestrator for W.E.D.N.E.S.D.A.Y.

Manages background worker process lifecycle, user consent, and state synchronization.
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from schemas.contracts import DeviceLocationFix, FixStatus, LocationMode, LocationServiceStatus
from backend.friday.config import settings
from backend.friday.location.base import BaseLocationProvider
from backend.friday.location.windows_provider import WindowsLocationProvider
from backend.friday.location.state import LocationStateManager, is_process_alive

logger = logging.getLogger(__name__)


class LocationService:
    """High-level service interface for Windows Location Intelligence.
    
    Guarantees:
    - Never enables tracking without explicit user invocation.
    - Prevents spawning duplicate background processes.
    - Cleans up background workers upon disabling.
    - Loopback only; zero third-party transmission.
    """

    def __init__(
        self,
        provider: Optional[BaseLocationProvider] = None,
        state_manager: Optional[LocationStateManager] = None,
    ) -> None:
        self.provider = provider or WindowsLocationProvider()
        self.state_manager = state_manager or LocationStateManager(
            state_file=settings.location_state_file,
            lock_file=settings.location_lock_file,
            staleness_threshold_s=settings.location_staleness_threshold_seconds,
        )

    def get_status(self) -> LocationServiceStatus:
        """Return current status of the location service and latest fix."""
        return self.state_manager.load_status()

    async def poll_once(self) -> DeviceLocationFix:
        """Acquire a single ad-hoc location fix without continuous background polling."""
        fix = await self.provider.get_current_location()
        status = self.state_manager.load_status()
        status.latest_fix = fix
        status.details = "One-time ad-hoc fix acquired"
        self.state_manager.save_status(status)
        return fix

    def enable_tracking(self, interval_s: Optional[int] = None) -> LocationServiceStatus:
        """Enable continuous background location tracking after explicit user consent."""
        poll_interval = interval_s or settings.location_default_interval_seconds
        if poll_interval < settings.location_min_interval_seconds:
            poll_interval = settings.location_min_interval_seconds

        status = self.state_manager.load_status()
        status.mode = LocationMode.CONTINUOUS
        status.tracking_enabled = True
        status.is_paused = False
        status.update_interval_s = poll_interval

        # Check if worker is already alive
        if status.worker_running and status.worker_pid and is_process_alive(status.worker_pid):
            status.details = f"Tracking enabled; worker already active (PID {status.worker_pid})"
            self.state_manager.save_status(status)
            return status

        # Launch detached background worker
        status.details = f"Starting background tracking worker (interval {poll_interval}s)"
        self.state_manager.save_status(status)
        launcher_pid = self._spawn_background_worker(poll_interval)

        # Allow worker a moment to acquire lock and register its true runtime PID
        import time
        for _ in range(15):
            time.sleep(0.1)
            refreshed = self.state_manager.load_status()
            if refreshed.worker_running and refreshed.worker_pid:
                return refreshed

        status.worker_pid = launcher_pid
        status.worker_running = launcher_pid is not None
        status.details = f"Background tracking active (PID {launcher_pid}, interval {poll_interval}s)"
        self.state_manager.save_status(status)
        return status

    def pause_tracking(self) -> LocationServiceStatus:
        """Temporarily suspend location polling without killing the worker."""
        status = self.state_manager.load_status()
        status.is_paused = True
        status.details = "Location tracking paused by user"
        self.state_manager.save_status(status)
        return status

    def resume_tracking(self) -> LocationServiceStatus:
        """Resume location polling from paused state."""
        status = self.state_manager.load_status()
        status.is_paused = False
        status.details = "Location tracking resumed by user"
        self.state_manager.save_status(status)
        # If worker died while paused, restart it
        if not status.worker_running or not is_process_alive(status.worker_pid):
            self.enable_tracking(status.update_interval_s)
            status = self.state_manager.load_status()
        return status

    def disable_tracking(self) -> LocationServiceStatus:
        """Disable tracking and stop the background worker process."""
        return self.set_mode(LocationMode.OFF)

    def set_mode(self, mode: LocationMode, interval_s: Optional[int] = None) -> LocationServiceStatus:
        """Apply the user's chosen mode. OFF also forgets the stored position."""
        if mode == LocationMode.CONTINUOUS:
            return self.enable_tracking(interval_s)
        status = self._stop_worker(self.state_manager.load_status())
        status.mode = mode
        status.tracking_enabled = False
        status.is_paused = False
        if mode == LocationMode.OFF:
            status.latest_fix = None
            status.details = "Location is off; the stored position was cleared"
        else:
            status.details = "Location is read only when needed; no background tracking"
        self.state_manager.save_status(status)
        return status

    def clear_location(self) -> LocationServiceStatus:
        """Forget the stored position. Only the latest fix is ever kept, so this clears all of it."""
        status = self.state_manager.load_status()
        status.latest_fix = None
        status.details = "Stored position cleared"
        self.state_manager.save_status(status)
        return status

    def resume_if_opted_in(self) -> LocationServiceStatus:
        """On app start, restart continuous tracking only if the user chose it and hasn't paused it."""
        status = self.state_manager.load_status()
        if status.mode != LocationMode.CONTINUOUS or not status.tracking_enabled or status.is_paused:
            return status
        # A worker left by a previous run belongs to a dead parent and is about to exit.
        status = self._stop_worker(status)
        self.state_manager.save_status(status)
        return self.enable_tracking(status.update_interval_s)

    def stop_worker_for_shutdown(self) -> None:
        """End the worker with the app, keeping the user's preference, so tracking never runs unseen."""
        status = self.state_manager.load_status()
        if not status.worker_running and not status.worker_pid:
            return
        status = self._stop_worker(status)
        status.details = "Tracking stopped because the app closed; it resumes when the app starts"
        self.state_manager.save_status(status)

    def _stop_worker(self, status: LocationServiceStatus) -> LocationServiceStatus:
        pid = status.worker_pid
        if pid and is_process_alive(pid):
            self._terminate_process(pid)
        status.worker_running = False
        status.worker_pid = None
        return status

    def _spawn_background_worker(self, interval_s: int) -> Optional[int]:
        """Spawn the daemon as a detached background process."""
        project_root = Path(__file__).resolve().parents[3]
        env = os.environ.copy()
        python_path = str(project_root)
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = python_path

        cmd = [
            sys.executable,
            "-m",
            "backend.friday.location.daemon",
            "--interval",
            str(interval_s),
            "--parent-pid",
            str(os.getpid()),
        ]

        log_path = settings.workspace_root / "location_daemon.log"
        settings.workspace_root.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")

        try:
            if os.name == "nt":
                # Windows flags for fully detached background process without console window
                CREATE_NO_WINDOW = 0x08000000
                DETACHED_PROCESS = 0x00000008
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(project_root),
                    env=env,
                    creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                    close_fds=True,
                    stdout=log_file,
                    stderr=log_file,
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(project_root),
                    env=env,
                    start_new_session=True,
                    close_fds=True,
                    stdout=log_file,
                    stderr=log_file,
                )
            return proc.pid
        except Exception as exc:
            logger.error("Failed to spawn background location daemon: %s", exc)
            return None

    def _terminate_process(self, pid: int) -> None:
        """Gracefully terminate a running worker process."""
        try:
            if os.name == "nt":
                # On Windows, try taskkill or SIGTERM
                os.kill(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
