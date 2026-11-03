"""Satellite positions from CelesTrak orbital elements, propagated locally with SGP4.

Elements (OMM JSON) are cached for hours, as CelesTrak requests; positions are computed
for the instant of each request, so they are real propagations, not interpolated guesses.
Accuracy is that of SGP4 with public elements (typically ~1 km near epoch for LEO).
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sgp4 import omm
from sgp4.api import Satrec, jday

from schemas.contracts import ProviderStatus, SatelliteRecord, SatellitesResponse, SatelliteTrackResponse
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.feed import cached_fetch, raise_for_upstream, utc_now_iso

PROVIDER = "CelesTrak (elements) + SGP4"
ATTRIBUTION = "Orbital elements: CelesTrak (celestrak.org); positions propagated locally with SGP4"

_WGS84_A = 6378.137
_WGS84_F = 1 / 298.257223563
_WGS84_E2 = _WGS84_F * (2 - _WGS84_F)


def _gmst(jd_ut1: float) -> float:
    """Greenwich mean sidereal time (IAU 1982), radians."""
    t = (jd_ut1 - 2451545.0) / 36525.0
    sec = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((sec % 86400.0) / 240.0)


def teme_to_geodetic(r: Tuple[float, float, float], jd_ut1: float) -> Tuple[float, float, float]:
    """TEME position (km) → WGS84 latitude°, longitude°, altitude km (polar motion ignored)."""
    g = _gmst(jd_ut1)
    x = math.cos(g) * r[0] + math.sin(g) * r[1]
    y = -math.sin(g) * r[0] + math.cos(g) * r[1]
    z = r[2]
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - _WGS84_E2))
    for _ in range(5):
        n = _WGS84_A / math.sqrt(1 - _WGS84_E2 * math.sin(lat) ** 2)
        lat = math.atan2(z + _WGS84_E2 * n * math.sin(lat), p)
    n = _WGS84_A / math.sqrt(1 - _WGS84_E2 * math.sin(lat) ** 2)
    alt = p / math.cos(lat) - n if abs(math.cos(lat)) > 1e-9 else abs(z) - n * (1 - _WGS84_E2)
    lon_deg = (math.degrees(lon) + 540) % 360 - 180
    return math.degrees(lat), lon_deg, alt


def orbit_class(alt_km: float, eccentricity: float) -> str:
    if eccentricity > 0.25:
        return "HEO"
    if alt_km < 2000:
        return "LEO"
    if 34786 <= alt_km <= 36786:
        return "GEO"
    return "MEO"


def _jd(at: datetime) -> Tuple[float, float]:
    return jday(at.year, at.month, at.day, at.hour, at.minute, at.second + at.microsecond / 1e6)


class SatelliteProvider:
    def __init__(
        self,
        cache: Optional[WorldDataCache] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        groups: Optional[List[str]] = None,
    ) -> None:
        self.cache = cache or WorldDataCache()
        self.transport = transport
        self.groups = groups or list(settings.celestrak_groups)

    async def _fetch_elements(self) -> List[Tuple[str, Dict[str, Any]]]:
        out: List[Tuple[str, Dict[str, Any]]] = []
        seen = set()
        headers = {"User-Agent": settings.osm_user_agent, "Accept": "application/json"}
        async with httpx.AsyncClient(transport=self.transport, timeout=settings.world_http_timeout_seconds) as client:
            for group in self.groups:
                resp = await client.get(settings.celestrak_gp_url, params={"GROUP": group, "FORMAT": "json"}, headers=headers)
                raise_for_upstream(resp, "CelesTrak")
                items = resp.json()
                if not isinstance(items, list):
                    continue
                for item in items:
                    norad = item.get("NORAD_CAT_ID")
                    if isinstance(norad, int) and norad not in seen and item.get("MEAN_MOTION"):
                        seen.add(norad)
                        out.append((group, item))
        return out

    @staticmethod
    def _satrec(fields: Dict[str, Any]) -> Satrec:
        sat = Satrec()
        omm.initialize(sat, {k: str(v) for k, v in fields.items()})
        return sat

    async def _elements(self, force_refresh: bool = False):
        return await cached_fetch(
            self.cache, "celestrak_elements", settings.celestrak_cache_ttl_seconds, self._fetch_elements, "CelesTrak", force_refresh
        )

    async def get_positions(self, at: Optional[datetime] = None, limit: int = 600) -> SatellitesResponse:
        at = at or datetime.now(timezone.utc)
        result = await self._elements()
        records: List[SatelliteRecord] = []
        for group, fields in (result.data or [])[:limit]:
            try:
                sat = self._satrec(fields)
                jd, fr = _jd(at)
                err, r, v = sat.sgp4(jd, fr)
                if err != 0:
                    continue  # decayed or invalid elements: skip rather than guess
                lat, lng, alt = teme_to_geodetic(r, jd + fr)
                mm = float(fields["MEAN_MOTION"])
                records.append(
                    SatelliteRecord(
                        norad_id=int(fields["NORAD_CAT_ID"]),
                        name=str(fields.get("OBJECT_NAME", "UNKNOWN")).strip(),
                        group=group,
                        latitude=round(lat, 4),
                        longitude=round(lng, 4),
                        altitude_km=round(alt, 1),
                        velocity_kms=round(math.sqrt(sum(c * c for c in v)), 3),
                        inclination_deg=float(fields.get("INCLINATION", 0.0)),
                        period_min=round(1440.0 / mm, 1),
                        orbit_class=orbit_class(alt, float(fields.get("ECCENTRICITY", 0.0))),
                        elements_epoch_utc=str(fields.get("EPOCH", "")) + "Z",
                    )
                )
            except Exception:
                continue
        return SatellitesResponse(
            status=result.status if result.data is not None else result.status,
            provider=PROVIDER,
            attribution=ATTRIBUTION,
            retrieved_at=result.retrieved_at,
            is_stale=result.is_stale,
            details=result.details,
            count=len(records),
            satellites=records,
            positions_at=at.isoformat().replace("+00:00", "Z"),
        )

    async def get_track(self, norad_id: int, minutes: int = 50, step_s: int = 60) -> SatelliteTrackResponse:
        """Ground track from `minutes` ago to `minutes` ahead, for drawing the orbit."""
        result = await self._elements()
        match = next((f for _, f in (result.data or []) if f.get("NORAD_CAT_ID") == norad_id), None)
        base = dict(provider=PROVIDER, attribution=ATTRIBUTION, retrieved_at=result.retrieved_at, is_stale=result.is_stale, norad_id=norad_id)
        if match is None:
            status = result.status if result.data is None else ProviderStatus.EMPTY
            return SatelliteTrackResponse(status=status, details=result.details or "Satellite not in the loaded catalog", **base)
        sat = self._satrec(match)
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=minutes)
        points: List[List[float]] = []
        for i in range(0, minutes * 2 * 60 + 1, step_s):
            t = start + timedelta(seconds=i)
            jd, fr = _jd(t)
            err, r, _ = sat.sgp4(jd, fr)
            if err == 0:
                lat, lng, alt = teme_to_geodetic(r, jd + fr)
                points.append([round(lat, 3), round(lng, 3), round(alt, 1)])
        return SatelliteTrackResponse(
            status=ProviderStatus.OK if points else ProviderStatus.EMPTY,
            name=str(match.get("OBJECT_NAME", "")).strip(),
            points=points,
            start_utc=start.isoformat().replace("+00:00", "Z"),
            end_utc=(start + timedelta(minutes=minutes * 2)).isoformat().replace("+00:00", "Z"),
            **base,
        )


__all__ = ["SatelliteProvider", "teme_to_geodetic", "orbit_class", "utc_now_iso"]
