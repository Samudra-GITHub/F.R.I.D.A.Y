"""Location Service REST API Router for W.E.D.N.E.S.D.A.Y.

Exposes tightly scoped loopback endpoints for inspecting and controlling
the local Windows Location Service.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from schemas.contracts import (
    LocationMode,
    DeviceLocationFix,
    LocationServiceStatus,
    NearbySearchResponse,
    ReverseGeocodeResponse,
)
from backend.friday.location.service import LocationService
from backend.friday.location.enrichment import (
    _global_nominatim_rate_limiter,
    get_location_enricher,
    validate_coordinates,
)
from backend.friday.config import settings
import time
import httpx

router = APIRouter(prefix="/location", tags=["location"])

# Shared service instance
location_service = LocationService()
enricher = get_location_enricher()


class EnableTrackingRequest(BaseModel):
    interval_s: Optional[int] = Field(default=None, ge=15, le=3600, description="Polling interval in seconds")


class SetModeRequest(BaseModel):
    mode: LocationMode
    interval_s: Optional[int] = Field(default=None, ge=15, le=3600, description="Polling interval in seconds")


class NearbySearchRequest(BaseModel):
    category: Optional[str] = Field(default=None, description="Category filter (e.g. pharmacy, hospital, cafe)")
    keyword: Optional[str] = Field(default=None, description="Keyword search term")
    radius_m: Optional[int] = Field(default=1500, ge=50, le=10000, description="Search radius in metres")
    limit: Optional[int] = Field(default=10, ge=1, le=20, description="Maximum results to return")
    latitude: Optional[float] = Field(default=None, description="Optional explicit center latitude")
    longitude: Optional[float] = Field(default=None, description="Optional explicit center longitude")


@router.get("/status", response_model=LocationServiceStatus)
async def get_location_status() -> LocationServiceStatus:
    """Read current tracking state and latest device fix."""
    try:
        return location_service.get_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read location status: {exc}")


@router.post("/enable", response_model=LocationServiceStatus)
async def enable_tracking(req: Optional[EnableTrackingRequest] = None) -> LocationServiceStatus:
    """Explicitly authorize and start background location tracking."""
    try:
        interval = req.interval_s if req else None
        return location_service.enable_tracking(interval_s=interval)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to enable tracking: {exc}")


@router.post("/pause", response_model=LocationServiceStatus)
async def pause_tracking() -> LocationServiceStatus:
    """Temporarily suspend location polling without terminating the worker process."""
    try:
        return location_service.pause_tracking()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to pause tracking: {exc}")


@router.post("/resume", response_model=LocationServiceStatus)
async def resume_tracking() -> LocationServiceStatus:
    """Resume location polling from a paused state."""
    try:
        return location_service.resume_tracking()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to resume tracking: {exc}")


@router.post("/disable", response_model=LocationServiceStatus)
async def disable_tracking() -> LocationServiceStatus:
    """Deauthorize and stop background location tracking, terminating the worker."""
    try:
        return location_service.disable_tracking()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to disable tracking: {exc}")


@router.post("/mode", response_model=LocationServiceStatus)
async def set_location_mode(req: SetModeRequest) -> LocationServiceStatus:
    """Switch between off, once, and continuous. Only the local UI calls this, never the model."""
    try:
        return location_service.set_mode(req.mode, req.interval_s)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to set location mode: {exc}")


@router.post("/clear", response_model=LocationServiceStatus)
async def clear_location() -> LocationServiceStatus:
    """Forget the stored position."""
    try:
        return location_service.clear_location()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear location: {exc}")


@router.post("/poll-once", response_model=DeviceLocationFix)
async def poll_location_once() -> DeviceLocationFix:
    """Acquire a single one-off device fix without enabling continuous background tracking."""
    try:
        return await location_service.poll_once()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to poll device location: {exc}")


@router.get("/geocode", response_model=ReverseGeocodeResponse)
async def reverse_geocode_location(
    lat: Optional[float] = Query(default=None, description="Latitude to reverse-geocode"),
    lng: Optional[float] = Query(default=None, description="Longitude to reverse-geocode"),
    latitude: Optional[float] = Query(default=None, description="Full latitude parameter"),
    longitude: Optional[float] = Query(default=None, description="Full longitude parameter"),
) -> ReverseGeocodeResponse:
    """Resolve coordinates to a human-readable address. Uses device location if omitted."""
    eff_lat = lat if lat is not None else latitude
    eff_lng = lng if lng is not None else longitude

    if eff_lat is not None or eff_lng is not None:
        if eff_lat is None or eff_lng is None:
            raise HTTPException(status_code=400, detail="Both latitude and longitude must be provided.")
        is_valid, err = validate_coordinates(eff_lat, eff_lng)
        if not is_valid:
            raise HTTPException(status_code=400, detail=err)
        lat = eff_lat
        lng = eff_lng
    else:
        status = location_service.get_status()
        fix = status.latest_fix
        if not status.tracking_enabled or not fix or fix.latitude is None or fix.longitude is None:
            return ReverseGeocodeResponse(
                status="no_fix",
                details="Device location fix is not available. Enable tracking to resolve host location.",
                provider="None",
            )
        lat = fix.latitude
        lng = fix.longitude

    active_enricher = get_location_enricher()
    return await active_enricher.reverse_geocode(lat, lng)


@router.post("/nearby", response_model=NearbySearchResponse)
async def search_nearby_places(
    req: Optional[NearbySearchRequest] = None,
) -> NearbySearchResponse:
    """Search points of interest near device location or specified coordinates."""
    request_data = req or NearbySearchRequest()
    radius_m = request_data.radius_m or 1500
    limit = request_data.limit or 10

    if request_data.latitude is not None or request_data.longitude is not None:
        if request_data.latitude is None or request_data.longitude is None:
            raise HTTPException(status_code=400, detail="Both latitude and longitude must be provided.")
        is_valid, err = validate_coordinates(request_data.latitude, request_data.longitude)
        if not is_valid:
            raise HTTPException(status_code=400, detail=err)
        lat = request_data.latitude
        lng = request_data.longitude
    else:
        status = location_service.get_status()
        fix = status.latest_fix
        if not status.tracking_enabled or not fix or fix.latitude is None or fix.longitude is None:
            return NearbySearchResponse(
                status="no_fix",
                query=request_data.keyword,
                category=request_data.category,
                radius_m=radius_m,
                places=[],
                details="Device location fix is not available. Enable tracking to search around host device.",
                provider="None",
            )
        lat = fix.latitude
        lng = fix.longitude

    active_enricher = get_location_enricher()
    return await active_enricher.search_nearby(
        lat=lat,
        lng=lng,
        radius_m=radius_m,
        category=request_data.category,
        keyword=request_data.keyword,
        limit=limit,
    )


# ---- Forward place search (user-initiated from the Earth view) -----------------

_search_cache: dict[str, tuple[float, dict]] = {}


@router.get("/search")
async def search_places(q: str = Query(..., min_length=2, max_length=120)) -> dict:
    """Resolve a place name to coordinates via OpenStreetMap Nominatim.

    Only runs when the OSM provider is configured. Honors Nominatim's usage policy
    (1 request/second, identifying User-Agent) and caches results for the OSM TTL.
    Returns ``status: provider_not_configured`` instead of guessing when disabled.
    """
    query = " ".join(q.split())
    if settings.location_provider != "osm":
        return {"status": "provider_not_configured", "query": query, "results": [],
                "details": "Place search needs LOCATION_PROVIDER=osm."}

    key = query.lower()
    cached = _search_cache.get(key)
    if cached and time.monotonic() - cached[0] < settings.osm_cache_ttl_seconds:
        return {**cached[1], "is_cached": True}

    url = settings.osm_nominatim_url.rsplit("/", 1)[0] + "/search"
    agent = settings.osm_user_agent
    if settings.osm_contact_email:
        agent = f"{agent} ({settings.osm_contact_email.strip()})"
    try:
        await _global_nominatim_rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=settings.osm_timeout_seconds) as client:
            res = await client.get(
                url,
                params={"q": query, "format": "jsonv2", "limit": 6, "addressdetails": 0},
                headers={"User-Agent": agent, "Accept-Language": "en"},
            )
    except httpx.TimeoutException:
        return {"status": "timeout", "query": query, "results": [], "details": "Nominatim did not respond in time."}
    except httpx.HTTPError as exc:
        return {"status": "provider_error", "query": query, "results": [], "details": str(exc)}

    if res.status_code == 429:
        return {"status": "rate_limited", "query": query, "results": [], "details": "Nominatim rate limit reached; try again shortly."}
    if res.status_code != 200:
        return {"status": "provider_error", "query": query, "results": [], "details": f"HTTP {res.status_code}"}

    results = []
    for item in res.json() if isinstance(res.json(), list) else []:
        try:
            lat, lng = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not validate_coordinates(lat, lng)[0]:
            continue
        bbox = item.get("boundingbox")
        results.append({
            "name": item.get("name") or item.get("display_name", "").split(",")[0],
            "display_name": item.get("display_name"),
            "category": item.get("category") or item.get("class"),
            "type": item.get("type"),
            "latitude": lat,
            "longitude": lng,
            "bbox": [float(b) for b in bbox] if isinstance(bbox, list) and len(bbox) == 4 else None,
            "osm_uri": f"https://www.openstreetmap.org/{item['osm_type']}/{item['osm_id']}" if item.get("osm_type") and item.get("osm_id") else None,
        })
    payload = {
        "status": "ok" if results else "empty",
        "query": query,
        "results": results,
        "attribution": "© OpenStreetMap contributors (ODbL), via Nominatim",
        "is_cached": False,
    }
    if len(_search_cache) > 200:
        _search_cache.clear()
    _search_cache[key] = (time.monotonic(), payload)
    return payload
