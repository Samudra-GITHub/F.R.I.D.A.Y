"""Location modes: what each mode does to tracking and the stored position."""

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.friday.location.daemon import distance_meters, next_poll_seconds
from backend.friday.location.service import LocationService
from backend.friday.location.state import LocationStateManager
from schemas.contracts import DeviceLocationFix, FixStatus, LocationMode


def fix(lat=22.5, lon=88.3):
    return DeviceLocationFix(latitude=lat, longitude=lon, status=FixStatus.FRESH)


@pytest.fixture
def service(tmp_path: Path):
    state = LocationStateManager(tmp_path / "state.json", tmp_path / "lock")
    svc = LocationService(provider=object(), state_manager=state)
    with patch.object(LocationService, "_spawn_background_worker", return_value=None) as spawn, patch(
        "time.sleep"
    ):
        svc.spawn = spawn
        yield svc


def stored(svc, **fields):
    status = svc.state_manager.load_status()
    for name, value in fields.items():
        setattr(status, name, value)
    svc.state_manager.save_status(status)


def test_default_mode_is_once_with_no_tracking(service):
    status = service.get_status()
    assert status.mode == LocationMode.ONCE
    assert status.tracking_enabled is False
    service.spawn.assert_not_called()


def test_continuous_starts_the_worker(service):
    status = service.set_mode(LocationMode.CONTINUOUS, 60)
    assert status.mode == LocationMode.CONTINUOUS
    assert status.tracking_enabled is True
    service.spawn.assert_called_once()


def test_off_stops_tracking_and_forgets_the_position(service):
    service.set_mode(LocationMode.CONTINUOUS, 60)
    stored(service, latest_fix=fix())
    status = service.set_mode(LocationMode.OFF)
    assert status.mode == LocationMode.OFF
    assert status.tracking_enabled is False
    assert service.get_status().latest_fix is None


def test_once_stops_tracking_but_keeps_the_last_reading(service):
    service.set_mode(LocationMode.CONTINUOUS, 60)
    stored(service, latest_fix=fix())
    status = service.set_mode(LocationMode.ONCE)
    assert status.tracking_enabled is False
    assert status.latest_fix is not None


def test_the_legacy_disable_route_means_off(service):
    service.enable_tracking(60)
    assert service.disable_tracking().mode == LocationMode.OFF


def test_clear_forgets_the_position_without_changing_the_mode(service):
    stored(service, latest_fix=fix())
    status = service.clear_location()
    assert status.latest_fix is None
    assert status.mode == LocationMode.ONCE


@pytest.mark.parametrize(
    "fields",
    [
        {"mode": LocationMode.OFF},
        {"mode": LocationMode.ONCE},
        {"mode": LocationMode.CONTINUOUS, "tracking_enabled": True, "is_paused": True},
        {"mode": LocationMode.CONTINUOUS, "tracking_enabled": False},
    ],
)
def test_startup_never_resumes_without_an_active_opt_in(service, fields):
    stored(service, **fields)
    service.resume_if_opted_in()
    service.spawn.assert_not_called()


def test_startup_resumes_continuous_tracking_the_user_chose(service):
    stored(service, mode=LocationMode.CONTINUOUS, tracking_enabled=True, update_interval_s=120)
    service.resume_if_opted_in()
    service.spawn.assert_called_once_with(120)


def test_shutdown_keeps_the_preference_but_reports_no_worker(service):
    stored(service, mode=LocationMode.CONTINUOUS, tracking_enabled=True, worker_running=True, worker_pid=None)
    service.stop_worker_for_shutdown()
    status = service.get_status()
    assert status.mode == LocationMode.CONTINUOUS
    assert status.worker_running is False


def test_state_files_from_before_modes_read_as_continuous_when_tracking(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"tracking_enabled": true}', encoding="utf-8")
    assert LocationStateManager(path, tmp_path / "lock").load_status().mode == LocationMode.CONTINUOUS


def test_distance_needs_coordinates_on_both_fixes():
    assert distance_meters(fix(lat=None), fix()) is None
    assert distance_meters(fix(), fix()) == pytest.approx(0)
    assert distance_meters(fix(0.0, 0.0), fix(0.0, 1.0)) == pytest.approx(111195, rel=0.01)


def test_polling_backs_off_only_while_still_and_never_past_freshness():
    assert next_poll_seconds(60, None, fix(), 180) == 60
    assert next_poll_seconds(60, fix(), fix(), 180) == 150
    assert next_poll_seconds(30, fix(), fix(), 180) == 90
    assert next_poll_seconds(60, fix(22.5), fix(22.6), 180) == 60
    assert next_poll_seconds(600, fix(), fix(), 180) == 600
