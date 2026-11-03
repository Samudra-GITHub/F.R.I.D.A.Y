"""World Intelligence REST API Router for W.E.D.N.E.S.D.A.Y. Phase 3.

Exposes endpoints for querying live earthquakes, atmospheric weather, natural events,
disaster alerts, verified news, and system status.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from schemas.contracts import (
    DisastersResponse,
    EarthquakesResponse,
    NaturalEventsResponse,
    NewsResponse,
    WeatherResponse,
    WorldStatusResponse,
    SatellitesResponse,
    SatelliteTrackResponse,
    FlightsResponse,
    LaunchesResponse,
    FiresResponse,
)
from backend.friday.world.service import WorldIntelligenceService
from backend.friday.world.satellites import SatelliteProvider
from backend.friday.world.flights import FlightProvider
from backend.friday.world.launches import LaunchProvider
from backend.friday.world.fires import FireProvider

router = APIRouter(prefix="/world", tags=["world"])

# Shared service instance
world_service = WorldIntelligenceService()
satellite_provider = SatelliteProvider(cache=world_service.cache)
flight_provider = FlightProvider(cache=world_service.cache)
launch_provider = LaunchProvider(cache=world_service.cache)
fire_provider = FireProvider(cache=world_service.cache)


@router.get("/status", response_model=WorldStatusResponse)
async def get_world_status() -> WorldStatusResponse:
    """Return health, freshness, and cache telemetry for all world providers."""
    try:
        return await world_service.get_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve world status: {exc}")


@router.get("/earthquakes", response_model=EarthquakesResponse)
async def get_earthquakes(
    min_magnitude: float = Query(default=0.0, ge=0.0, le=10.0, description="Minimum earthquake magnitude"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum results to return"),
    refresh: bool = Query(default=False, description="Bypass cache and force fresh fetch"),
) -> EarthquakesResponse:
    """Query recent earthquakes from official USGS GeoJSON summary feeds."""
    try:
        return await world_service.get_earthquakes(
            min_magnitude=min_magnitude,
            limit=limit,
            force_refresh=refresh,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query earthquakes: {exc}")


@router.get("/weather", response_model=WeatherResponse)
async def get_weather(
    lat: Optional[float] = Query(default=None, description="Latitude for weather lookup"),
    lng: Optional[float] = Query(default=None, description="Longitude for weather lookup"),
    latitude: Optional[float] = Query(default=None, description="Alternative parameter for latitude"),
    longitude: Optional[float] = Query(default=None, description="Alternative parameter for longitude"),
    location_name: Optional[str] = Query(default=None, description="Optional city or location label"),
    refresh: bool = Query(default=False, description="Bypass cache and force fresh fetch"),
) -> WeatherResponse:
    """Query current atmospheric weather and forecasts from Open-Meteo."""
    target_lat = lat if lat is not None else latitude
    target_lng = lng if lng is not None else longitude

    if target_lat is None or target_lng is None:
        raise HTTPException(status_code=400, detail="Parameters 'lat' and 'lng' (or 'latitude' and 'longitude') are required.")

    if not (-90.0 <= target_lat <= 90.0 and -180.0 <= target_lng <= 180.0):
        raise HTTPException(status_code=400, detail=f"Coordinates ({target_lat}, {target_lng}) are out of valid range [-90..90, -180..180].")

    try:
        return await world_service.get_weather(
            latitude=target_lat,
            longitude=target_lng,
            location_name=location_name,
            force_refresh=refresh,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query weather: {exc}")


@router.get("/events", response_model=NaturalEventsResponse)
async def get_natural_events(
    days: Optional[int] = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    category: Optional[str] = Query(default=None, description="Filter category (e.g. 'wildfires', 'severeStorms')"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum results to return"),
    refresh: bool = Query(default=False, description="Bypass cache and force fresh fetch"),
) -> NaturalEventsResponse:
    """Query active natural events from NASA Earth Observatory Natural Event Tracker (EONET v3)."""
    try:
        return await world_service.get_events(
            days=days,
            category=category,
            limit=limit,
            force_refresh=refresh,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query natural events: {exc}")


@router.get("/disasters", response_model=DisastersResponse)
async def get_disaster_alerts(
    alert_level: Optional[str] = Query(default=None, description="Filter alert level ('Green', 'Orange', 'Red')"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum results to return"),
    refresh: bool = Query(default=False, description="Bypass cache and force fresh fetch"),
) -> DisastersResponse:
    """Query disaster alerts from Global Disaster Alert and Coordination System (GDACS)."""
    try:
        return await world_service.get_disasters(
            alert_level=alert_level,
            limit=limit,
            force_refresh=refresh,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query disaster alerts: {exc}")


@router.get("/news", response_model=NewsResponse)
async def get_world_news(
    limit: int = Query(default=30, ge=1, le=100, description="Maximum articles to return"),
    refresh: bool = Query(default=False, description="Bypass cache and force fresh fetch"),
) -> NewsResponse:
    """Query verified world news headlines from allowlisted RSS feeds."""
    try:
        return await world_service.get_news(
            limit=limit,
            force_refresh=refresh,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query news: {exc}")


# ---- Additional Earth layers ------------------------------------------------------

@router.get("/satellites", response_model=SatellitesResponse)
async def get_satellites(limit: int = Query(default=600, ge=1, le=1000)) -> SatellitesResponse:
    """Current positions of tracked satellites (CelesTrak elements, SGP4 propagation)."""
    return await satellite_provider.get_positions(limit=limit)


@router.get("/satellites/{norad_id}/track", response_model=SatelliteTrackResponse)
async def get_satellite_track(norad_id: int, minutes: int = Query(default=50, ge=5, le=180)) -> SatelliteTrackResponse:
    """Ground track ±minutes around now for one satellite."""
    return await satellite_provider.get_track(norad_id, minutes=minutes)


@router.get("/flights", response_model=FlightsResponse)
async def get_flights(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_nm: int = Query(default=200, ge=10, le=250),
) -> FlightsResponse:
    """Live aircraft within radius_nm of a point (adsb.lol)."""
    return await flight_provider.get_flights(lat, lng, radius_nm)


@router.get("/launches", response_model=LaunchesResponse)
async def get_launches(limit: int = Query(default=25, ge=1, le=30)) -> LaunchesResponse:
    """Upcoming orbital launches (Launch Library 2)."""
    return await launch_provider.get_launches(limit)


@router.get("/fires", response_model=FiresResponse)
async def get_fires(limit: int = Query(default=4000, ge=1, le=4000)) -> FiresResponse:
    """Active fire detections in the last 24 h (NASA FIRMS; requires FIRMS_MAP_KEY)."""
    return await fire_provider.get_fires(limit)
