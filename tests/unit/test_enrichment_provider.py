"""Unit tests for Location Enrichment Providers (NoOp & Google Maps Platform).

All Google API requests are strictly mocked using httpx MockTransport.
Zero live or paid API requests are made during testing.
"""

import json
import pytest
import httpx

from schemas.contracts import ReverseGeocodeResponse, NearbySearchResponse
from backend.friday.location.enrichment import (
    NoOpLocationEnricher,
    GoogleMapsLocationEnricher,
    validate_coordinates,
    haversine_distance_m,
    mask_coords,
    GMP_SOLUTION_ID,
)


def test_validate_coordinates_valid():
    ok, err = validate_coordinates(28.6139, 77.2090)
    assert ok is True
    assert err is None


def test_validate_coordinates_invalid():
    ok, err = validate_coordinates(95.0, 77.0)
    assert ok is False
    assert "Latitude" in err

    ok, err = validate_coordinates(28.0, 195.0)
    assert ok is False
    assert "Longitude" in err

    ok, err = validate_coordinates("invalid", 77.0)
    assert ok is False


def test_haversine_distance_calculation():
    # Distance between New Delhi (28.6139, 77.2090) and Connaught Place (28.6315, 77.2167) ~2km
    dist = haversine_distance_m(28.6139, 77.2090, 28.6315, 77.2167)
    assert 1800 < dist < 2200

    # Distance to self is 0
    assert haversine_distance_m(12.34, 56.78, 12.34, 56.78) == 0.0


def test_mask_coords_privacy():
    masked = mask_coords(28.613928, 77.209015)
    assert masked == "(28.***, 77.***)"


@pytest.mark.asyncio
async def test_noop_enricher_reverse_geocode_honesty():
    enricher = NoOpLocationEnricher()
    assert enricher.is_configured is False
    assert enricher.provider_name == "None"

    res = await enricher.reverse_geocode(28.6139, 77.2090)
    assert isinstance(res, ReverseGeocodeResponse)
    assert res.status == "provider_not_configured"
    assert res.address is None
    assert "not configured" in (res.details or "")


@pytest.mark.asyncio
async def test_noop_enricher_search_nearby_honesty():
    enricher = NoOpLocationEnricher()
    res = await enricher.search_nearby(28.6139, 77.2090, category="hospital")
    assert isinstance(res, NearbySearchResponse)
    assert res.status == "provider_not_configured"
    assert res.places == []
    assert "not configured" in (res.details or "")


@pytest.mark.asyncio
async def test_google_maps_reverse_geocode_success_mocked():
    geocode_payload = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "Connaught Place, New Delhi, Delhi 110001, India",
                "place_id": "ChIJ12345ABCD",
                "address_components": [
                    {"long_name": "Connaught Place", "types": ["sublocality", "political"]},
                    {"long_name": "New Delhi", "types": ["locality", "political"]},
                    {"long_name": "Delhi", "types": ["administrative_area_level_1", "political"]},
                    {"long_name": "India", "types": ["country", "political"]},
                    {"long_name": "110001", "types": ["postal_code"]},
                ],
            }
        ],
    }

    recorded_requests = []

    def handle_request(request: httpx.Request):
        recorded_requests.append(request)
        return httpx.Response(200, json=geocode_payload)

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    enricher = GoogleMapsLocationEnricher(
        api_key="AIzaFakeKeyForMockTestingOnly",
        timeout_seconds=5.0,
        cache_ttl_seconds=300,
        client=client,
    )

    res = await enricher.reverse_geocode(28.6139, 77.2090)
    assert res.status == "success"
    assert res.address is not None
    assert res.address.formatted_address == "Connaught Place, New Delhi, Delhi 110001, India"
    assert res.address.locality == "New Delhi"
    assert res.address.country == "India"
    assert res.address.postal_code == "110001"

    # Check request headers
    assert len(recorded_requests) == 1
    req = recorded_requests[0]
    assert req.headers.get("X-Goog-Maps-Solution-ID") == GMP_SOLUTION_ID


@pytest.mark.asyncio
async def test_google_maps_caching_avoids_redundant_calls():
    geocode_payload = {
        "status": "OK",
        "results": [{"formatted_address": "Cached Location, City, Country", "place_id": "ch1"}],
    }

    call_count = 0

    def handle_request(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=geocode_payload)

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    enricher = GoogleMapsLocationEnricher(
        api_key="AIzaFakeKeyForMockTestingOnly",
        timeout_seconds=5.0,
        cache_ttl_seconds=300,
        client=client,
    )

    # First call
    res1 = await enricher.reverse_geocode(28.61390, 77.20900)
    assert res1.status == "success"
    assert call_count == 1

    # Second call within cache key rounding resolution (same 4 decimals)
    res2 = await enricher.reverse_geocode(28.61391, 77.20901)
    assert res2.status == "success"
    assert call_count == 1  # Did not make second network call


@pytest.mark.asyncio
async def test_google_maps_reverse_geocode_zero_results():
    payload = {"status": "ZERO_RESULTS", "results": []}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    client = httpx.AsyncClient(transport=transport)

    enricher = GoogleMapsLocationEnricher(api_key="AIzaFakeKey", client=client)
    res = await enricher.reverse_geocode(0.0, 0.0)
    assert res.status == "empty"
    assert res.address is None


@pytest.mark.asyncio
async def test_google_maps_reverse_geocode_rate_limited():
    payload = {"status": "OVER_QUERY_LIMIT", "error_message": "Quota exceeded"}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    client = httpx.AsyncClient(transport=transport)

    enricher = GoogleMapsLocationEnricher(api_key="AIzaFakeKey", client=client)
    res = await enricher.reverse_geocode(28.6139, 77.2090)
    assert res.status == "rate_limited"


@pytest.mark.asyncio
async def test_google_maps_search_nearby_success_mocked():
    places_payload = {
        "places": [
            {
                "id": "place_apollo_1",
                "displayName": {"text": "Apollo Pharmacy CP"},
                "formattedAddress": "Block E, Connaught Place, New Delhi",
                "location": {"latitude": 28.6320, "longitude": 77.2170},
                "types": ["pharmacy", "health", "point_of_interest"],
                "rating": 4.6,
                "googleMapsUri": "https://maps.google.com/?cid=111",
            },
            {
                "id": "place_fortis_2",
                "displayName": {"text": "Fortis Clinic"},
                "formattedAddress": "Barakhamba Road, New Delhi",
                "location": {"latitude": 28.6290, "longitude": 77.2250},
                "types": ["hospital", "health"],
                "rating": 4.2,
                "googleMapsUri": "https://maps.google.com/?cid=222",
            },
        ]
    }

    recorded_headers = {}

    def handle_request(request: httpx.Request):
        nonlocal recorded_headers
        recorded_headers = dict(request.headers)
        return httpx.Response(200, json=places_payload)

    transport = httpx.MockTransport(handle_request)
    client = httpx.AsyncClient(transport=transport)

    enricher = GoogleMapsLocationEnricher(
        api_key="AIzaFakeKey",
        client=client,
    )

    res = await enricher.search_nearby(
        lat=28.6139,
        lng=77.2090,
        category="pharmacy",
        radius_m=2000,
        limit=5,
    )

    assert res.status == "success"
    assert len(res.places) == 2
    assert res.places[0].name == "Apollo Pharmacy CP"
    assert res.places[0].distance_m is not None
    assert res.places[0].distance_m > 0
    assert res.places[0].google_maps_uri == "https://maps.google.com/?cid=111"

    # Verify Places API (New) required headers
    assert recorded_headers.get("x-goog-maps-solution-id") == GMP_SOLUTION_ID
    assert "places.displayName" in recorded_headers.get("x-goog-fieldmask", "")
    assert "places.location" in recorded_headers.get("x-goog-fieldmask", "")
