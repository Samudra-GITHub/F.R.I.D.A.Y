"""Historical and place-based queries against providers that keep real archives.

USGS's FDSN event service holds the earthquake catalogue back to 1900, and NASA EONET
returns natural events active in a date range. Nothing here fills a gap: a day with
no records is reported as empty, and an unreachable provider is reported as missing.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.friday.config import settings
from backend.friday.earth.actions import EarthRecord

logger = logging.getLogger("friday.world.history")

FDSN_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
EARLIEST = date(1900, 1, 1)
MAX_RANGE_DAYS = 92
MAX_RECORDS = 500


class HistoryRangeError(ValueError):
    """The requested dates can't be served honestly."""


def validate_range(start: date, end: date, today: Optional[date] = None) -> Tuple[date, date]:
    """Check a date range against what the archives hold. Returns it unchanged if valid."""
    today = today or datetime.now(timezone.utc).date()
    if start > end:
        raise HistoryRangeError("The start date is after the end date.")
    if end > today:
        raise HistoryRangeError("The end date is in the future, and there is no record of the future.")
    if start < EARLIEST:
        raise HistoryRangeError("The archives used here start in 1900.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HistoryRangeError(f"Choose at most {MAX_RANGE_DAYS} days at a time.")
    return start, end


@dataclass
class HistoryResult:
    records: List[Dict[str, Any]] = field(default_factory=list)
    consulted: List[Dict[str, Any]] = field(default_factory=list)
    missing: List[Dict[str, str]] = field(default_factory=list)


def _iso_from_ms(ms: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def earthquake_records(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """USGS GeoJSON features to records. Features without a position, magnitude, or time are dropped."""
    out = []
    for f in features:
        props = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        when = _iso_from_ms(props.get("time"))
        if len(coords) < 2 or props.get("mag") is None or not when:
            continue
        try:
            rec = EarthRecord(
                id=f"usgs:{f.get('id')}", category="earthquake", latitude=float(coords[1]),
                longitude=float(coords[0]), title=str(props.get("title") or props.get("place") or "Earthquake")[:200],
                time_utc=when, magnitude=float(props["mag"]), source="USGS", url=props.get("url"),
            )
        except (ValueError, TypeError):
            continue
        out.append(rec.model_dump(exclude_none=True))
    return out


def eonet_records(events: List[Dict[str, Any]], start: date, end: date) -> List[Dict[str, Any]]:
    """EONET events to records, placed at their last observation inside the range."""
    out = []
    for e in events:
        best = None
        for g in e.get("geometry") or []:
            when = str(g.get("date") or "")
            coords = g.get("coordinates")
            if not when or g.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
                continue
            day = when[:10]
            if start.isoformat() <= day <= end.isoformat():
                best = (when, coords)
        if not best:
            continue
        categories = e.get("categories") or [{}]
        sources = e.get("sources") or [{}]
        try:
            rec = EarthRecord(
                id=f"eonet:{e.get('id')}", category="event", latitude=float(best[1][1]),
                longitude=float(best[1][0]), title=str(e.get("title") or categories[0].get("title") or "Event")[:200],
                time_utc=best[0], source="NASA EONET", url=sources[0].get("url") or e.get("link"),
            )
        except (ValueError, TypeError, IndexError):
            continue
        out.append(rec.model_dump(exclude_none=True))
    return out


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def bbox_around(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    """A west, north, east, south box that contains the circle, clamped to valid ranges."""
    dlat = radius_km / 111.0
    dlon = radius_km / max(1.0, 111.0 * math.cos(math.radians(lat)))
    return (max(-180.0, lon - dlon), min(90.0, lat + dlat), min(180.0, lon + dlon), max(-90.0, lat - dlat))


class HistoryService:
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None, timeout: float = 20.0) -> None:
        self.transport = transport
        self.timeout = timeout

    async def _get(self, url: str, params: Dict[str, Any]) -> Any:
        headers = {"User-Agent": settings.osm_user_agent, "Accept": "application/json"}
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def earthquakes(
        self,
        start: date,
        end: date,
        min_magnitude: float,
        result: HistoryResult,
        center: Optional[Tuple[float, float]] = None,
        radius_km: Optional[float] = None,
    ) -> None:
        params: Dict[str, Any] = {
            "format": "geojson",
            "starttime": start.isoformat(),
            "endtime": (end + timedelta(days=1)).isoformat(),
            "minmagnitude": min_magnitude,
            "orderby": "time",
            "limit": MAX_RECORDS,
        }
        if center and radius_km:
            params.update(latitude=center[0], longitude=center[1], maxradiuskm=radius_km)
        try:
            data = await self._get(FDSN_URL, params)
        except Exception as exc:  # report, never guess
            logger.warning("USGS history request failed: %s", exc)
            result.missing.append({"provider": "USGS", "reason": "The earthquake catalogue couldn't be reached."})
            return
        records = earthquake_records(data.get("features") or [])
        result.records.extend(records)
        result.consulted.append({"provider": "USGS earthquake catalogue", "count": len(records), "url": FDSN_URL})

    async def events(
        self,
        start: date,
        end: date,
        result: HistoryResult,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> None:
        params: Dict[str, Any] = {"status": "all", "start": start.isoformat(), "end": end.isoformat(), "limit": MAX_RECORDS}
        if bbox:
            params["bbox"] = ",".join(f"{v:.4f}" for v in bbox)
        try:
            data = await self._get(settings.nasa_eonet_url, params)
        except Exception as exc:
            logger.warning("EONET history request failed: %s", exc)
            result.missing.append({"provider": "NASA EONET", "reason": "The natural events archive couldn't be reached."})
            return
        records = eonet_records(data.get("events") or [], start, end)
        result.records.extend(records)
        result.consulted.append({"provider": "NASA EONET", "count": len(records), "url": settings.nasa_eonet_url})
