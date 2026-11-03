"""Unit tests for LocationStateManager, process isolation, and daemon mechanics."""

import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from schemas.contracts import DeviceLocationFix, FixStatus, LocationServiceStatus
from backend.friday.location.state import LocationStateManager, is_process_alive
from backend.friday.location.daemon import LocationDaemon
from backend.friday.location.mock_provider import MockLocationProvider


def test_atomic_state_save_and_load(tmp_path: Path):
    state_file = tmp_path / "test_state.json"
    lock_file = tmp_path / "test.lock"
    manager = LocationStateManager(state_file=state_file, lock_file=lock_file)

    # Initial load of empty state
    initial = manager.load_status()
    assert initial.tracking_enabled is False
    assert initial.worker_running is False
    assert initial.latest_fix is None

    # Save an active status
    fix = DeviceLocationFix(
        latitude=40.7128,
        longitude=-74.0060,
        accuracy_m=10.0,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        status=FixStatus.FRESH,
    )
    status_to_save = LocationServiceStatus(
        tracking_enabled=True,
        is_paused=False,
        worker_running=True,
        worker_pid=os.getpid(),
        latest_fix=fix,
    )
    manager.save_status(status_to_save)

    loaded = manager.load_status()
    assert loaded.tracking_enabled is True
    assert loaded.worker_running is True
    assert loaded.worker_pid == os.getpid()
    assert loaded.latest_fix is not None
    assert loaded.latest_fix.latitude == 40.7128


def test_stale_pid_recovery(tmp_path: Path):
    state_file = tmp_path / "test_state.json"
    lock_file = tmp_path / "test.lock"
    manager = LocationStateManager(state_file=state_file, lock_file=lock_file)

    # Write a status with a non-existent PID (e.g. 9999999)
    status_to_save = LocationServiceStatus(
        tracking_enabled=True,
        is_paused=False,
        worker_running=True,
        worker_pid=9999999,
        details="Worker running with dead pid",
    )
    manager.save_status(status_to_save)

    # When loaded, manager detects PID 9999999 is dead and cleans up worker state
    loaded = manager.load_status()
    assert loaded.worker_running is False
    assert loaded.worker_pid is None
    assert "terminated unexpectedly" in (loaded.details or "")


def test_is_process_alive():
    current_pid = os.getpid()
    assert is_process_alive(current_pid) is True
    assert is_process_alive(None) is False
    assert is_process_alive(9999999) is False


@pytest.mark.asyncio
async def test_daemon_single_iteration_with_mock_provider(tmp_path: Path):
    state_file = tmp_path / "daemon_state.json"
    lock_file = tmp_path / "daemon.lock"
    manager = LocationStateManager(state_file=state_file, lock_file=lock_file)

    # Enable tracking in state
    manager.save_status(
        LocationServiceStatus(
            tracking_enabled=True,
            is_paused=False,
        )
    )

    mock_prov = MockLocationProvider(status=FixStatus.FRESH, latitude=12.9716, longitude=77.5946)
    daemon = LocationDaemon(provider=mock_prov, state_manager=manager, interval_s=1)

    # Run for a brief moment and stop
    import asyncio
    run_task = asyncio.create_task(daemon.run())
    await asyncio.sleep(0.2)
    daemon.stop()
    await run_task

    status = manager.load_status()
    assert status.latest_fix is not None
    assert status.latest_fix.status == FixStatus.FRESH
    assert status.latest_fix.latitude == 12.9716
    assert status.worker_running is False  # Cleaned up on exit
