"""Standalone Background Location Worker Daemon for Windows Location Services.

Runs independently of the frontend dashboard and FastAPI server.
Operates only after explicit user consent has enabled tracking.
"""

import argparse
import asyncio
import logging
import math
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from schemas.contracts import DeviceLocationFix, FixStatus, LocationServiceStatus
from backend.friday.config import settings
from backend.friday.location.base import BaseLocationProvider
from backend.friday.location.windows_provider import WindowsLocationProvider
from backend.friday.location.state import LocationStateManager, is_process_alive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("friday.location.daemon")

STATIONARY_METERS = 50.0
STATIONARY_BACKOFF = 3
PARENT_CHECK_SECONDS = 5.0


def distance_meters(a: DeviceLocationFix, b: DeviceLocationFix) -> Optional[float]:
    """Great-circle distance between two fixes, or None if either lacks coordinates."""
    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return None
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat, dlon = lat2 - lat1, math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def next_poll_seconds(
    base_s: float,
    previous: Optional[DeviceLocationFix],
    current: Optional[DeviceLocationFix],
    staleness_s: float,
) -> float:
    """Poll less often while the device is still, but always soon enough to keep the fix fresh."""
    if previous is None or current is None:
        return base_s
    moved = distance_meters(previous, current)
    if moved is None or moved >= STATIONARY_METERS:
        return base_s
    return max(base_s, min(base_s * STATIONARY_BACKOFF, staleness_s - 30.0))


class LocationDaemon:
    """Manages continuous background device location polling."""

    def __init__(
        self,
        provider: Optional[BaseLocationProvider] = None,
        state_manager: Optional[LocationStateManager] = None,
        interval_s: Optional[int] = None,
        parent_pid: Optional[int] = None,
    ) -> None:
        self.provider = provider or WindowsLocationProvider()
        self.state_manager = state_manager or LocationStateManager(
            state_file=settings.location_state_file,
            lock_file=settings.location_lock_file,
            staleness_threshold_s=settings.location_staleness_threshold_seconds,
        )
        self.interval_s = interval_s or settings.location_default_interval_seconds
        self.parent_pid = parent_pid
        self.running = False
        self._stop_event = asyncio.Event()
        self._lock_file_handle = None

    def _acquire_instance_lock(self) -> bool:
        """Acquire non-blocking exclusive lock to enforce reliable single-instance execution."""
        try:
            self.state_manager._ensure_parent_dirs()
            self._lock_file_handle = open(self.state_manager.lock_file, "a+", encoding="utf-8")
            if os.name == "nt":
                import msvcrt
                self._lock_file_handle.seek(0)
                msvcrt.locking(self._lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            self._lock_file_handle.seek(0)
            self._lock_file_handle.truncate()
            self._lock_file_handle.write(str(os.getpid()))
            self._lock_file_handle.flush()
            return True
        except (IOError, OSError) as exc:
            logger.warning("Could not acquire instance lock: %s", exc)
            if self._lock_file_handle:
                try:
                    self._lock_file_handle.close()
                except Exception:
                    pass
                self._lock_file_handle = None
            return False

    def _release_instance_lock(self) -> None:
        """Release the instance lock file."""
        if self._lock_file_handle:
            try:
                if os.name == "nt":
                    import msvcrt
                    self._lock_file_handle.seek(0)
                    msvcrt.locking(self._lock_file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._lock_file_handle.fileno(), fcntl.LOCK_UN)
                self._lock_file_handle.close()
            except Exception:
                pass
            self._lock_file_handle = None

    def _setup_signal_handlers(self) -> None:
        """Register graceful shutdown hooks."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda s, f: self.stop())
            except (ValueError, AttributeError):
                pass

    def stop(self) -> None:
        """Signal daemon loop to stop."""
        logger.info("Stopping location daemon...")
        self.running = False
        self._stop_event.set()

    async def run(self) -> None:
        """Execute single-instance background polling loop."""
        self._setup_signal_handlers()

        # Enforce kernel-backed single-instance lock
        if not self._acquire_instance_lock():
            logger.warning("Another location daemon is already active (lock held). Exiting duplicate process.")
            return

        # Mark worker as running with its true runtime PID
        current_status = self.state_manager.load_status()
        current_status.worker_running = True
        current_status.worker_pid = os.getpid()
        current_status.update_interval_s = self.interval_s
        current_status.details = "Daemon active and polling Windows location"
        self.state_manager.save_status(current_status)
        logger.info("Location daemon started (PID %s, interval %ss)", os.getpid(), self.interval_s)

        self.running = True
        previous_fix: Optional[DeviceLocationFix] = None

        try:
            while self.running and not self._stop_event.is_set():
                wait_s = float(self.interval_s)
                # Re-read state to see if tracking was disabled or paused externally
                status = self.state_manager.load_status()

                if not status.tracking_enabled:
                    logger.info("Tracking disabled by policy/user. Daemon stopping.")
                    break

                if status.is_paused:
                    logger.debug("Location tracking paused. Sleeping interval.")
                else:
                    try:
                        logger.debug("Acquiring location fix from provider...")
                        fix = await self.provider.get_current_location()

                        # Check staleness
                        if fix.status == FixStatus.FRESH:
                            fix.is_stale = False
                        wait_s = next_poll_seconds(
                            float(self.interval_s), previous_fix, fix, self.state_manager.staleness_threshold_s
                        )
                        previous_fix = fix
                        status.latest_fix = fix
                        status.details = f"Last polled at {datetime.now(timezone.utc).strftime('%H:%M:%SZ')} ({fix.status.value})"
                        self.state_manager.save_status(status)
                        logger.info("Location fix updated (status: %s, provider: %s)", fix.status.value, fix.provider)
                    except Exception as poll_exc:
                        logger.error("Error acquiring location fix: %s", poll_exc)

                # Wait for the next poll, a stop, or the app closing.
                if await self._wait_or_exit(wait_s):
                    break
        finally:
            self._cleanup_on_exit()

    def _parent_gone(self) -> bool:
        return self.parent_pid is not None and not is_process_alive(self.parent_pid)

    async def _wait_or_exit(self, seconds: float) -> bool:
        """Sleep up to `seconds`. True means stop: signalled, or the app that started us has gone."""
        remaining = seconds
        while remaining > 0:
            if self._parent_gone():
                logger.info("The app that started this worker has closed. Stopping.")
                return True
            step = min(remaining, PARENT_CHECK_SECONDS)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=step)
                return True
            except asyncio.TimeoutError:
                remaining -= step
        return False

    def _cleanup_on_exit(self) -> None:
        """Clean up process ID and state on daemon exit."""
        logger.info("Performing daemon cleanup...")
        try:
            final_status = self.state_manager.load_status()
            if final_status.worker_pid == os.getpid():
                final_status.worker_running = False
                final_status.worker_pid = None
                final_status.details = "Daemon shut down cleanly"
                self.state_manager.save_status(final_status)
        except Exception as exc:
            logger.error("Error during daemon cleanup: %s", exc)
        finally:
            self._release_instance_lock()


def main() -> None:
    parser = argparse.ArgumentParser(description="W.E.D.N.E.S.D.A.Y. Background Location Daemon")
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.location_default_interval_seconds,
        help="Update interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=None,
        help="Stop when this process exits, so tracking never outlives the app",
    )
    args = parser.parse_args()

    daemon = LocationDaemon(interval_s=args.interval, parent_pid=args.parent_pid)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
