"""World Intelligence Service coordinator for W.E.D.N.E.S.D.A.Y. Phase 3.

Coordinates external providers with caching, error isolation, freshness tracking,
and status aggregation.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import httpx

from schemas.contracts import (
    DisastersResponse,
    EarthquakesResponse,
    NaturalEventsResponse,
    NewsResponse,
    ProviderHealth,
    ProviderStatus,
    WeatherResponse,
    WorldStatusResponse,
)
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.gdacs_disasters import GDACSDisasterProvider
from backend.friday.world.nasa_eonet import NASAEonetProvider
from backend.friday.world.news_rss import NewsRSSProvider
from backend.friday.world.open_meteo import OpenMeteoWeatherProvider
from backend.friday.world.usgs_earthquakes import USGSEarthquakeProvider


class WorldIntelligenceService:
    """Unified service for real-time geospatial and planetary intelligence."""

    def __init__(
        self,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        cache: Optional[WorldDataCache] = None,
    ) -> None:
        self.cache = cache or WorldDataCache()
        self.usgs_provider = USGSEarthquakeProvider(cache=self.cache, transport=transport)
        self.weather_provider = OpenMeteoWeatherProvider(cache=self.cache, transport=transport)
        self.eonet_provider = NASAEonetProvider(cache=self.cache, transport=transport)
        self.gdacs_provider = GDACSDisasterProvider(cache=self.cache, transport=transport)
        self.news_provider = NewsRSSProvider(cache=self.cache, transport=transport)

    async def get_earthquakes(
        self,
        min_magnitude: float = 0.0,
        limit: int = 50,
        force_refresh: bool = False,
    ) -> EarthquakesResponse:
        """Query recent earthquakes from USGS."""
        return await self.usgs_provider.get_earthquakes(
            min_magnitude=min_magnitude,
            limit=limit,
            force_refresh=force_refresh,
        )

    async def get_weather(
        self,
        latitude: float,
        longitude: float,
        location_name: Optional[str] = None,
        force_refresh: bool = False,
    ) -> WeatherResponse:
        """Query current weather telemetry from Open-Meteo."""
        return await self.weather_provider.get_weather(
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            force_refresh=force_refresh,
        )

    async def get_events(
        self,
        days: Optional[int] = None,
        category: Optional[str] = None,
        limit: int = 50,
        force_refresh: bool = False,
    ) -> NaturalEventsResponse:
        """Query active natural events from NASA EONET."""
        return await self.eonet_provider.get_events(
            days=days,
            category=category,
            limit=limit,
            force_refresh=force_refresh,
        )

    async def get_disasters(
        self,
        alert_level: Optional[str] = None,
        limit: int = 50,
        force_refresh: bool = False,
    ) -> DisastersResponse:
        """Query active disaster alerts from GDACS."""
        return await self.gdacs_provider.get_disasters(
            alert_level=alert_level,
            limit=limit,
            force_refresh=force_refresh,
        )

    async def get_news(
        self,
        limit: int = 30,
        force_refresh: bool = False,
    ) -> NewsResponse:
        """Query verified world news headlines from RSS allowlist."""
        return await self.news_provider.get_news(
            limit=limit,
            force_refresh=force_refresh,
        )

    async def get_status(self) -> WorldStatusResponse:
        """Aggregate health, cache state, and freshness across all providers."""
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        providers: Dict[str, ProviderHealth] = {}

        # 1. USGS Status
        usgs_snap = self.cache.get_last_successful("usgs_earthquakes_raw")
        usgs_fresh = self.cache.get("usgs_earthquakes_raw")
        providers["usgs_earthquakes"] = ProviderHealth(
            provider="USGS Earthquakes",
            status=ProviderStatus.OK if (usgs_fresh and not usgs_fresh[1]) else (
                ProviderStatus.STALE if usgs_snap else ProviderStatus.OK
            ),
            last_successful_retrieval=usgs_snap[1] if usgs_snap else None,
            is_stale=bool(usgs_fresh[1]) if usgs_fresh else bool(usgs_snap),
            cached_items_count=len(usgs_snap[0]) if usgs_snap and isinstance(usgs_snap[0], list) else 0,
        )

        # 2. NASA EONET Status
        eonet_snap = self.cache.get_last_successful(f"nasa_eonet_events_{self.eonet_provider.days}")
        eonet_fresh = self.cache.get(f"nasa_eonet_events_{self.eonet_provider.days}")
        providers["nasa_eonet"] = ProviderHealth(
            provider="NASA EONET v3",
            status=ProviderStatus.OK if (eonet_fresh and not eonet_fresh[1]) else (
                ProviderStatus.STALE if eonet_snap else ProviderStatus.OK
            ),
            last_successful_retrieval=eonet_snap[1] if eonet_snap else None,
            is_stale=bool(eonet_fresh[1]) if eonet_fresh else bool(eonet_snap),
            cached_items_count=len(eonet_snap[0]) if eonet_snap and isinstance(eonet_snap[0], list) else 0,
        )

        # 3. GDACS Status
        gdacs_snap = self.cache.get_last_successful("gdacs_disasters_raw")
        gdacs_fresh = self.cache.get("gdacs_disasters_raw")
        providers["gdacs_disasters"] = ProviderHealth(
            provider="GDACS Disasters",
            status=ProviderStatus.OK if (gdacs_fresh and not gdacs_fresh[1]) else (
                ProviderStatus.STALE if gdacs_snap else ProviderStatus.OK
            ),
            last_successful_retrieval=gdacs_snap[1] if gdacs_snap else None,
            is_stale=bool(gdacs_fresh[1]) if gdacs_fresh else bool(gdacs_snap),
            cached_items_count=len(gdacs_snap[0]) if gdacs_snap and isinstance(gdacs_snap[0], list) else 0,
        )

        # 4. Open-Meteo Weather Status
        weather_keys = [k for k in self.cache._entries.keys() if k.startswith("open_meteo_")]
        providers["open_meteo"] = ProviderHealth(
            provider="Open-Meteo Weather",
            status=ProviderStatus.OK,
            last_successful_retrieval=now_iso if weather_keys else None,
            is_stale=False,
            cached_items_count=len(weather_keys),
        )

        # 5. News RSS Status
        news_snap = self.cache.get_last_successful("world_news_rss")
        news_fresh = self.cache.get("world_news_rss")
        providers["news_rss"] = ProviderHealth(
            provider="Verified News RSS",
            status=ProviderStatus.OK if (news_fresh and not news_fresh[1]) else (
                ProviderStatus.STALE if news_snap else ProviderStatus.OK
            ),
            last_successful_retrieval=news_snap[1] if news_snap else None,
            is_stale=bool(news_fresh[1]) if news_fresh else bool(news_snap),
            cached_items_count=len(news_snap[0]) if news_snap and isinstance(news_snap[0], list) else 0,
        )

        overall_status = "healthy"
        for p in providers.values():
            if p.status in (ProviderStatus.PROVIDER_ERROR, ProviderStatus.TIMEOUT):
                overall_status = "degraded"
                break

        return WorldStatusResponse(
            status=overall_status,
            providers=providers,
            retrieved_at=now_iso,
        )
