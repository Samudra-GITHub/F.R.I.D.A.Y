"""NASA EONET v3 natural event provider.

Fetches and normalizes active natural events (wildfires, severe storms, volcanoes, etc.)
from NASA Earth Observatory Natural Event Tracker (EONET v3).
Extracts latest observation coordinates without fabrication.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from schemas.contracts import NaturalEventRecord, NaturalEventsResponse, ProviderStatus
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache

logger = logging.getLogger(__name__)


class NASAEonetProvider:
    """Provider for real-time natural events tracked by NASA EONET v3."""

    def __init__(
        self,
        cache: Optional[WorldDataCache] = None,
        api_url: Optional[str] = None,
        days: Optional[int] = None,
        cache_ttl_seconds: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.cache = cache or WorldDataCache()
        self.api_url = api_url or settings.nasa_eonet_url
        self.days = days if days is not None else settings.nasa_eonet_days
        self.cache_ttl = cache_ttl_seconds if cache_ttl_seconds is not None else settings.nasa_eonet_cache_ttl_seconds
        self.timeout = timeout_seconds if timeout_seconds is not None else settings.world_http_timeout_seconds
        self.transport = transport

    def _extract_latest_coordinates(self, geometries: List[Dict[str, Any]]) -> Optional[Tuple[float, float, str, str]]:
        """Extract latest valid coordinates and observation timestamp from geometry list.
        
        Returns:
            Tuple of (latitude, longitude, timestamp_utc, geometry_type) or None.
        """
        if not geometries:
            return None

        # Sort by date descending if dates are provided
        sorted_geoms = sorted(
            geometries,
            key=lambda g: str(g.get("date") or ""),
            reverse=True,
        )

        for geom in sorted_geoms:
            geom_type = str(geom.get("type") or "Point")
            coords = geom.get("coordinates")
            date_str = str(geom.get("date") or "")

            if not coords:
                continue

            # Handle Point: [longitude, latitude]
            if geom_type == "Point" and isinstance(coords, (list, tuple)) and len(coords) >= 2:
                try:
                    lng = float(coords[0])
                    lat = float(coords[1])
                    if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
                        return lat, lng, date_str, geom_type
                except (ValueError, TypeError):
                    continue

            # Handle Polygon: [[[lng, lat], ...]]
            if geom_type == "Polygon" and isinstance(coords, (list, tuple)) and len(coords) > 0:
                ring = coords[0]
                if isinstance(ring, (list, tuple)) and len(ring) > 0:
                    try:
                        # Compute simple polygon centroid
                        sum_lat = 0.0
                        sum_lng = 0.0
                        valid_pts = 0
                        for pt in ring:
                            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                p_lng = float(pt[0])
                                p_lat = float(pt[1])
                                if -90.0 <= p_lat <= 90.0 and -180.0 <= p_lng <= 180.0:
                                    sum_lat += p_lat
                                    sum_lng += p_lng
                                    valid_pts += 1
                        if valid_pts > 0:
                            return sum_lat / valid_pts, sum_lng / valid_pts, date_str, geom_type
                    except Exception:
                        continue

        return None

    def _parse_event(self, item: Dict[str, Any]) -> Optional[NaturalEventRecord]:
        """Parse and normalize a single NASA EONET event object."""
        try:
            event_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not event_id or not title:
                return None

            geometries = item.get("geometry", [])
            coord_data = self._extract_latest_coordinates(geometries)
            if not coord_data:
                # Discard event without valid source-supplied coordinates
                return None

            lat, lng, obs_time, geom_type = coord_data

            categories = item.get("categories", [])
            cat_slug = categories[0].get("id", "natural_event") if categories else "natural_event"
            cat_title = categories[0].get("title", "Natural Event") if categories else "Natural Event"

            sources = item.get("sources", [])
            source_url = sources[0].get("url") if sources else None
            if not source_url:
                source_url = item.get("link")

            description = item.get("description")
            is_closed = bool(item.get("closed") is not None)

            if not obs_time:
                obs_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            return NaturalEventRecord(
                id=event_id,
                title=title,
                category=str(cat_slug),
                category_title=str(cat_title),
                latitude=round(lat, 4),
                longitude=round(lng, 4),
                timestamp_utc=obs_time,
                source_url=source_url,
                description=description,
                geometry_type=geom_type,
                is_closed=is_closed,
            )
        except Exception as exc:
            logger.debug(f"Skipping malformed EONET event: {exc}")
            return None

    async def get_events(
        self,
        days: Optional[int] = None,
        category: Optional[str] = None,
        limit: int = 50,
        force_refresh: bool = False,
    ) -> NaturalEventsResponse:
        """Fetch and return natural events from NASA EONET."""
        lookback_days = days if days is not None else self.days
        cache_key = f"nasa_eonet_events_{lookback_days}"

        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                records, is_stale, retrieved_at = cached
                filtered = self._filter_events(records, category, limit)
                return NaturalEventsResponse(
                    status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                    count=len(filtered),
                    events=filtered,
                    retrieved_at=retrieved_at,
                    is_stale=is_stale,
                )

        lock = await self.cache.get_lock(cache_key)
        async with lock:
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached:
                    records, is_stale, retrieved_at = cached
                    filtered = self._filter_events(records, category, limit)
                    return NaturalEventsResponse(
                        status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                        count=len(filtered),
                        events=filtered,
                        retrieved_at=retrieved_at,
                        is_stale=is_stale,
                    )

            params = {
                "status": "open",
                "days": lookback_days,
            }

            headers = {"User-Agent": settings.osm_user_agent, "Accept": "application/json"}

            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                    resp = await client.get(self.api_url, params=params, headers=headers)

                if resp.status_code == 429:
                    logger.warning("NASA EONET rate limit encountered")
                    return self._fallback_or_error(cache_key, ProviderStatus.RATE_LIMITED, "NASA EONET rate limit reached", category, limit)

                if resp.status_code >= 500:
                    logger.warning(f"NASA EONET server error HTTP {resp.status_code}")
                    return self._fallback_or_error(cache_key, ProviderStatus.PROVIDER_ERROR, f"NASA EONET server returned HTTP {resp.status_code}", category, limit)

                resp.raise_for_status()
                data = resp.json()

                raw_events = data.get("events", [])
                records: List[NaturalEventRecord] = []
                seen_ids = set()

                for raw_evt in raw_events:
                    rec = self._parse_event(raw_evt)
                    if rec and rec.id not in seen_ids:
                        seen_ids.add(rec.id)
                        records.append(rec)

                # Sort by timestamp descending
                records.sort(key=lambda r: r.timestamp_utc, reverse=True)

                retrieved_at = self.cache.set(cache_key, records, self.cache_ttl)
                filtered = self._filter_events(records, category, limit)

                return NaturalEventsResponse(
                    status=ProviderStatus.OK if filtered else ProviderStatus.EMPTY,
                    count=len(filtered),
                    events=filtered,
                    retrieved_at=retrieved_at,
                    is_stale=False,
                )

            except httpx.TimeoutException:
                logger.warning("NASA EONET request timed out")
                return self._fallback_or_error(cache_key, ProviderStatus.TIMEOUT, "Request to NASA EONET timed out", category, limit)
            except Exception as exc:
                logger.error(f"Failed to fetch NASA EONET events: {exc}")
                return self._fallback_or_error(cache_key, ProviderStatus.PROVIDER_ERROR, str(exc), category, limit)

    def _filter_events(
        self,
        records: List[NaturalEventRecord],
        category: Optional[str],
        limit: int,
    ) -> List[NaturalEventRecord]:
        """Filter records by category and apply limit."""
        if not category:
            return records[:limit]
        cat_lower = category.strip().lower()
        return [r for r in records if cat_lower in r.category.lower() or cat_lower in r.category_title.lower()][:limit]

    def _fallback_or_error(
        self,
        cache_key: str,
        status: ProviderStatus,
        details: str,
        category: Optional[str],
        limit: int,
    ) -> NaturalEventsResponse:
        """Serve last successful snapshot if available, or error payload."""
        snapshot = self.cache.get_last_successful(cache_key)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if snapshot:
            records, retrieved_at = snapshot
            filtered = self._filter_events(records, category, limit)
            return NaturalEventsResponse(
                status=ProviderStatus.STALE,
                count=len(filtered),
                events=filtered,
                retrieved_at=retrieved_at,
                is_stale=True,
                details=f"Serving cached snapshot: {details}",
            )

        return NaturalEventsResponse(
            status=status,
            count=0,
            events=[],
            retrieved_at=now_iso,
            is_stale=False,
            details=details,
        )
