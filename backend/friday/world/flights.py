"""Live aircraft around a point, from the adsb.lol community ADS-B network (no key).

Queries are regional (≤250 nm), keyed on a rounded centre, and cached briefly so panning
the globe does not hammer the volunteer service.
"""

from typing import Any, Dict, List, Optional

import httpx

from schemas.contracts import FlightRecord, FlightsResponse
from backend.friday.config import settings
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.feed import cached_fetch, raise_for_upstream

PROVIDER = "adsb.lol"
ATTRIBUTION = "Aircraft data: adsb.lol community ADS-B network (ODbL)"
MAX_POSITION_AGE_S = 60


def parse_aircraft(ac: Dict[str, Any]) -> Optional[FlightRecord]:
    lat, lon = ac.get("lat"), ac.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    age = ac.get("seen_pos")
    if isinstance(age, (int, float)) and age > MAX_POSITION_AGE_S:
        return None
    alt = ac.get("alt_baro")
    on_ground = alt == "ground"
    rate = ac.get("baro_rate", ac.get("geom_rate"))
    emergency = ac.get("emergency")
    return FlightRecord(
        hex=str(ac.get("hex", "")).strip() or "unknown",
        callsign=(str(ac["flight"]).strip() or None) if ac.get("flight") else None,
        registration=ac.get("r"),
        aircraft_type=ac.get("t"),
        latitude=round(float(lat), 5),
        longitude=round(float(lon), 5),
        altitude_ft=int(alt) if isinstance(alt, (int, float)) else None,
        on_ground=on_ground,
        ground_speed_kt=float(ac["gs"]) if isinstance(ac.get("gs"), (int, float)) else None,
        track_deg=float(ac["track"]) if isinstance(ac.get("track"), (int, float)) else None,
        vertical_rate_fpm=int(rate) if isinstance(rate, (int, float)) else None,
        squawk=ac.get("squawk"),
        emergency=emergency if emergency and emergency != "none" else None,
        position_source=ac.get("type"),
        position_age_s=float(age) if isinstance(age, (int, float)) else None,
    )


class FlightProvider:
    def __init__(self, cache: Optional[WorldDataCache] = None, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.cache = cache or WorldDataCache()
        self.transport = transport

    async def get_flights(self, lat: float, lng: float, radius_nm: int = 200) -> FlightsResponse:
        radius = max(10, min(int(radius_nm), settings.flights_max_radius_nm))
        clat, clng = round(lat, 1), round(lng, 1)
        key = f"adsb:{clat}:{clng}:{radius}"

        async def fetch() -> List[FlightRecord]:
            url = f"{settings.adsb_lol_url}/lat/{clat}/lon/{clng}/dist/{radius}"
            async with httpx.AsyncClient(transport=self.transport, timeout=max(25.0, settings.world_http_timeout_seconds)) as client:
                resp = await client.get(url, headers={"User-Agent": settings.osm_user_agent, "Accept": "application/json"})
            raise_for_upstream(resp, "adsb.lol")
            out = []
            for ac in resp.json().get("ac") or []:
                rec = parse_aircraft(ac)
                if rec:
                    out.append(rec)
            return out

        result = await cached_fetch(self.cache, key, settings.flights_cache_ttl_seconds, fetch, "adsb.lol")
        flights = result.data or []
        return FlightsResponse(
            status=result.status,
            provider=PROVIDER,
            attribution=ATTRIBUTION,
            retrieved_at=result.retrieved_at,
            is_stale=result.is_stale,
            details=result.details,
            count=len(flights),
            flights=flights,
            center_lat=clat,
            center_lng=clng,
            radius_nm=radius,
        )
