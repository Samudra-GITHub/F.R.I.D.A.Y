"""Unit tests for Location Provider abstraction and MockLocationProvider."""

import pytest
from datetime import datetime, timezone, timedelta

from schemas.contracts import FixStatus, WindowsLocationStatus
from backend.friday.location.mock_provider import MockLocationProvider
from backend.friday.location.base import BaseLocationProvider


@pytest.mark.asyncio
async def test_mock_provider_fresh_fix():
    provider = MockLocationProvider(
        status=FixStatus.FRESH,
        latitude=37.7749,
        longitude=-122.4194,
        accuracy_m=12.5,
        age_seconds=5,
    )
    fix = await provider.get_current_location()
    assert fix.status == FixStatus.FRESH
    assert fix.latitude == 37.7749
    assert fix.longitude == -122.4194
    assert fix.accuracy_m == 12.5
    assert fix.is_stale is False
    assert fix.provider == "MockLocationProvider"


@pytest.mark.asyncio
async def test_mock_provider_stale_fix():
    provider = MockLocationProvider(
        status=FixStatus.STALE,
        latitude=37.7749,
        longitude=-122.4194,
        accuracy_m=20.0,
        age_seconds=600,
    )
    fix = await provider.get_current_location()
    assert fix.status == FixStatus.STALE
    assert fix.is_stale is True


@pytest.mark.asyncio
async def test_mock_provider_denied_permission():
    provider = MockLocationProvider(
        status=FixStatus.DENIED,
        windows_status=WindowsLocationStatus.DISABLED.value,
    )
    fix = await provider.get_current_location()
    assert fix.status == FixStatus.DENIED
    assert fix.latitude is None
    assert fix.longitude is None
    assert "denied" in (fix.details or "").lower()


@pytest.mark.asyncio
async def test_mock_provider_unavailable_signal():
    provider = MockLocationProvider(
        status=FixStatus.UNAVAILABLE,
        windows_status=WindowsLocationStatus.NO_DATA.value,
    )
    fix = await provider.get_current_location()
    assert fix.status == FixStatus.UNAVAILABLE
    assert fix.latitude is None
    assert fix.longitude is None


@pytest.mark.asyncio
async def test_base_provider_staleness_calculation():
    now = datetime.now(timezone.utc)
    fresh_ts = (now - timedelta(seconds=30)).isoformat()
    stale_ts = (now - timedelta(seconds=400)).isoformat()

    assert BaseLocationProvider.calculate_is_stale(fresh_ts, threshold_seconds=180) is False
    assert BaseLocationProvider.calculate_is_stale(stale_ts, threshold_seconds=180) is True
    assert BaseLocationProvider.calculate_is_stale(None, threshold_seconds=180) is True
    assert BaseLocationProvider.calculate_is_stale("invalid-date", threshold_seconds=180) is True
