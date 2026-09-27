"""Checks for turning OpenStreetMap water features into areas to leave out.

Uses hand-made Overpass elements, so no network access is needed.
"""

import pytest
from shapely.geometry import Point

from app import water
from app.water import WaterLookupError, find_water, water_geometry

BOUNDS = (81.28, 21.24, 81.32, 21.27)


def _way(tags, coords):
    return {"type": "way", "tags": tags, "geometry": [{"lon": x, "lat": y} for x, y in coords]}


def _square(x, y, size):
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]


def test_lake_is_left_out_with_a_margin():
    lake = _way({"natural": "water"}, _square(81.29, 21.25, 0.002))
    geometry = water_geometry([lake], BOUNDS)

    assert geometry.contains(Point(81.291, 21.251))
    # the lake's east edge is at 81.292; 1e-5 deg of longitude is ~1 m here
    assert geometry.contains(Point(81.292 + 5e-5, 21.251))  # ~5 m out: within the margin
    assert not geometry.contains(Point(81.292 + 2e-4, 21.251))  # ~20 m out: land


def test_river_centre_line_is_widened():
    river = _way({"waterway": "river"}, [(81.285, 21.25), (81.315, 21.25)])
    geometry = water_geometry([river], BOUNDS)
    # centre line on 21.25; the half width plus margin is 25 m, ~0.000225 deg
    assert geometry.contains(Point(81.30, 21.2501))
    assert not geometry.contains(Point(81.30, 21.2505))


def test_streams_are_kept():
    stream = _way({"waterway": "stream"}, [(81.285, 21.25), (81.315, 21.25)])
    assert water_geometry([stream], BOUNDS) is None


def test_multipolygon_island_stays_land():
    outer = _square(81.29, 21.25, 0.01)
    inner = _square(81.294, 21.254, 0.002)
    relation = {
        "type": "relation",
        "tags": {"type": "multipolygon", "natural": "water"},
        "members": [
            {"type": "way", "role": "outer", "geometry": [{"lon": x, "lat": y} for x, y in outer]},
            {"type": "way", "role": "inner", "geometry": [{"lon": x, "lat": y} for x, y in inner]},
        ],
    }
    geometry = water_geometry([relation], BOUNDS)
    assert geometry.contains(Point(81.291, 21.251))
    assert not geometry.contains(Point(81.295, 21.255))


def test_water_is_clipped_to_the_bounds():
    big_lake = _way({"natural": "water"}, _square(81.25, 21.20, 0.2))
    geometry = water_geometry([big_lake], BOUNDS)
    minx, miny, maxx, maxy = geometry.bounds
    assert (minx, miny) >= BOUNDS[:2] and (maxx, maxy) <= BOUNDS[2:]


def test_lookup_failure_pauses_further_lookups(monkeypatch):
    calls = []

    def failing_fetch(bounds):
        calls.append(bounds)
        raise WaterLookupError("down")

    monkeypatch.setattr(water, "_fetch_elements", failing_fetch)
    monkeypatch.setattr(water, "_unavailable_until", 0.0)
    water._cached_water.cache_clear()

    with pytest.raises(WaterLookupError):
        find_water(BOUNDS)
    with pytest.raises(WaterLookupError):
        find_water(BOUNDS)
    assert len(calls) == 1  # the second request didn't wait on the network again


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


QUERY = {"min_lon": 81.28, "min_lat": 21.24, "max_lon": 81.32, "max_lat": 21.27}


def test_water_bodies_endpoint_returns_geojson(monkeypatch):
    lake = water_geometry([_way({"natural": "water"}, _square(81.29, 21.25, 0.002))], BOUNDS)
    monkeypatch.setattr("app.main.find_water", lambda bounds: lake)

    body = _client().get("/waterBodies", params=QUERY).json()

    assert body["status"] == "found"
    assert body["geometry"]["type"] == "MultiPolygon"


@pytest.mark.parametrize("result, status", [(None, "none"), (WaterLookupError("down"), "unavailable")])
def test_water_bodies_endpoint_without_water(monkeypatch, result, status):
    def fake_find_water(bounds):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("app.main.find_water", fake_find_water)
    body = _client().get("/waterBodies", params=QUERY).json()
    assert body == {"status": status, "geometry": None}


def test_water_bodies_endpoint_rejects_huge_areas():
    response = _client().get("/waterBodies", params={**QUERY, "max_lon": 82.5})
    assert response.status_code == 422


def test_lookup_falls_back_to_the_next_server(monkeypatch):
    import httpx

    tried = []

    def fake_post(url, **kwargs):
        tried.append(url)
        request = httpx.Request("POST", url)
        if url == "https://first.example":
            return httpx.Response(504, request=request)
        return httpx.Response(200, json={"elements": [{"type": "way", "id": 1}]}, request=request)

    monkeypatch.setattr(water, "OVERPASS_URLS", ["https://first.example", "https://second.example"])
    monkeypatch.setattr(water.httpx, "post", fake_post)

    assert water._fetch_elements(BOUNDS) == [{"type": "way", "id": 1}]
    assert tried == ["https://first.example", "https://second.example"]
