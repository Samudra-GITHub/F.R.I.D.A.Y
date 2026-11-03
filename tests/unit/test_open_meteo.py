"""Unit tests for OpenMeteoWeatherProvider with mocked HTTP transport."""

import httpx
import pytest

from schemas.contracts import ProviderStatus
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.open_meteo import OpenMeteoWeatherProvider, translate_wmo_code

SAMPLE_OPEN_METEO_JSON = {
    "latitude": 51.5,
    "longitude": -0.12,
    "generationtime_ms": 0.12,
    "utc_offset_seconds": 0,
    "timezone": "GMT",
    "elevation": 25.0,
    "current": {
        "time": "2026-10-27T12:00",
        "interval": 900,
        "temperature_2m": 16.4,
        "relative_humidity_2m": 72.0,
        "apparent_temperature": 15.8,
        "precipitation": 0.2,
        "weather_code": 61,
        "wind_speed_10m": 18.5,
        "wind_direction_10m": 240.0,
        "is_day": 1,
    },
    "daily": {
        "time": ["2026-10-27", "2026-10-28", "2026-10-29"],
        "weather_code": [61, 3, 0],
        "temperature_2m_max": [18.2, 17.0, 19.5],
        "temperature_2m_min": [12.1, 10.4, 9.8],
    },
}


def test_wmo_code_translation():
    assert translate_wmo_code(0) == "Clear sky"
    assert translate_wmo_code(61) == "Slight rain"
    assert translate_wmo_code(95) == "Thunderstorm"
    assert "999" in translate_wmo_code(999)


@pytest.mark.asyncio
async def test_open_meteo_weather_lookup():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "latitude=51.5" in str(request.url)
        assert "longitude=-0.12" in str(request.url)
        return httpx.Response(200, json=SAMPLE_OPEN_METEO_JSON)

    transport = httpx.MockTransport(handler)
    provider = OpenMeteoWeatherProvider(transport=transport, cache=WorldDataCache())

    res = await provider.get_weather(latitude=51.5007, longitude=-0.1246, location_name="London")
    assert res.status == ProviderStatus.OK
    assert res.weather is not None
    w = res.weather
    assert w.temperature_c == 16.4
    assert w.feels_like_c == 15.8
    assert w.condition == "Slight rain"
    assert w.weather_code == 61
    assert w.humidity_percent == 72.0
    assert w.wind_speed_kmh == 18.5
    assert w.location_name == "London"
    assert w.is_day is True
    assert len(w.daily_forecasts) == 3
    assert "High 18.2°C" in (w.forecast_summary or "")


@pytest.mark.asyncio
async def test_open_meteo_invalid_coords_and_fallback():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=SAMPLE_OPEN_METEO_JSON)
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    cache = WorldDataCache()
    provider = OpenMeteoWeatherProvider(transport=transport, cache=cache)

    # 1. Invalid coordinates rejected
    bad_res = await provider.get_weather(latitude=999.0, longitude=0.0)
    assert bad_res.status == ProviderStatus.PROVIDER_ERROR
    assert "Invalid coordinates" in (bad_res.details or "")

    # 2. Success populates cache
    good_res = await provider.get_weather(latitude=51.5, longitude=-0.12)
    assert good_res.status == ProviderStatus.OK

    # 3. 500 server error falls back to stale cache
    stale_res = await provider.get_weather(latitude=51.5, longitude=-0.12, force_refresh=True)
    assert stale_res.status == ProviderStatus.STALE
    assert stale_res.is_stale is True
    assert stale_res.weather is not None
