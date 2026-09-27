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
