"""Real Windows Geolocation Integration Test.

Runs against native Windows.Devices.Geolocation WinRT API.
Privacy Protection: Never logs or prints precise coordinates.
"""

import pytest
import os
from schemas.contracts import FixStatus
from backend.friday.location.windows_provider import WindowsLocationProvider


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows OS")
@pytest.mark.asyncio
async def test_real_windows_location_provider():
    provider = WindowsLocationProvider()
    fix = await provider.get_current_location()

    # The fix must return a valid recognized status
    assert fix.status in (
        FixStatus.FRESH,
        FixStatus.DENIED,
        FixStatus.UNAVAILABLE,
        FixStatus.INITIALIZING,
    )

    if fix.status == FixStatus.FRESH:
        # Validate coordinate bounds without printing precise values
        assert fix.latitude is not None
        assert -90.0 <= fix.latitude <= 90.0
        assert fix.longitude is not None
        assert -180.0 <= fix.longitude <= 180.0
        if fix.accuracy_m is not None:
            assert fix.accuracy_m >= 0.0

        # Privacy-preserving logging
        masked_lat = f"{int(fix.latitude)}.***"
        masked_lng = f"{int(fix.longitude)}.***"
        print(f"\n[Real Windows Provider] Verified valid fix: Lat={masked_lat}, Lng={masked_lng}, Accuracy={fix.accuracy_m}m, Status={fix.status.value}")
    elif fix.status == FixStatus.DENIED:
        print("\n[Real Windows Provider] Windows Location Services are disabled in Windows Settings.")
    else:
        print(f"\n[Real Windows Provider] Sensor returned status: {fix.status.value} ({fix.details})")
