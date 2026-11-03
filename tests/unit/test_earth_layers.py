"""Satellites, flights, launches, fires: parsing, honesty on failure, and orbital math."""

import math
from datetime import datetime, timezone

import httpx
import pytest

from schemas.contracts import ProviderStatus
from backend.friday.world.cache import WorldDataCache
from backend.friday.world.fires import FireProvider, parse_firms_csv
from backend.friday.world.flights import FlightProvider, parse_aircraft
from backend.friday.world.launches import LaunchProvider, parse_launch
from backend.friday.world.satellites import SatelliteProvider, orbit_class, teme_to_geodetic

ISS_OMM = {
    "OBJECT_NAME": "ISS (ZARYA)", "OBJECT_ID": "1998-067A", "EPOCH": "2026-10-28T14:18:15.597504",
    "MEAN_MOTION": 15.49090321, "ECCENTRICITY": 0.00069949, "INCLINATION": 51.6336, "RA_OF_ASC_NODE": 359.9178,
    "ARG_OF_PERICENTER": 320.4528, "MEAN_ANOMALY": 39.5949, "EPHEMERIS_TYPE": 0, "CLASSIFICATION_TYPE": "U",
    "NORAD_CAT_ID": 25544, "ELEMENT_SET_NO": 999, "REV_AT_EPOCH": 59243, "BSTAR": 0.00011161276,
    "MEAN_MOTION_DOT": 5.724e-5, "MEAN_MOTION_DDOT": 0,
}


def transport(handler):
    return httpx.MockTransport(handler)


def test_teme_to_geodetic_equator_and_pole():
    lat, lng, alt = teme_to_geodetic((6378.137 + 400, 0.0, 0.0), 2451545.0)
    assert abs(lat) < 1e-6 and abs(alt - 400) < 1e-6
    lat, _, alt = teme_to_geodetic((0.0, 0.0, 6356.7523 + 500), 2451545.0)
    assert abs(lat - 90) < 1e-3 and abs(alt - 500) < 0.5


def test_orbit_class():
    assert orbit_class(420, 0.0007) == "LEO"
    assert orbit_class(20200, 0.01) == "MEO"
    assert orbit_class(35786, 0.0002) == "GEO"
    assert orbit_class(1000, 0.7) == "HEO"


@pytest.mark.asyncio
async def test_satellite_positions_are_propagated_and_plausible():
    t = transport(lambda req: httpx.Response(200, json=[ISS_OMM]))
    prov = SatelliteProvider(cache=WorldDataCache(), transport=t, groups=["stations"])
    res = await prov.get_positions(at=datetime(2026, 10, 29, 14, 25, 15, tzinfo=timezone.utc))
    assert res.status == ProviderStatus.OK and res.count == 1
    iss = res.satellites[0]
    assert 380 < iss.altitude_km < 460
    assert abs(iss.latitude) <= 51.7  # can never exceed its inclination
    assert 7.5 < iss.velocity_kms < 7.8
    assert iss.orbit_class == "LEO" and iss.period_min == pytest.approx(93.0, abs=0.2)
    # Cross-checked live against wheretheiss.at on 2026-10-29 14:25:15Z: −21.40°, −61.33°.
    assert abs(iss.latitude - (-21.4)) < 1.5 and abs(iss.longitude - (-61.33)) < 2.5


@pytest.mark.asyncio
async def test_satellite_track_spans_both_directions():
    t = transport(lambda req: httpx.Response(200, json=[ISS_OMM]))
    prov = SatelliteProvider(cache=WorldDataCache(), transport=t, groups=["stations"])
    track = await prov.get_track(25544, minutes=10)
    assert track.status == ProviderStatus.OK and len(track.points) == 21
    missing = await prov.get_track(1)
    assert missing.status == ProviderStatus.EMPTY and missing.points == []


@pytest.mark.asyncio
async def test_satellites_report_upstream_failure_without_data():
    t = transport(lambda req: httpx.Response(503))
    res = await SatelliteProvider(cache=WorldDataCache(), transport=t, groups=["stations"]).get_positions()
    assert res.status == ProviderStatus.PROVIDER_ERROR and res.count == 0


def test_parse_aircraft_filters_stale_and_positionless():
    ok = parse_aircraft({"hex": "aa6b9f", "flight": "UAL932  ", "lat": 51.6, "lon": -2.9, "alt_baro": 39000, "gs": 510.5, "track": 98.4, "seen_pos": 0.3, "emergency": "none", "type": "adsb_icao"})
    assert ok.callsign == "UAL932" and ok.altitude_ft == 39000 and ok.emergency is None
    ground = parse_aircraft({"hex": "x", "lat": 51.4, "lon": -0.4, "alt_baro": "ground"})
    assert ground.on_ground and ground.altitude_ft is None
    assert parse_aircraft({"hex": "y", "alt_baro": 1000}) is None
    assert parse_aircraft({"hex": "z", "lat": 1, "lon": 1, "seen_pos": 600}) is None


@pytest.mark.asyncio
async def test_flights_clamp_radius_and_cache():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={"ac": [{"hex": "a", "lat": 51.5, "lon": -0.4, "alt_baro": 1000}]})

    prov = FlightProvider(cache=WorldDataCache(), transport=transport(handler))
    r1 = await prov.get_flights(51.47, -0.45, radius_nm=900)
    r2 = await prov.get_flights(51.47, -0.45, radius_nm=900)
    assert r1.radius_nm == 250 and r1.count == 1 and r2.count == 1
    assert len(calls) == 1 and "/dist/250" in calls[0]


def test_parse_launch_keeps_pad_coordinates_and_rejects_bad_ones():
    item = {
        "id": "abc", "name": "GSLV Mk II | NVS-03", "net": "2026-10-30T18:21:00Z", "slug": "gslv",
        "status": {"name": "Go for Launch", "abbrev": "Go"}, "net_precision": {"name": "Minute"},
        "pad": {"name": "SLP", "latitude": "13.7199", "longitude": "80.2304", "location": {"name": "Satish Dhawan Space Centre, India"}},
        "rocket": {"configuration": {"full_name": "GSLV Mk. II"}}, "mission": {"name": "NVS-03", "orbit": {"name": "GTO"}},
    }
    rec = parse_launch(item)
    assert rec.latitude == pytest.approx(13.7199) and rec.orbit == "GTO" and rec.url.endswith("/gslv")
    bad = parse_launch({**item, "pad": {"latitude": "not-a-number", "longitude": 5}})
    assert bad.latitude is None and bad.longitude is None


@pytest.mark.asyncio
async def test_launch_rate_limit_is_reported():
    res = await LaunchProvider(cache=WorldDataCache(), transport=transport(lambda r: httpx.Response(429))).get_launches()
    assert res.status == ProviderStatus.RATE_LIMITED and res.count == 0


@pytest.mark.asyncio
async def test_fires_not_configured_without_key_makes_no_request():
    def handler(req):
        raise AssertionError("must not call FIRMS without a key")

    res = await FireProvider(cache=WorldDataCache(), transport=transport(handler), map_key="").get_fires()
    assert res.status == ProviderStatus.NOT_CONFIGURED and res.count == 0


@pytest.mark.asyncio
async def test_fires_parse_and_keep_strongest():
    csv_text = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
        "-12.5,130.1,330.5,0.4,0.4,2026-10-29,0412,N20,VIIRS,n,2.0NRT,290.1,12.3,D\n"
        "-12.6,130.2,360.0,0.4,0.4,2026-10-29,0412,N20,VIIRS,h,2.0NRT,295.0,88.0,D\n"
        "999,130.2,360.0,0.4,0.4,2026-10-29,0412,N20,VIIRS,h,2.0NRT,295.0,1.0,D\n"
    )
    prov = FireProvider(cache=WorldDataCache(), transport=transport(lambda r: httpx.Response(200, text=csv_text)), map_key="KEY")
    res = await prov.get_fires(limit=1)
    assert res.total_detections == 2 and res.count == 1
    assert res.fires[0].frp_mw == 88.0 and res.fires[0].acquired_utc == "2026-10-29T04:12:00Z"


def test_firms_error_text_is_not_parsed_as_data():
    with pytest.raises(Exception):
        parse_firms_csv("Invalid MAP_KEY.")
