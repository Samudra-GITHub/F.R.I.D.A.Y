"""Open-Meteo atmospheric weather provider.

Fetches current weather telemetry and forecasts from the free Open-Meteo API.
Implements bounded coordinate caching, WMO weather code translation, and error fallback.
Attribution: Weather data by Open-Meteo.com (CC BY 4.0).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from schemas.contracts import ProviderStatus, WeatherConditionRecord, WeatherResponse
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache

logger = logging.getLogger(__name__)

# WMO Weather Interpretation Codes (WW)
WMO_CODE_MAP: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def translate_wmo_code(code: int) -> str:
    """Translate numerical WMO code into human-readable description."""
    return WMO_CODE_MAP.get(code, f"Weather code {code}")


class OpenMeteoWeatherProvider:
    """Atmospheric weather provider using Open-Meteo API."""

    def __init__(
        self,
        cache: Optional[WorldDataCache] = None,
        forecast_url: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.cache = cache or WorldDataCache()
        self.forecast_url = forecast_url or settings.open_meteo_forecast_url
        self.cache_ttl = cache_ttl_seconds if cache_ttl_seconds is not None else settings.open_meteo_cache_ttl_seconds
        self.timeout = timeout_seconds if timeout_seconds is not None else settings.world_http_timeout_seconds
        self.transport = transport

    def _cache_key(self, lat: float, lng: float) -> str:
        """Construct bounded cache key with coordinates rounded to 2 decimal places (~1.1 km)."""
        return f"open_meteo_{round(lat, 2)}_{round(lng, 2)}"

    async def get_weather(
        self,
        latitude: float,
        longitude: float,
        location_name: Optional[str] = None,
        force_refresh: bool = False,
    ) -> WeatherResponse:
        """Fetch current weather for given coordinates."""
        # Validate coordinates
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            return WeatherResponse(
                status=ProviderStatus.PROVIDER_ERROR,
                retrieved_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                details=f"Invalid coordinates: ({latitude}, {longitude})",
            )

        cache_key = self._cache_key(latitude, longitude)

        # Check cache
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                record, is_stale, retrieved_at = cached
                if location_name and not record.location_name:
                    record.location_name = location_name
                return WeatherResponse(
                    status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                    weather=record,
                    retrieved_at=retrieved_at,
                    is_stale=is_stale,
                )

        lock = await self.cache.get_lock(cache_key)
        async with lock:
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached:
                    record, is_stale, retrieved_at = cached
                    if location_name and not record.location_name:
                        record.location_name = location_name
                    return WeatherResponse(
                        status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                        weather=record,
                        retrieved_at=retrieved_at,
                        is_stale=is_stale,
                    )

            params = {
                "latitude": round(latitude, 4),
                "longitude": round(longitude, 4),
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "precipitation,weather_code,wind_speed_10m,wind_direction_10m,is_day"
                ),
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
                "forecast_days": 3,
            }

            headers = {"User-Agent": settings.osm_user_agent, "Accept": "application/json"}

            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                    resp = await client.get(self.forecast_url, params=params, headers=headers)

                if resp.status_code == 429:
                    logger.warning("Open-Meteo rate limit encountered")
                    return self._fallback_or_error(cache_key, ProviderStatus.RATE_LIMITED, "Open-Meteo rate limit reached")

                if resp.status_code >= 500:
                    logger.warning(f"Open-Meteo server error: HTTP {resp.status_code}")
                    return self._fallback_or_error(cache_key, ProviderStatus.PROVIDER_ERROR, f"Open-Meteo server error HTTP {resp.status_code}")

                resp.raise_for_status()
                data = resp.json()

                current = data.get("current", {})
                daily = data.get("daily", {})

                w_code = int(current.get("weather_code", 0))
                condition_text = translate_wmo_code(w_code)

                # Format daily forecast summary
                daily_forecasts: List[Dict[str, Any]] = []
                days = daily.get("time", [])
                max_temps = daily.get("temperature_2m_max", [])
                min_temps = daily.get("temperature_2m_min", [])
                daily_codes = daily.get("weather_code", [])

                for i in range(len(days)):
                    daily_forecasts.append({
                        "date": days[i],
                        "max_temp_c": max_temps[i] if i < len(max_temps) else None,
                        "min_temp_c": min_temps[i] if i < len(min_temps) else None,
                        "condition": translate_wmo_code(daily_codes[i]) if i < len(daily_codes) else "Unknown",
                    })

                summary_parts: List[str] = [condition_text]
                if daily_forecasts:
                    today = daily_forecasts[0]
                    if today.get("max_temp_c") is not None and today.get("min_temp_c") is not None:
                        summary_parts.append(f"High {today['max_temp_c']}°C / Low {today['min_temp_c']}°C")

                forecast_summary = " • ".join(summary_parts)

                record = WeatherConditionRecord(
                    latitude=round(latitude, 4),
                    longitude=round(longitude, 4),
                    location_name=location_name,
                    temperature_c=float(current.get("temperature_2m", 0.0)),
                    feels_like_c=float(current.get("apparent_temperature", current.get("temperature_2m", 0.0))),
                    condition=condition_text,
                    weather_code=w_code,
                    humidity_percent=float(current.get("relative_humidity_2m", 0.0)),
                    wind_speed_kmh=float(current.get("wind_speed_10m", 0.0)),
                    wind_direction_deg=float(current.get("wind_direction_10m", 0.0)),
                    precipitation_mm=float(current.get("precipitation", 0.0)),
                    is_day=bool(current.get("is_day", 1) == 1),
                    forecast_summary=forecast_summary,
                    daily_forecasts=daily_forecasts,
                    source_time_utc=str(current.get("time", "")),
                )

                retrieved_at = self.cache.set(cache_key, record, self.cache_ttl)

                return WeatherResponse(
                    status=ProviderStatus.OK,
                    weather=record,
                    retrieved_at=retrieved_at,
                    is_stale=False,
                )

            except httpx.TimeoutException:
                logger.warning("Open-Meteo request timed out")
                return self._fallback_or_error(cache_key, ProviderStatus.TIMEOUT, "Request to Open-Meteo timed out")
            except Exception as exc:
                logger.error(f"Failed to fetch weather from Open-Meteo: {exc}")
                return self._fallback_or_error(cache_key, ProviderStatus.PROVIDER_ERROR, str(exc))

    def _fallback_or_error(self, cache_key: str, status: ProviderStatus, details: str) -> WeatherResponse:
        """Serve last successful snapshot if available, or error payload."""
        snapshot = self.cache.get_last_successful(cache_key)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if snapshot:
            record, retrieved_at = snapshot
            return WeatherResponse(
                status=ProviderStatus.STALE,
                weather=record,
                retrieved_at=retrieved_at,
                is_stale=True,
                details=f"Serving cached snapshot: {details}",
            )

        return WeatherResponse(
            status=status,
            weather=None,
            retrieved_at=now_iso,
            is_stale=False,
            details=details,
        )
