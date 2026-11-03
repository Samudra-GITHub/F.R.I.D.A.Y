"""Upcoming orbital launches from The Space Devs' Launch Library 2 (free tier: 15 req/hour)."""

from typing import Any, Dict, List, Optional

import httpx

from schemas.contracts import LaunchesResponse, LaunchRecord, ProviderStatus
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.feed import cached_fetch, raise_for_upstream

PROVIDER = "Launch Library 2"
ATTRIBUTION = "Launch data: The Space Devs, Launch Library 2"


def _float(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def parse_launch(item: Dict[str, Any]) -> Optional[LaunchRecord]:
    if not item.get("id") or not item.get("name"):
        return None
    pad = item.get("pad") or {}
    lat, lng = _float(pad.get("latitude")), _float(pad.get("longitude"))
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        lat = lng = None
    status = item.get("status") or {}
    mission = item.get("mission") or {}
    orbit = mission.get("orbit") or {}
    rocket = ((item.get("rocket") or {}).get("configuration") or {})
    precision = item.get("net_precision") or {}
    slug = item.get("slug")
    return LaunchRecord(
        id=str(item["id"]),
        name=str(item["name"]),
        net_utc=item.get("net"),
        net_precision=precision.get("name"),
        window_start_utc=item.get("window_start"),
        window_end_utc=item.get("window_end"),
        status=status.get("name"),
        status_abbrev=status.get("abbrev"),
        provider_name=(item.get("launch_service_provider") or {}).get("name"),
        rocket=rocket.get("full_name") or rocket.get("name"),
        mission_name=mission.get("name"),
        mission_description=mission.get("description"),
        orbit=orbit.get("name"),
        pad_name=pad.get("name"),
        location_name=(pad.get("location") or {}).get("name"),
        latitude=lat,
        longitude=lng,
        probability=item.get("probability") if isinstance(item.get("probability"), int) else None,
        webcast_live=bool(item.get("webcast_live")),
        # Space Launch Now is The Space Devs' public site for the same records.
        url=f"https://spacelaunchnow.me/launch/{slug}" if slug else None,
    )


class LaunchProvider:
    def __init__(self, cache: Optional[WorldDataCache] = None, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.cache = cache or WorldDataCache()
        self.transport = transport

    async def get_launches(self, limit: int = 25) -> LaunchesResponse:
        async def fetch() -> List[LaunchRecord]:
            async with httpx.AsyncClient(transport=self.transport, timeout=settings.world_http_timeout_seconds) as client:
                resp = await client.get(
                    settings.launch_library_url,
                    params={"limit": 30, "hide_recent_previous": "true"},
                    headers={"User-Agent": settings.osm_user_agent, "Accept": "application/json"},
                )
            raise_for_upstream(resp, "Launch Library 2")
            out = [parse_launch(i) for i in resp.json().get("results") or []]
            return [r for r in out if r]

        result = await cached_fetch(self.cache, "ll2_upcoming", settings.launches_cache_ttl_seconds, fetch, "Launch Library 2")
        launches = (result.data or [])[: max(1, min(limit, 30))]
        status = result.status
        if result.data is not None and not launches:
            status = ProviderStatus.EMPTY
        return LaunchesResponse(
            status=status,
            provider=PROVIDER,
            attribution=ATTRIBUTION,
            retrieved_at=result.retrieved_at,
            is_stale=result.is_stale,
            details=result.details,
            count=len(launches),
            launches=launches,
        )
