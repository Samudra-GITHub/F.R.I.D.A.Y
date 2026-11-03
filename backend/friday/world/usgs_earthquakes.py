"""USGS Earthquake GeoJSON feed provider.

Fetches and normalizes earthquake telemetry from official USGS GeoJSON summary feeds.
Guarantees zero-fabrication: reports actual event locations, magnitude, depth, and USGS links.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from schemas.contracts import EarthquakeRecord, EarthquakesResponse, ProviderStatus
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache

logger = logging.getLogger(__name__)


class USGSEarthquakeProvider:
    """Provider for real-time earthquake telemetry from the U.S. Geological Survey."""

    def __init__(
        self,
        cache: Optional[WorldDataCache] = None,
        feed_url: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.cache = cache or WorldDataCache()
        self.feed_url = feed_url or settings.usgs_earthquakes_url
        self.cache_ttl = cache_ttl_seconds if cache_ttl_seconds is not None else settings.usgs_cache_ttl_seconds
        self.timeout = timeout_seconds if timeout_seconds is not None else settings.world_http_timeout_seconds
        self.transport = transport

    def _format_epoch_ms(self, epoch_ms: Optional[int]) -> Optional[str]:
        """Convert epoch millisecond timestamp to ISO-8601 UTC string."""
        if epoch_ms is None or not isinstance(epoch_ms, (int, float)):
            return None
        try:
            return datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return None

    def _parse_feature(self, feature: Dict[str, Any]) -> Optional[EarthquakeRecord]:
        """Parse and validate a single GeoJSON earthquake feature."""
        try:
            event_id = str(feature.get("id") or "").strip()
            if not event_id:
                return None

            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates")
            if not coords or len(coords) < 2:
                return None

            # GeoJSON coordinates order: [longitude, latitude, depth_km]
            lng = float(coords[0])
            lat = float(coords[1])
            depth_km = float(coords[2]) if len(coords) > 2 else 0.0

            # Validate WGS84 coordinate ranges
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
                return None

            props = feature.get("properties") or {}
            raw_mag = props.get("mag")
            if raw_mag is None:
                return None
            magnitude = float(raw_mag)

            place = str(props.get("place") or "Unknown location").strip()
            title = str(props.get("title") or f"M {magnitude:.1f} - {place}").strip()
            time_utc = self._format_epoch_ms(props.get("time"))
            if not time_utc:
                time_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            updated_utc = self._format_epoch_ms(props.get("updated"))
            url = props.get("url")
            tsunami = bool(props.get("tsunami") == 1)
            felt = props.get("felt")
            felt_reports = int(felt) if isinstance(felt, (int, float)) else None
            alert = str(props.get("alert")).lower() if props.get("alert") else None

            return EarthquakeRecord(
                id=event_id,
                title=title,
                magnitude=round(magnitude, 1),
                place=place,
                latitude=round(lat, 4),
                longitude=round(lng, 4),
                depth_km=round(depth_km, 1),
                time_utc=time_utc,
                updated_utc=updated_utc,
                url=url,
                tsunami_alert=tsunami,
                felt_reports=felt_reports,
                alert_level=alert,
            )
        except Exception as exc:
            logger.debug(f"Skipping malformed USGS feature: {exc}")
            return None

    async def get_earthquakes(
        self,
        min_magnitude: float = 0.0,
        limit: int = 50,
        force_refresh: bool = False,
    ) -> EarthquakesResponse:
        """Fetch and return recent earthquakes from USGS with caching and filtering."""
        cache_key = "usgs_earthquakes_raw"
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Check fresh cache unless force_refresh is requested
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                raw_records, is_stale, retrieved_at = cached
                filtered = [r for r in raw_records if r.magnitude >= min_magnitude][:limit]
                return EarthquakesResponse(
                    status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                    count=len(filtered),
                    earthquakes=filtered,
                    retrieved_at=retrieved_at,
                    is_stale=is_stale,
                )

        lock = await self.cache.get_lock(cache_key)
        async with lock:
            # Re-check cache after acquiring lock
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached:
                    raw_records, is_stale, retrieved_at = cached
                    filtered = [r for r in raw_records if r.magnitude >= min_magnitude][:limit]
                    return EarthquakesResponse(
                        status=ProviderStatus.OK if not is_stale else ProviderStatus.STALE,
                        count=len(filtered),
                        earthquakes=filtered,
                        retrieved_at=retrieved_at,
                        is_stale=is_stale,
                    )

            try:
                headers = {"User-Agent": settings.osm_user_agent, "Accept": "application/json"}
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                    resp = await client.get(self.feed_url, headers=headers)

                if resp.status_code == 429:
                    logger.warning("USGS Earthquakes rate limit encountered")
                    return self._fallback_or_error(cache_key, ProviderStatus.RATE_LIMITED, "Rate limit reached on USGS feed", min_magnitude, limit)

                if resp.status_code >= 500:
                    logger.warning(f"USGS server error: HTTP {resp.status_code}")
                    return self._fallback_or_error(cache_key, ProviderStatus.PROVIDER_ERROR, f"USGS server returned HTTP {resp.status_code}", min_magnitude, limit)

                resp.raise_for_status()
                data = resp.json()

                features = data.get("features", [])
                records: List[EarthquakeRecord] = []
                seen_ids = set()

                for f in features:
                    rec = self._parse_feature(f)
                    if rec and rec.id not in seen_ids:
                        seen_ids.add(rec.id)
                        records.append(rec)

                # Sort descending by occurrence time
                records.sort(key=lambda r: r.time_utc, reverse=True)

                retrieved_at = self.cache.set(cache_key, records, self.cache_ttl)
                filtered = [r for r in records if r.magnitude >= min_magnitude][:limit]

                return EarthquakesResponse(
                    status=ProviderStatus.OK if filtered else ProviderStatus.EMPTY,
                    count=len(filtered),
                    earthquakes=filtered,
                    retrieved_at=retrieved_at,
                    is_stale=False,
                )

            except httpx.TimeoutException:
                logger.warning("USGS Earthquakes request timed out")
                return self._fallback_or_error(cache_key, ProviderStatus.TIMEOUT, "Request to USGS timed out", min_magnitude, limit)
            except Exception as exc:
                logger.error(f"Failed to fetch USGS earthquakes: {exc}")
                return self._fallback_or_error(cache_key, ProviderStatus.PROVIDER_ERROR, str(exc), min_magnitude, limit)

    def _fallback_or_error(
        self,
        cache_key: str,
        status: ProviderStatus,
        details: str,
        min_magnitude: float,
        limit: int,
    ) -> EarthquakesResponse:
        """Serve last successful snapshot if available, or error payload."""
        snapshot = self.cache.get_last_successful(cache_key)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if snapshot:
            raw_records, retrieved_at = snapshot
            filtered = [r for r in raw_records if r.magnitude >= min_magnitude][:limit]
            return EarthquakesResponse(
                status=ProviderStatus.STALE,
                count=len(filtered),
                earthquakes=filtered,
                retrieved_at=retrieved_at,
                is_stale=True,
                details=f"Serving cached snapshot: {details}",
            )

        return EarthquakesResponse(
            status=status,
            count=0,
            earthquakes=[],
            retrieved_at=now_iso,
            is_stale=False,
            details=details,
        )
