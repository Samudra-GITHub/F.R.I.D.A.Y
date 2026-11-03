"""Active fire detections from NASA FIRMS (needs a free MAP_KEY in FIRMS_MAP_KEY).

Without a key the provider reports ``not_configured`` and returns nothing; it never
substitutes another source. The global 24-hour file can hold tens of thousands of
detections, so only the strongest (by fire radiative power) are returned for display.
"""

import csv
import io
from typing import List, Optional

import httpx

from schemas.contracts import FireRecord, FiresResponse, ProviderStatus
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.feed import UpstreamError, cached_fetch, raise_for_upstream, utc_now_iso

PROVIDER = "NASA FIRMS"
ATTRIBUTION = "Fire detections: NASA FIRMS (LANCE), VIIRS/MODIS near-real-time"


def _num(v: Optional[str]) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def parse_firms_csv(text: str) -> List[FireRecord]:
    if text.lstrip().lower().startswith(("invalid", "error")):
        raise UpstreamError(ProviderStatus.PROVIDER_ERROR, f"FIRMS rejected the request: {text.strip()[:120]}")
    out: List[FireRecord] = []
    for row in csv.DictReader(io.StringIO(text)):
        lat, lng = _num(row.get("latitude")), _num(row.get("longitude"))
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        date, hhmm = row.get("acq_date"), (row.get("acq_time") or "").zfill(4)
        out.append(
            FireRecord(
                latitude=lat,
                longitude=lng,
                brightness_k=_num(row.get("bright_ti4") or row.get("brightness")),
                frp_mw=_num(row.get("frp")),
                confidence=row.get("confidence"),
                acquired_utc=f"{date}T{hhmm[:2]}:{hhmm[2:]}:00Z" if date else None,
                satellite=row.get("satellite"),
                daynight=row.get("daynight"),
            )
        )
    return out


class FireProvider:
    def __init__(self, cache: Optional[WorldDataCache] = None, transport: Optional[httpx.AsyncBaseTransport] = None, map_key: Optional[str] = None) -> None:
        self.cache = cache or WorldDataCache()
        self.transport = transport
        self.map_key = map_key if map_key is not None else settings.firms_map_key

    async def get_fires(self, limit: Optional[int] = None) -> FiresResponse:
        base = dict(provider=PROVIDER, attribution=ATTRIBUTION)
        if not self.map_key:
            return FiresResponse(
                status=ProviderStatus.NOT_CONFIGURED,
                retrieved_at=utc_now_iso(),
                details="Set FIRMS_MAP_KEY (free from NASA FIRMS) to enable active-fire detections.",
                **base,
            )

        async def fetch() -> List[FireRecord]:
            url = f"{settings.firms_url}/{self.map_key}/{settings.firms_source}/world/1"
            async with httpx.AsyncClient(transport=self.transport, timeout=max(30.0, settings.world_http_timeout_seconds)) as client:
                resp = await client.get(url, headers={"User-Agent": settings.osm_user_agent})
            raise_for_upstream(resp, "NASA FIRMS")
            return parse_firms_csv(resp.text)

        result = await cached_fetch(self.cache, "firms_world_24h", settings.firms_cache_ttl_seconds, fetch, "NASA FIRMS")
        all_fires = result.data or []
        cap = min(limit or settings.firms_max_points, settings.firms_max_points)
        strongest = sorted(all_fires, key=lambda f: f.frp_mw or 0.0, reverse=True)[:cap]
        status = result.status
        if result.data is not None and not strongest:
            status = ProviderStatus.EMPTY
        return FiresResponse(
            status=status,
            retrieved_at=result.retrieved_at,
            is_stale=result.is_stale,
            details=result.details
            or (f"Showing the {len(strongest)} strongest of {len(all_fires)} detections." if len(all_fires) > len(strongest) else None),
            count=len(strongest),
            total_detections=len(all_fires),
            fires=strongest,
            **base,
        )
