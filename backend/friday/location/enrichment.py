"""Decoupled Location Enrichment & Google Maps Platform Integration.

Provides reverse geocoding and nearby point-of-interest discovery.
Operates with strict privacy guarantees, coordinate masking, bounded caching,
and honest offline fallback (NoOp) when no API key is configured.
"""

import asyncio
import logging
import math
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import httpx

from schemas.contracts import (
    DeviceLocationFix,
    GeocodedAddress,
    NearbySearchResponse,
    PlaceSummary,
    ReverseGeocodeResponse,
)
from backend.friday.config import settings

logger = logging.getLogger(__name__)

GMP_SOLUTION_ID = "gmp_git_agentskills_v1"

# Mapping human/query category terms to official Places API (New) types
CATEGORY_TYPE_MAP: Dict[str, str] = {
    "hospital": "hospital",
    "hospitals": "hospital",
    "pharmacy": "pharmacy",
    "pharmacies": "pharmacy",
    "chemist": "pharmacy",
    "fuel": "gas_station",
    "petrol": "gas_station",
    "gas": "gas_station",
    "gas_station": "gas_station",
    "petrol_station": "gas_station",
    "cafe": "cafe",
    "cafes": "cafe",
    "coffee": "coffee_shop",
    "restaurant": "restaurant",
    "restaurants": "restaurant",
    "food": "restaurant",
    "bank": "bank",
    "atm": "atm",
    "supermarket": "supermarket",
    "grocery": "supermarket",
    "police": "police",
    "lodging": "lodging",
    "hotel": "hotel",
}


def mask_coords(lat: float, lng: float) -> str:
    """Mask coordinates for privacy in logs."""
    try:
        lat_str = str(lat).split(".")[0]
        lng_str = str(lng).split(".")[0]
        return f"({lat_str}.***, {lng_str}.***)"
    except Exception:
        return "(masked)"


def validate_coordinates(lat: float, lng: float) -> Tuple[bool, Optional[str]]:
    """Validate latitude and longitude ranges."""
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False, "Coordinates must be numeric."
    if math.isnan(lat) or math.isnan(lng):
        return False, "Coordinates cannot be NaN."
    if not (-90.0 <= lat <= 90.0):
        return False, f"Latitude {lat} out of valid range [-90, 90]."
    if not (-180.0 <= lng <= 180.0):
        return False, f"Longitude {lng} out of valid range [-180, 180]."
    return True, None


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance between two points on Earth in metres."""
    r = 6371000.0  # Earth radius in metres
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 1)


class BaseLocationEnricher(ABC):
    """Abstract place enrichment and reverse geocoding interface."""

    @property
    def is_configured(self) -> bool:
        """Whether this enrichment provider has valid active credentials."""
        return False

    @property
    def provider_name(self) -> str:
        """Name of this provider."""
        return "None"

    @abstractmethod
    async def reverse_geocode(self, lat: float, lng: float) -> ReverseGeocodeResponse:
        """Convert coordinates to human-readable address."""
        pass

    @abstractmethod
    async def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int = 1500,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10,
    ) -> NearbySearchResponse:
        """Search points of interest near given coordinates."""
        pass


class NoOpLocationEnricher(BaseLocationEnricher):
    """Default local-first offline fallback.

    Performs zero network calls and requires zero credentials.
    Returns explicit 'provider_not_configured' status without fabricating places.
    """

    @property
    def is_configured(self) -> bool:
        return False

    @property
    def provider_name(self) -> str:
        return "None"

    async def reverse_geocode(self, lat: float, lng: float) -> ReverseGeocodeResponse:
        is_valid, err = validate_coordinates(lat, lng)
        if not is_valid:
            return ReverseGeocodeResponse(
                status="error",
                latitude=lat,
                longitude=lng,
                details=err,
                provider="None",
            )
        return ReverseGeocodeResponse(
            status="provider_not_configured",
            latitude=lat,
            longitude=lng,
            details="Google Maps API key is not configured. Reverse geocoding is unavailable.",
            provider="None",
        )

    async def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int = 1500,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10,
    ) -> NearbySearchResponse:
        is_valid, err = validate_coordinates(lat, lng)
        if not is_valid:
            return NearbySearchResponse(
                status="error",
                center_lat=lat,
                center_lng=lng,
                radius_m=radius_m,
                details=err,
                provider="None",
            )
        return NearbySearchResponse(
            status="provider_not_configured",
            query=keyword,
            category=category,
            center_lat=lat,
            center_lng=lng,
            radius_m=radius_m,
            places=[],
            details="Google Maps API key is not configured. Set GOOGLE_MAPS_API_KEY to enable nearby search.",
            provider="None",
        )


class GoogleMapsLocationEnricher(BaseLocationEnricher):
    """Google Maps Platform Provider for Geocoding and Places API (New).

    Features:
    - Bounded in-memory TTL caching for reverse geocoding to prevent repeat calls.
    - Coordinate validation and radius clamping.
    - Safe error handling (quota, invalid key, timeouts).
    - Solution attribution header 'gmp_git_agentskills_v1'.
    - Zero fabrication of ratings, hours, or place attributes.
    """

    GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @property
    def provider_name(self) -> str:
        return "GoogleMaps"

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 8.0,
        cache_ttl_seconds: int = 300,
        client: Optional[httpx.AsyncClient] = None,
        max_cache_entries: int = 128,
    ) -> None:
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._external_client = client
        self.max_cache_entries = max_cache_entries
        # Cache key: (round(lat, 4), round(lng, 4)) -> (timestamp, GeocodedAddress)
        self._geocode_cache: Dict[Tuple[float, float], Tuple[float, GeocodedAddress]] = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client:
            return self._external_client
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    def _get_cached_geocode(self, lat: float, lng: float) -> Optional[GeocodedAddress]:
        key = (round(lat, 4), round(lng, 4))
        if key in self._geocode_cache:
            ts, addr = self._geocode_cache[key]
            if time.time() - ts < self.cache_ttl_seconds:
                return addr
            else:
                del self._geocode_cache[key]
        return None

    def _store_cached_geocode(self, lat: float, lng: float, addr: GeocodedAddress) -> None:
        if len(self._geocode_cache) >= self.max_cache_entries:
            # Evict oldest entry
            oldest_key = min(self._geocode_cache.keys(), key=lambda k: self._geocode_cache[k][0])
            del self._geocode_cache[oldest_key]
        key = (round(lat, 4), round(lng, 4))
        self._geocode_cache[key] = (time.time(), addr)

    async def reverse_geocode(self, lat: float, lng: float) -> ReverseGeocodeResponse:
        """Resolve coordinates to human-readable address using Geocoding API."""
        is_valid, err = validate_coordinates(lat, lng)
        if not is_valid:
            return ReverseGeocodeResponse(
                status="error",
                latitude=lat,
                longitude=lng,
                details=err,
            )

        # Check cache
        cached = self._get_cached_geocode(lat, lng)
        if cached:
            logger.debug("Geocoding cache hit for %s", mask_coords(lat, lng))
            return ReverseGeocodeResponse(
                status="success",
                latitude=lat,
                longitude=lng,
                address=cached,
                details="Resolved from fresh in-memory cache",
            )

        params = {
            "latlng": f"{lat},{lng}",
            "key": self.api_key,
            "solution_id": GMP_SOLUTION_ID,
        }

        logger.info("Querying Google Geocoding API for %s", mask_coords(lat, lng))

        headers = {
            "X-Goog-Maps-Solution-ID": GMP_SOLUTION_ID,
        }

        try:
            client = self._get_client()
            should_close = self._external_client is None
            try:
                resp = await client.get(self.GEOCODING_URL, params=params, headers=headers)
            finally:
                if should_close:
                    await client.aclose()

            if resp.status_code != 200:
                logger.error("Geocoding API HTTP error: %s - %s", resp.status_code, resp.text)
                return ReverseGeocodeResponse(
                    status="error",
                    latitude=lat,
                    longitude=lng,
                    details=f"Google Geocoding API returned HTTP status {resp.status_code}",
                )

            data = resp.json()
            api_status = data.get("status")

            if api_status == "OK" and data.get("results"):
                top_result = data["results"][0]
                formatted = top_result.get("formatted_address", "")
                place_id = top_result.get("place_id")

                # Extract address components
                locality: Optional[str] = None
                sublocality: Optional[str] = None
                admin_area: Optional[str] = None
                country: Optional[str] = None
                postal_code: Optional[str] = None
                street_num: str = ""
                route: str = ""

                for comp in top_result.get("address_components", []):
                    types = comp.get("types", [])
                    name = comp.get("long_name", "")
                    if "street_number" in types:
                        street_num = name
                    elif "route" in types:
                        route = name
                    elif "locality" in types:
                        locality = name
                    elif "sublocality" in types or "sublocality_level_1" in types:
                        sublocality = name
                    elif "administrative_area_level_1" in types:
                        admin_area = name
                    elif "country" in types:
                        country = name
                    elif "postal_code" in types:
                        postal_code = name

                if not locality and sublocality:
                    locality = sublocality

                street = f"{street_num} {route}".strip() or None

                addr = GeocodedAddress(
                    formatted_address=formatted,
                    street=street,
                    locality=locality,
                    sublocality=sublocality,
                    admin_area=admin_area,
                    country=country,
                    postal_code=postal_code,
                    place_id=place_id,
                )

                self._store_cached_geocode(lat, lng, addr)
                return ReverseGeocodeResponse(
                    status="success",
                    latitude=lat,
                    longitude=lng,
                    address=addr,
                    details="Successfully resolved address from Google Maps Geocoding API",
                )

            elif api_status == "ZERO_RESULTS":
                return ReverseGeocodeResponse(
                    status="empty",
                    latitude=lat,
                    longitude=lng,
                    details="No address found for the given coordinates",
                )
            elif api_status == "OVER_QUERY_LIMIT":
                return ReverseGeocodeResponse(
                    status="rate_limited",
                    latitude=lat,
                    longitude=lng,
                    details="Google Maps API quota exceeded (OVER_QUERY_LIMIT)",
                )
            elif api_status == "REQUEST_DENIED":
                err_msg = data.get("error_message") or "Request denied by Google Maps"
                logger.error("Geocoding REQUEST_DENIED: %s", err_msg)
                return ReverseGeocodeResponse(
                    status="error",
                    latitude=lat,
                    longitude=lng,
                    details=f"Google Maps request denied: {err_msg}",
                )
            else:
                return ReverseGeocodeResponse(
                    status="error",
                    latitude=lat,
                    longitude=lng,
                    details=f"Geocoding provider returned status: {api_status}",
                )

        except httpx.TimeoutException:
            logger.warning("Geocoding request timed out for %s", mask_coords(lat, lng))
            return ReverseGeocodeResponse(
                status="error",
                latitude=lat,
                longitude=lng,
                details=f"Geocoding request timed out after {self.timeout_seconds}s",
            )
        except Exception as exc:
            logger.error("Geocoding request failed: %s", exc)
            return ReverseGeocodeResponse(
                status="error",
                latitude=lat,
                longitude=lng,
                details=f"Network error querying Geocoding API: {exc}",
            )

    async def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int = 1500,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10,
    ) -> NearbySearchResponse:
        """Search nearby places of interest using Google Places API (New)."""
        is_valid, err = validate_coordinates(lat, lng)
        if not is_valid:
            return NearbySearchResponse(
                status="error",
                center_lat=lat,
                center_lng=lng,
                radius_m=radius_m,
                details=err,
            )

        # Clamp radius between 50m and maximum configured radius
        clamped_radius = max(50, min(radius_m, settings.nearby_search_max_radius_m))
        # Clamp limit between 1 and 20
        clamped_limit = max(1, min(limit, 20))

        # Resolve category to Places API (New) type
        place_type: Optional[str] = None
        if category:
            cat_norm = category.lower().strip().replace(" ", "_")
            place_type = CATEGORY_TYPE_MAP.get(cat_norm, cat_norm)

        payload: Dict[str, Any] = {
            "maxResultCount": clamped_limit,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(clamped_radius),
                }
            },
        }

        if place_type:
            payload["includedTypes"] = [place_type]

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.id,"
                "places.displayName,"
                "places.formattedAddress,"
                "places.location,"
                "places.types,"
                "places.rating,"
                "places.googleMapsUri"
            ),
            "X-Goog-Maps-Solution-ID": GMP_SOLUTION_ID,
        }

        logger.info(
            "Querying Places API (New) searchNearby at %s (radius: %sm, type: %s)",
            mask_coords(lat, lng),
            clamped_radius,
            place_type or "all",
        )

        try:
            client = self._get_client()
            should_close = self._external_client is None
            try:
                resp = await client.post(self.PLACES_NEARBY_URL, json=payload, headers=headers)
            finally:
                if should_close:
                    await client.aclose()

            if resp.status_code == 400:
                logger.error("Places API 400: %s", resp.text)
                return NearbySearchResponse(
                    status="error",
                    query=keyword,
                    category=category,
                    center_lat=lat,
                    center_lng=lng,
                    radius_m=clamped_radius,
                    details=f"Invalid search request: {resp.text}",
                )
            elif resp.status_code == 403:
                logger.error("Places API 403: %s", resp.text)
                return NearbySearchResponse(
                    status="error",
                    query=keyword,
                    category=category,
                    center_lat=lat,
                    center_lng=lng,
                    radius_m=clamped_radius,
                    details="Google Places API request denied: invalid API key, missing Places API (New) enablement, or billing inactive.",
                )
            elif resp.status_code == 429:
                return NearbySearchResponse(
                    status="rate_limited",
                    query=keyword,
                    category=category,
                    center_lat=lat,
                    center_lng=lng,
                    radius_m=clamped_radius,
                    details="Google Places API quota or rate limit exceeded.",
                )
            elif resp.status_code != 200:
                return NearbySearchResponse(
                    status="error",
                    query=keyword,
                    category=category,
                    center_lat=lat,
                    center_lng=lng,
                    radius_m=clamped_radius,
                    details=f"Places API returned HTTP status {resp.status_code}",
                )

            data = resp.json()
            raw_places = data.get("places", [])

            if not raw_places:
                return NearbySearchResponse(
                    status="empty",
                    query=keyword,
                    category=category,
                    center_lat=lat,
                    center_lng=lng,
                    radius_m=clamped_radius,
                    places=[],
                    details=f"No places found matching '{category or keyword or 'places'}' within {clamped_radius}m.",
                )

            summaries: List[PlaceSummary] = []
            for p in raw_places:
                pid = p.get("id") or ""
                pname = p.get("displayName", {}).get("text") or "Unnamed Place"
                paddr = p.get("formattedAddress")
                ploc = p.get("location", {})
                plat = ploc.get("latitude")
                plng = ploc.get("longitude")

                if plat is None or plng is None:
                    continue

                pdist = haversine_distance_m(lat, lng, plat, plng)
                prating = p.get("rating")
                ptypes = p.get("types", [])
                puri = p.get("googleMapsUri")

                summaries.append(
                    PlaceSummary(
                        id=pid,
                        name=pname,
                        formatted_address=paddr,
                        latitude=plat,
                        longitude=plng,
                        types=ptypes,
                        rating=prating,
                        distance_m=pdist,
                        google_maps_uri=puri,
                    )
                )

            # Sort by ascending distance
            summaries.sort(key=lambda x: x.distance_m if x.distance_m is not None else float("inf"))

            return NearbySearchResponse(
                status="success",
                query=keyword,
                category=category,
                center_lat=lat,
                center_lng=lng,
                radius_m=clamped_radius,
                places=summaries,
                details=f"Found {len(summaries)} places via Google Places API (New)",
            )

        except httpx.TimeoutException:
            logger.warning("Places search timed out for %s", mask_coords(lat, lng))
            return NearbySearchResponse(
                status="error",
                query=keyword,
                category=category,
                center_lat=lat,
                center_lng=lng,
                radius_m=clamped_radius,
                details=f"Places search timed out after {self.timeout_seconds}s",
            )
        except Exception as exc:
            logger.error("Places search failed: %s", exc)
            return NearbySearchResponse(
                status="error",
                query=keyword,
                category=category,
                center_lat=lat,
                center_lng=lng,
                radius_m=clamped_radius,
                details=f"Network error querying Places API: {exc}",
            )


# ==============================================================================
# OpenStreetMap (OSM) Platform Integration (Phase 2D)
# ==============================================================================

class NominatimRateLimiter:
    """Async thread-safe rate limiter ensuring >= 1.0s between Nominatim requests.
    
    Complies strictly with the official OpenStreetMap Nominatim Usage Policy:
    'No more than 1 request per second'.
    """

    def __init__(self, min_interval_seconds: float = 1.0) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._lock = asyncio.Lock()
        self._last_request_time: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval_seconds:
                await asyncio.sleep(self.min_interval_seconds - elapsed)
            self._last_request_time = time.monotonic()


_global_nominatim_rate_limiter = NominatimRateLimiter(min_interval_seconds=settings.osm_rate_limit_seconds)

# OpenStreetMap Overpass category tag selectors
OSM_CATEGORY_TAG_MAP: Dict[str, List[str]] = {
    # Hospitals and clinics
    "hospital": ['["amenity"~"^(hospital|clinic)$"]'],
    "hospitals": ['["amenity"~"^(hospital|clinic)$"]'],
    "clinic": ['["amenity"~"^(hospital|clinic)$"]'],
    "clinics": ['["amenity"~"^(hospital|clinic)$"]'],
    
    # Pharmacies
    "pharmacy": ['["amenity"="pharmacy"]'],
    "pharmacies": ['["amenity"="pharmacy"]'],
    "chemist": ['["amenity"="pharmacy"]'],
    
    # Fuel stations and EV charging
    "fuel": ['["amenity"~"^(fuel|charging_station)$"]'],
    "gas": ['["amenity"~"^(fuel|charging_station)$"]'],
    "petrol": ['["amenity"~"^(fuel|charging_station)$"]'],
    "gas_station": ['["amenity"~"^(fuel|charging_station)$"]'],
    "petrol_station": ['["amenity"~"^(fuel|charging_station)$"]'],
    "charging_station": ['["amenity"~"^(fuel|charging_station)$"]'],
    "ev_charging": ['["amenity"~"^(fuel|charging_station)$"]'],
    
    # Cafes
    "cafe": ['["amenity"="cafe"]'],
    "cafes": ['["amenity"="cafe"]'],
    "coffee": ['["amenity"="cafe"]'],
    "coffee_shop": ['["amenity"="cafe"]'],
    
    # Restaurants
    "restaurant": ['["amenity"~"^(restaurant|fast_food)$"]'],
    "restaurants": ['["amenity"~"^(restaurant|fast_food)$"]'],
    "food": ['["amenity"~"^(restaurant|fast_food)$"]'],
    "fast_food": ['["amenity"~"^(restaurant|fast_food)$"]'],
    
    # Grocery stores and supermarkets
    "supermarket": ['["shop"~"^(supermarket|convenience|grocery)$"]'],
    "supermarkets": ['["shop"~"^(supermarket|convenience|grocery)$"]'],
    "grocery": ['["shop"~"^(supermarket|convenience|grocery)$"]'],
    "groceries": ['["shop"~"^(supermarket|convenience|grocery)$"]'],
    "convenience": ['["shop"~"^(supermarket|convenience|grocery)$"]'],
    
    # Ancillary categories for navigation bar consistency
    "bank": ['["amenity"="bank"]'],
    "atm": ['["amenity"="atm"]'],
    "police": ['["amenity"="police"]'],
    "lodging": ['["tourism"~"^(hotel|hostel|guest_house)$"]'],
    "hotel": ['["tourism"~"^(hotel|hostel|guest_house)$"]'],
}


def build_overpass_query(
    lat: float,
    lng: float,
    radius_m: int,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 15,
    timeout_seconds: int = 12,
) -> str:
    """Build a robust Overpass QL query with bounded radius and centroid output."""
    clean_kw = re.sub(r'["\\;]', '', keyword.strip()) if keyword else None
    kw_filter = f'["name"~"{clean_kw}",i]' if clean_kw else ''
    
    cat_key = category.strip().lower() if category else None
    selectors = OSM_CATEGORY_TAG_MAP.get(cat_key, [])
    
    clauses: List[str] = []
    if selectors:
        for sel in selectors:
            clauses.append(f"  nwr{sel}{kw_filter}(around:{radius_m},{lat},{lng});")
    elif kw_filter:
        clauses.append(f"  nwr{kw_filter}(around:{radius_m},{lat},{lng});")
    else:
        clauses.append(f"  nwr[\"amenity\"](around:{radius_m},{lat},{lng});")

    body_clauses = "\n".join(clauses)
    return (
        f"[out:json][timeout:{timeout_seconds}];\n"
        f"(\n"
        f"{body_clauses}\n"
        f");\n"
        f"out center body qt {limit};"
    )


class OpenStreetMapLocationEnricher(BaseLocationEnricher):
    """OpenStreetMap Location Intelligence Provider (Nominatim + Overpass API).
    
    Features:
    - Free and production-conscious; operates without paid API keys.
    - Honors Nominatim usage policy (<= 1 request/second) via NominatimRateLimiter.
    - Identifiable User-Agent with configurable contact details.
    - In-flight request deduplication and bounded in-memory caching.
    - Overpass API POI discovery across 6 primary categories with centroid coordinates.
    - Automatic secondary endpoint fallback on HTTP 429, 5xx, or network timeout.
    - Zero fabricated ratings, hours, or place attributes.
    - Full '© OpenStreetMap contributors' attribution in responses.
    """

    @property
    def is_configured(self) -> bool:
        """OSM requires no API key and is always ready if network is reachable."""
        return True

    @property
    def provider_name(self) -> str:
        return "OpenStreetMap"

    def __init__(
        self,
        nominatim_url: Optional[str] = None,
        overpass_url: Optional[str] = None,
        overpass_fallback_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        contact_email: Optional[str] = None,
        timeout_seconds: float = 12.0,
        cache_ttl_seconds: int = 600,
        rate_limiter: Optional[NominatimRateLimiter] = None,
        client: Optional[httpx.AsyncClient] = None,
        max_cache_entries: int = 128,
    ) -> None:
        self.nominatim_url = nominatim_url or settings.osm_nominatim_url
        self.overpass_url = overpass_url or settings.osm_overpass_url
        self.overpass_fallback_url = overpass_fallback_url or settings.osm_overpass_fallback_url
        self.user_agent = user_agent or settings.osm_user_agent
        self.contact_email = contact_email or settings.osm_contact_email
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._rate_limiter = rate_limiter or _global_nominatim_rate_limiter
        self._external_client = client
        self.max_cache_entries = max_cache_entries

        # Bounded caches
        self._geocode_cache: Dict[Tuple[float, float], Tuple[float, ReverseGeocodeResponse]] = {}
        self._nearby_cache: Dict[Tuple[float, float, str, str, int, int], Tuple[float, NearbySearchResponse]] = {}
        # In-flight request deduplication
        self._inflight_geocodes: Dict[Tuple[float, float], asyncio.Future[ReverseGeocodeResponse]] = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client:
            return self._external_client
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    def _build_user_agent(self) -> str:
        if self.contact_email and self.contact_email.strip():
            return f"{self.user_agent} ({self.contact_email.strip()})"
        return self.user_agent

    async def reverse_geocode(self, lat: float, lng: float) -> ReverseGeocodeResponse:
        """Resolve coordinates to address using Nominatim with rate limiting and deduplication."""
        is_valid, err = validate_coordinates(lat, lng)
        if not is_valid:
            return ReverseGeocodeResponse(
                status="error",
                latitude=lat,
                longitude=lng,
                details=err,
                provider=self.provider_name,
            )

        coord_key = (round(lat, 4), round(lng, 4))

        # 1. Check cache
        if coord_key in self._geocode_cache:
            ts, cached_resp = self._geocode_cache[coord_key]
            if time.time() - ts < self.cache_ttl_seconds:
                return cached_resp
            else:
                del self._geocode_cache[coord_key]

        # 2. In-flight request deduplication
        if coord_key in self._inflight_geocodes:
            return await self._inflight_geocodes[coord_key]

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ReverseGeocodeResponse] = loop.create_future()
        self._inflight_geocodes[coord_key] = future

        try:
            # 3. Acquire rate limiter (<= 1 req/sec)
            await self._rate_limiter.acquire()

            headers = {
                "User-Agent": self._build_user_agent(),
                "Accept": "application/json",
            }
            params = {
                "lat": str(lat),
                "lon": str(lng),
                "format": "jsonv2",
                "addressdetails": "1",
            }

            client = self._get_client()
            resp = await client.get(self.nominatim_url, params=params, headers=headers)

            if resp.status_code == 429:
                logger.warning("Nominatim rate limited (429) for %s", mask_coords(lat, lng))
                result = ReverseGeocodeResponse(
                    status="rate_limited",
                    latitude=lat,
                    longitude=lng,
                    details="Nominatim rate limit reached (HTTP 429). Please wait before requesting again.",
                    provider=self.provider_name,
                    attribution="© OpenStreetMap contributors",
                )
            elif resp.status_code >= 500:
                logger.warning("Nominatim server error (%s) for %s", resp.status_code, mask_coords(lat, lng))
                result = ReverseGeocodeResponse(
                    status="error",
                    latitude=lat,
                    longitude=lng,
                    details=f"Nominatim server error (HTTP {resp.status_code}).",
                    provider=self.provider_name,
                    attribution="© OpenStreetMap contributors",
                )
            elif resp.status_code != 200:
                result = ReverseGeocodeResponse(
                    status="error",
                    latitude=lat,
                    longitude=lng,
                    details=f"Nominatim returned unexpected HTTP {resp.status_code}.",
                    provider=self.provider_name,
                    attribution="© OpenStreetMap contributors",
                )
            else:
                data = resp.json()
                if "error" in data:
                    result = ReverseGeocodeResponse(
                        status="empty",
                        latitude=lat,
                        longitude=lng,
                        details=str(data["error"]),
                        provider=self.provider_name,
                        attribution="© OpenStreetMap contributors",
                    )
                else:
                    addr_dict = data.get("address", {})
                    road = addr_dict.get("road")
                    house_number = addr_dict.get("house_number")
                    street = f"{house_number} {road}".strip() if (house_number and road) else (road or house_number)
                    locality = (
                        addr_dict.get("city")
                        or addr_dict.get("town")
                        or addr_dict.get("village")
                        or addr_dict.get("municipality")
                        or addr_dict.get("hamlet")
                    )
                    sublocality = (
                        addr_dict.get("suburb")
                        or addr_dict.get("neighbourhood")
                        or addr_dict.get("quarter")
                        or addr_dict.get("city_district")
                    )
                    admin_area = (
                        addr_dict.get("state")
                        or addr_dict.get("state_district")
                        or addr_dict.get("county")
                        or addr_dict.get("region")
                    )
                    country = addr_dict.get("country")
                    postal_code = addr_dict.get("postcode")
                    osm_type = data.get("osm_type", "node")
                    osm_id = data.get("osm_id")
                    place_id = str(osm_id) if osm_id else str(data.get("place_id", ""))
                    osm_uri = f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else None

                    address_obj = GeocodedAddress(
                        formatted_address=data.get("display_name") or f"{lat:.4f}, {lng:.4f}",
                        street=street,
                        locality=locality,
                        sublocality=sublocality,
                        admin_area=admin_area,
                        country=country,
                        postal_code=postal_code,
                        place_id=place_id,
                    )
                    result = ReverseGeocodeResponse(
                        status="success",
                        latitude=lat,
                        longitude=lng,
                        address=address_obj,
                        provider=self.provider_name,
                        osm_uri=osm_uri,
                        attribution="© OpenStreetMap contributors",
                        details="Address resolved via OpenStreetMap Nominatim",
                    )

                    # Store in bounded cache
                    if len(self._geocode_cache) >= self.max_cache_entries:
                        oldest_key = min(self._geocode_cache.keys(), key=lambda k: self._geocode_cache[k][0])
                        del self._geocode_cache[oldest_key]
                    self._geocode_cache[coord_key] = (time.time(), result)

        except httpx.TimeoutException:
            logger.warning("Nominatim request timed out for %s", mask_coords(lat, lng))
            result = ReverseGeocodeResponse(
                status="timeout",
                latitude=lat,
                longitude=lng,
                details=f"Nominatim request timed out after {self.timeout_seconds}s.",
                provider=self.provider_name,
                attribution="© OpenStreetMap contributors",
            )
        except Exception as exc:
            logger.error("Nominatim request failed: %s", exc)
            result = ReverseGeocodeResponse(
                status="error",
                latitude=lat,
                longitude=lng,
                details=f"Network error querying Nominatim: {exc}",
                provider=self.provider_name,
                attribution="© OpenStreetMap contributors",
            )
        finally:
            future.set_result(result)
            self._inflight_geocodes.pop(coord_key, None)

        return result

    async def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int = 1500,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10,
    ) -> NearbySearchResponse:
        """Search nearby points of interest via Overpass API with endpoint fallback."""
        is_valid, err = validate_coordinates(lat, lng)
        if not is_valid:
            return NearbySearchResponse(
                status="error",
                center_lat=lat,
                center_lng=lng,
                radius_m=radius_m,
                details=err,
                provider=self.provider_name,
            )

        clamped_radius = max(50, min(radius_m, 10000))
        clamped_limit = max(1, min(limit, 25))

        cache_key = (
            round(lat, 3),
            round(lng, 3),
            (category or "").strip().lower(),
            (keyword or "").strip().lower(),
            clamped_radius,
            clamped_limit,
        )

        # Check cache
        if cache_key in self._nearby_cache:
            ts, cached_search = self._nearby_cache[cache_key]
            if time.time() - ts < self.cache_ttl_seconds:
                return cached_search
            else:
                del self._nearby_cache[cache_key]

        query = build_overpass_query(
            lat=lat,
            lng=lng,
            radius_m=clamped_radius,
            category=category,
            keyword=keyword,
            limit=clamped_limit,
            timeout_seconds=int(self.timeout_seconds),
        )

        headers = {
            "User-Agent": self._build_user_agent(),
        }
        data_payload = {"data": query}

        client = self._get_client()
        endpoints = [self.overpass_url]
        if self.overpass_fallback_url and self.overpass_fallback_url != self.overpass_url:
            endpoints.append(self.overpass_fallback_url)

        last_error: Optional[str] = None
        last_status_code: Optional[int] = None
        parsed_data: Optional[Dict[str, Any]] = None

        for endpoint in endpoints:
            try:
                resp = await client.post(endpoint, data=data_payload, headers=headers)
                last_status_code = resp.status_code

                if resp.status_code == 200:
                    try:
                        parsed_data = resp.json()
                        break  # Successful response
                    except Exception as json_err:
                        last_error = f"Malformed JSON from Overpass: {json_err}"
                        logger.warning("Overpass endpoint %s returned malformed JSON: %s", endpoint, json_err)
                elif resp.status_code == 429:
                    last_error = "Overpass API rate limit reached (HTTP 429)."
                    logger.warning("Overpass endpoint %s rate limited (429)", endpoint)
                elif resp.status_code >= 500:
                    last_error = f"Overpass server error (HTTP {resp.status_code})."
                    logger.warning("Overpass endpoint %s server error %d", endpoint, resp.status_code)
                else:
                    last_error = f"Overpass unexpected status code HTTP {resp.status_code}."
            except httpx.TimeoutException:
                last_error = f"Overpass request timed out after {self.timeout_seconds}s."
                logger.warning("Overpass endpoint %s timed out", endpoint)
            except Exception as exc:
                last_error = f"Connection error reaching Overpass ({endpoint}): {exc}"
                logger.warning("Overpass endpoint %s failed: %s", endpoint, exc)

        if parsed_data is None:
            if last_status_code == 429:
                return NearbySearchResponse(
                    status="rate_limited",
                    query=keyword,
                    category=category,
                    center_lat=lat,
                    center_lng=lng,
                    radius_m=clamped_radius,
                    places=[],
                    provider=self.provider_name,
                    attribution="© OpenStreetMap contributors",
                    details=last_error or "Overpass API rate limited. Please try again later.",
                )
            if "timed out" in (last_error or "").lower():
                return NearbySearchResponse(
                    status="timeout",
                    query=keyword,
                    category=category,
                    center_lat=lat,
                    center_lng=lng,
                    radius_m=clamped_radius,
                    places=[],
                    provider=self.provider_name,
                    attribution="© OpenStreetMap contributors",
                    details=last_error or "Places search timed out.",
                )
            return NearbySearchResponse(
                status="provider_error",
                query=keyword,
                category=category,
                center_lat=lat,
                center_lng=lng,
                radius_m=clamped_radius,
                places=[],
                provider=self.provider_name,
                attribution="© OpenStreetMap contributors",
                details=last_error or "Overpass API unavailable across primary and fallback endpoints.",
            )

        elements = parsed_data.get("elements", [])
        if not elements:
            empty_resp = NearbySearchResponse(
                status="empty",
                query=keyword,
                category=category,
                center_lat=lat,
                center_lng=lng,
                radius_m=clamped_radius,
                places=[],
                provider=self.provider_name,
                attribution="© OpenStreetMap contributors",
                details=f"No places found matching your filter within {clamped_radius}m.",
            )
            return empty_resp

        seen_ids = set()
        summaries: List[PlaceSummary] = []

        for elem in elements:
            elem_type = elem.get("type", "node")
            elem_id = elem.get("id")
            if not elem_id:
                continue

            dedup_key = (elem_type, elem_id)
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)

            # Coordinates: nodes have lat/lon; ways/relations have center.lat/center.lon
            elat = elem.get("lat") or (elem.get("center") or {}).get("lat")
            elng = elem.get("lon") or (elem.get("center") or {}).get("lon")
            if elat is None or elng is None:
                continue

            try:
                elem_lat = float(elat)
                elem_lng = float(elng)
            except (ValueError, TypeError):
                continue

            dist = haversine_distance_m(lat, lng, elem_lat, elem_lng)
            tags = elem.get("tags") or {}

            # Display name: tag 'name' or friendly tag descriptor
            name = tags.get("name")
            if not name:
                amenity_val = tags.get("amenity") or tags.get("shop") or tags.get("tourism") or "Place"
                name = f"{amenity_val.replace('_', ' ').title()} (Unnamed)"

            # Construct human-readable address if available from tags
            housenumber = tags.get("addr:housenumber")
            street_name = tags.get("addr:street")
            city_name = tags.get("addr:city") or tags.get("addr:suburb")
            postcode = tags.get("addr:postcode")

            addr_parts = []
            if housenumber and street_name:
                addr_parts.append(f"{housenumber} {street_name}")
            elif street_name:
                addr_parts.append(street_name)
            elif housenumber:
                addr_parts.append(housenumber)

            if city_name:
                addr_parts.append(city_name)
            if postcode:
                addr_parts.append(postcode)

            formatted_address = ", ".join(addr_parts) if addr_parts else None

            # Types: collect standard tags
            types: List[str] = []
            for k in ["amenity", "shop", "tourism", "healthcare"]:
                v = tags.get(k)
                if v and v not in types:
                    types.append(v)
            if not types and category:
                types.append(category)

            osm_uri = f"https://www.openstreetmap.org/{elem_type}/{elem_id}"

            summaries.append(
                PlaceSummary(
                    id=f"osm_{elem_type}_{elem_id}",
                    name=name,
                    formatted_address=formatted_address,
                    latitude=elem_lat,
                    longitude=elem_lng,
                    types=types,
                    rating=None,  # Real OSM data has no ratings; never fabricate
                    distance_m=dist,
                    google_maps_uri=None,
                    osm_uri=osm_uri,
                    attribution="© OpenStreetMap contributors",
                )
            )

        # Sort by distance from search center
        summaries.sort(key=lambda p: (p.distance_m if p.distance_m is not None else float("inf")))
        limited_summaries = summaries[:clamped_limit]

        final_response = NearbySearchResponse(
            status="success",
            query=keyword,
            category=category,
            center_lat=lat,
            center_lng=lng,
            radius_m=clamped_radius,
            places=limited_summaries,
            provider=self.provider_name,
            attribution="© OpenStreetMap contributors",
            details=f"Found {len(limited_summaries)} places via OpenStreetMap Overpass",
        )

        # Store in cache
        if len(self._nearby_cache) >= self.max_cache_entries:
            oldest_key = min(self._nearby_cache.keys(), key=lambda k: self._nearby_cache[k][0])
            del self._nearby_cache[oldest_key]
        self._nearby_cache[cache_key] = (time.time(), final_response)

        return final_response


def get_location_enricher(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> BaseLocationEnricher:
    """Factory creating the appropriate enricher based on environment configuration.
    
    Supports:
    - 'osm': Free OpenStreetMap (Nominatim + Overpass API)
    - 'google': Google Maps Platform (Geocoding + Places API New)
    - 'none': No-op offline fallback
    """
    prov = (provider if provider is not None else settings.location_provider).strip().lower()
    if prov == "osm":
        return OpenStreetMapLocationEnricher(
            nominatim_url=settings.osm_nominatim_url,
            overpass_url=settings.osm_overpass_url,
            overpass_fallback_url=settings.osm_overpass_fallback_url,
            user_agent=settings.osm_user_agent,
            contact_email=settings.osm_contact_email,
            timeout_seconds=settings.osm_timeout_seconds,
            cache_ttl_seconds=settings.osm_cache_ttl_seconds,
            client=client,
        )
    elif prov == "google":
        key = api_key if api_key is not None else settings.google_maps_api_key
        if key and key.strip():
            return GoogleMapsLocationEnricher(
                api_key=key.strip(),
                timeout_seconds=settings.google_maps_timeout_seconds,
                cache_ttl_seconds=settings.geocoding_cache_ttl_seconds,
                client=client,
            )
        return NoOpLocationEnricher()
    elif prov == "none":
        return NoOpLocationEnricher()

    return NoOpLocationEnricher()

