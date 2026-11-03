"""Unit tests for OpenStreetMap Location Intelligence Provider (Phase 2D).

Verifies Nominatim reverse geocoding, Overpass API POI search, rate limiting,
request deduplication, bounded caching, fallback endpoints, error mapping,
broker authorization, and attribution.

All external requests are 100% mocked with httpx.MockTransport.
Zero live or paid network requests are performed.
"""

import asyncio
import time
import pytest
import httpx

from schemas.contracts import (
    PermissionType,
    SessionPolicy,
    ToolCallProposal,
)
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.places_tool import ReverseGeocodeTool, SearchNearbyPlacesTool
from backend.friday.location.enrichment import (
    NominatimRateLimiter,
    OpenStreetMapLocationEnricher,
    build_overpass_query,
    get_location_enricher,
    NoOpLocationEnricher,
    GoogleMapsLocationEnricher,
    validate_coordinates,
)


# ------------------------------------------------------------------------------
# 1. Nominatim Rate Limiter Unit Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nominatim_rate_limiter_enforces_interval():
    """Verify rate limiter enforces minimum elapsed time between acquires."""
    limiter = NominatimRateLimiter(min_interval_seconds=0.1)

    t0 = time.monotonic()
    await limiter.acquire()
    t1 = time.monotonic()
    await limiter.acquire()
    t2 = time.monotonic()

    # Second acquire must have waited at least 0.09s
    assert (t2 - t1) >= 0.08
    assert (t2 - t0) >= 0.08


# ------------------------------------------------------------------------------
# 2. Nominatim Reverse Geocoding Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nominatim_reverse_geocode_success():
    """Verify Nominatim 200 OK parsing, address extraction, osm_uri, and attribution."""
    nominatim_payload = {
        "place_id": 1234567,
        "osm_type": "way",
        "osm_id": 987654321,
        "lat": "28.6139",
        "lon": "77.2090",
        "display_name": "Rajpath, Central Secretariat, New Delhi, Delhi, 110001, India",
        "address": {
            "road": "Rajpath",
            "neighbourhood": "Central Secretariat",
            "city": "New Delhi",
            "state": "Delhi",
            "postcode": "110001",
            "country": "India",
        },
    }

    recorded_headers = {}

    def handle_request(request: httpx.Request):
        nonlocal recorded_headers
        recorded_headers = dict(request.headers)
        return httpx.Response(200, json=nominatim_payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    limiter = NominatimRateLimiter(min_interval_seconds=0.0)

    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=limiter,
        user_agent="FRIDAY-Test/1.0",
        contact_email="test@example.com",
    )

    res = await enricher.reverse_geocode(28.6139, 77.2090)

    assert res.status == "success"
    assert res.provider == "OpenStreetMap"
    assert res.attribution == "© OpenStreetMap contributors"
    assert res.osm_uri == "https://www.openstreetmap.org/way/987654321"
    assert res.address is not None
    assert res.address.formatted_address == "Rajpath, Central Secretariat, New Delhi, Delhi, 110001, India"
    assert res.address.street == "Rajpath"
    assert res.address.locality == "New Delhi"
    assert res.address.admin_area == "Delhi"
    assert res.address.country == "India"
    assert res.address.postal_code == "110001"

    # Verify user agent includes contact info
    ua = recorded_headers.get("user-agent", "")
    assert "FRIDAY-Test/1.0" in ua
    assert "test@example.com" in ua


@pytest.mark.asyncio
async def test_nominatim_reverse_geocode_empty_result():
    """Verify Nominatim response with error object yields status='empty'."""
    def handle_request(request: httpx.Request):
        return httpx.Response(200, json={"error": "Unable to geocode"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    res = await enricher.reverse_geocode(0.0, 0.0)
    assert res.status == "empty"
    assert "Unable to geocode" in (res.details or "")
    assert res.address is None


@pytest.mark.asyncio
async def test_nominatim_reverse_geocode_rate_limited_429():
    """Verify HTTP 429 maps to status='rate_limited'."""
    def handle_request(request: httpx.Request):
        return httpx.Response(429, text="Too Many Requests")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    res = await enricher.reverse_geocode(28.6139, 77.2090)
    assert res.status == "rate_limited"
    assert "rate limit" in (res.details or "").lower()


@pytest.mark.asyncio
async def test_nominatim_reverse_geocode_server_error_500():
    """Verify HTTP 500 maps to status='error'."""
    def handle_request(request: httpx.Request):
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    res = await enricher.reverse_geocode(28.6139, 77.2090)
    assert res.status == "error"
    assert "server error" in (res.details or "").lower()


@pytest.mark.asyncio
async def test_nominatim_reverse_geocode_timeout():
    """Verify request timeout maps to status='timeout'."""
    def handle_request(request: httpx.Request):
        raise httpx.TimeoutException("Read timed out")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    res = await enricher.reverse_geocode(28.6139, 77.2090)
    assert res.status == "timeout"
    assert "timed out" in (res.details or "").lower()


@pytest.mark.asyncio
async def test_nominatim_caching_and_ttl_expiry():
    """Verify cache hits prevent duplicate network calls and TTL expiry triggers re-fetch."""
    call_count = 0

    def handle_request(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "place_id": 1,
                "osm_type": "node",
                "osm_id": 100 + call_count,
                "display_name": f"Location Fix #{call_count}",
                "address": {"city": "City"},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
        cache_ttl_seconds=1,  # Short 1-second TTL
    )

    # First call: network hit
    res1 = await enricher.reverse_geocode(28.6139, 77.2090)
    assert call_count == 1
    assert "Fix #1" in res1.address.formatted_address

    # Second call (immediate): cache hit, no network call
    res2 = await enricher.reverse_geocode(28.6139, 77.2090)
    assert call_count == 1
    assert "Fix #1" in res2.address.formatted_address

    # Wait for TTL expiry
    await asyncio.sleep(1.1)

    # Third call: cache expired, re-fetches
    res3 = await enricher.reverse_geocode(28.6139, 77.2090)
    assert call_count == 2
    assert "Fix #2" in res3.address.formatted_address


@pytest.mark.asyncio
async def test_nominatim_inflight_request_deduplication():
    """Verify identical concurrent requests deduplicate into a single in-flight network call."""
    call_count = 0

    def handle_request(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "place_id": 99,
                "osm_type": "node",
                "osm_id": 999,
                "display_name": "Deduplicated Address",
                "address": {"city": "New Delhi"},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    # Fire two concurrent reverse geocode calls for the exact same coords
    res1, res2 = await asyncio.gather(
        enricher.reverse_geocode(28.6139, 77.2090),
        enricher.reverse_geocode(28.6139, 77.2090),
    )

    assert call_count == 1  # Only ONE network call made!
    assert res1.status == "success"
    assert res2.status == "success"
    assert res1.address.formatted_address == "Deduplicated Address"
    assert res2.address.formatted_address == "Deduplicated Address"


# ------------------------------------------------------------------------------
# 3. Overpass Query Construction & Category Mapping
# ------------------------------------------------------------------------------

def test_overpass_query_building():
    """Verify Overpass QL query construction across supported categories."""
    # Hospital category
    q_hosp = build_overpass_query(28.61, 77.20, 1500, category="hospital")
    assert 'nwr["amenity"~"^(hospital|clinic)$"]' in q_hosp
    assert "(around:1500,28.61,77.2)" in q_hosp
    assert "out center body qt 15;" in q_hosp

    # Pharmacy category
    q_pharm = build_overpass_query(28.61, 77.20, 1000, category="pharmacy")
    assert 'nwr["amenity"="pharmacy"]' in q_pharm

    # Fuel / EV
    q_fuel = build_overpass_query(28.61, 77.20, 2000, category="gas_station")
    assert 'nwr["amenity"~"^(fuel|charging_station)$"]' in q_fuel

    # Cafe
    q_cafe = build_overpass_query(28.61, 77.20, 500, category="cafe")
    assert 'nwr["amenity"="cafe"]' in q_cafe

    # Restaurant
    q_rest = build_overpass_query(28.61, 77.20, 1200, category="restaurant")
    assert 'nwr["amenity"~"^(restaurant|fast_food)$"]' in q_rest

    # Supermarket / grocery
    q_super = build_overpass_query(28.61, 77.20, 3000, category="supermarket")
    assert 'nwr["shop"~"^(supermarket|convenience|grocery)$"]' in q_super

    # Keyword filter with sanitization
    q_kw = build_overpass_query(28.61, 77.20, 1500, category="cafe", keyword='Costa "Coffee";')
    assert '["name"~"Costa Coffee",i]' in q_kw


# ------------------------------------------------------------------------------
# 4. Overpass Nearby Place Search Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overpass_search_nearby_success():
    """Verify Overpass result parsing for nodes and ways, distance calculation, and zero fake ratings."""
    overpass_payload = {
        "elements": [
            {
                "type": "node",
                "id": 101,
                "lat": 28.6150,
                "lon": 77.2100,
                "tags": {
                    "name": "City Care Hospital",
                    "amenity": "hospital",
                    "addr:street": "Health Way",
                    "addr:housenumber": "10",
                    "addr:city": "New Delhi",
                },
            },
            {
                "type": "way",
                "id": 202,
                # Way with center coordinates
                "center": {"lat": 28.6200, "lon": 77.2150},
                "tags": {
                    "name": "Central Clinic",
                    "amenity": "clinic",
                    "addr:street": "Clinic Road",
                },
            },
            {
                "type": "node",
                "id": 303,
                # Unnamed place
                "lat": 28.6180,
                "lon": 77.2120,
                "tags": {
                    "amenity": "hospital",
                },
            },
        ]
    }

    def handle_request(request: httpx.Request):
        return httpx.Response(200, json=overpass_payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(client=client)

    res = await enricher.search_nearby(
        lat=28.6139,
        lng=77.2090,
        category="hospital",
        radius_m=1500,
        limit=5,
    )

    assert res.status == "success"
    assert res.provider == "OpenStreetMap"
    assert res.attribution == "© OpenStreetMap contributors"
    assert len(res.places) == 3

    # Sorted ascending by distance
    p1 = res.places[0]
    p2 = res.places[1]
    p3 = res.places[2]
    assert p1.distance_m <= p2.distance_m <= p3.distance_m

    # First place (node)
    assert p1.id == "osm_node_101"
    assert p1.name == "City Care Hospital"
    assert p1.formatted_address == "10 Health Way, New Delhi"
    assert p1.rating is None  # Honest: no fake ratings!
    assert p1.osm_uri == "https://www.openstreetmap.org/node/101"

    # Second place (way with center)
    assert p2.name in ("Central Clinic", "Hospital (Unnamed)")
    assert p2.rating is None

    # Unnamed place gets clean descriptor
    assert any("Unnamed" in p.name for p in res.places)


@pytest.mark.asyncio
async def test_overpass_search_nearby_fallback_endpoint_recovery():
    """Verify automatic switch to fallback endpoint when primary endpoint fails."""
    primary_called = False
    fallback_called = False

    def handle_request(request: httpx.Request):
        nonlocal primary_called, fallback_called
        url = str(request.url)
        if "primary" in url or "overpass-api.de" in url:
            primary_called = True
            return httpx.Response(504, text="Gateway Timeout")
        elif "fallback" in url or "kumi.systems" in url:
            fallback_called = True
            return httpx.Response(
                200,
                json={
                    "elements": [
                        {
                            "type": "node",
                            "id": 555,
                            "lat": 28.6140,
                            "lon": 77.2095,
                            "tags": {"name": "Fallback Pharmacy", "amenity": "pharmacy"},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        overpass_url="https://overpass-api.de/api/interpreter",
        overpass_fallback_url="https://overpass.kumi.systems/api/interpreter",
        client=client,
    )

    res = await enricher.search_nearby(
        lat=28.6139,
        lng=77.2090,
        category="pharmacy",
        radius_m=1000,
    )

    assert primary_called is True
    assert fallback_called is True
    assert res.status == "success"
    assert len(res.places) == 1
    assert res.places[0].name == "Fallback Pharmacy"


@pytest.mark.asyncio
async def test_overpass_search_nearby_empty_and_rate_limited():
    """Verify empty results and rate limit responses."""
    # Case 1: Empty results
    def handle_empty(request: httpx.Request):
        return httpx.Response(200, json={"elements": []})

    client_empty = httpx.AsyncClient(transport=httpx.MockTransport(handle_empty))
    enricher_empty = OpenStreetMapLocationEnricher(client=client_empty)
    res_empty = await enricher_empty.search_nearby(28.6139, 77.2090, category="hospital")
    assert res_empty.status == "empty"
    assert len(res_empty.places) == 0

    # Case 2: 429 Rate limited on all endpoints
    def handle_429(request: httpx.Request):
        return httpx.Response(429, text="Too Many Requests")

    client_429 = httpx.AsyncClient(transport=httpx.MockTransport(handle_429))
    enricher_429 = OpenStreetMapLocationEnricher(client=client_429)
    res_429 = await enricher_429.search_nearby(28.6139, 77.2090, category="hospital")
    assert res_429.status == "rate_limited"


# ------------------------------------------------------------------------------
# 5. Factory Selection and Broker Permission Enforcement
# ------------------------------------------------------------------------------

def test_get_location_enricher_provider_selection():
    """Verify factory returns appropriate enricher according to provider configuration."""
    # Explicit OSM
    osm_enricher = get_location_enricher(provider="osm")
    assert isinstance(osm_enricher, OpenStreetMapLocationEnricher)
    assert osm_enricher.provider_name == "OpenStreetMap"
    assert osm_enricher.is_configured is True

    # Explicit none
    noop_enricher = get_location_enricher(provider="none")
    assert isinstance(noop_enricher, NoOpLocationEnricher)
    assert noop_enricher.provider_name == "None"
    assert noop_enricher.is_configured is False

    # Explicit google without key -> NoOp
    g_noop = get_location_enricher(provider="google", api_key="")
    assert isinstance(g_noop, NoOpLocationEnricher)

    # Explicit google with key -> GoogleMapsLocationEnricher
    g_enricher = get_location_enricher(provider="google", api_key="AIzaValidKey")
    assert isinstance(g_enricher, GoogleMapsLocationEnricher)
    assert g_enricher.provider_name == "GoogleMaps"
    assert g_enricher.is_configured is True


@pytest.mark.asyncio
async def test_osm_tools_with_capability_broker():
    """Verify Capability Broker governs ReverseGeocodeTool and SearchNearbyPlacesTool with OSM enricher."""
    osm_payload = {
        "place_id": 1,
        "osm_type": "node",
        "osm_id": 999,
        "display_name": "Broker Authorized Location, New Delhi",
        "address": {"city": "New Delhi", "country": "India"},
    }

    def handle_request(request: httpx.Request):
        return httpx.Response(200, json=osm_payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    enricher = OpenStreetMapLocationEnricher(
        client=client,
        rate_limiter=NominatimRateLimiter(min_interval_seconds=0.0),
    )

    registry = ToolRegistry()
    registry.register(ReverseGeocodeTool(enricher=enricher))
    registry.register(SearchNearbyPlacesTool(enricher=enricher))

    # 1. Denied when PLACES_SEARCH permission missing
    unauthorized_policy = SessionPolicy(
        allowed_permissions={PermissionType.SYSTEM_TIME},
        places_search_enabled=True,
        allowed_workspace_root="/tmp",
    )
    broker_unauth = CapabilityBroker(registry=registry, session_policy=unauthorized_policy)
    prop = ToolCallProposal(tool_name="reverse_geocode", arguments={"latitude": 28.6139, "longitude": 77.2090})
    decision = broker_unauth.evaluate(prop)
    assert decision.allowed is False
    assert "lacks required permission 'places:search'" in decision.reason

    # 2. Allowed when authorized
    authorized_policy = SessionPolicy(
        allowed_permissions={PermissionType.PLACES_SEARCH},
        places_search_enabled=True,
        allowed_workspace_root="/tmp",
    )
    broker_auth = CapabilityBroker(registry=registry, session_policy=authorized_policy)
    decision_ok = broker_auth.evaluate(prop)
    assert decision_ok.allowed is True

    # 3. Execution produces genuine OSM output
    tool = registry.get("reverse_geocode")
    output = await tool.execute({"latitude": 28.6139, "longitude": 77.2090})
    assert output["ok"] is True
    assert output["status"] == "success"
    assert output["provider"] == "OpenStreetMap"
    assert output["formatted_address"] == "Broker Authorized Location, New Delhi"

    # 4. Independent verification succeeds
    is_verified, reason = await tool.verify({"latitude": 28.6139, "longitude": 77.2090}, output)
    assert is_verified is True
    assert "Verified address resolution" in reason
