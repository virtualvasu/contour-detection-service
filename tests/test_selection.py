"""Checks that an analysis restricted to a selected area stays inside it."""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, box

from app.main import app
from app.pipeline import analyze_contour_file
from app.selection import parse_area

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "samples" / "contours_1m.kml"

# Western half of the sample map.
WEST_HALF = {
    "type": "Polygon",
    "coordinates": [[
        [81.2814, 21.2398], [81.2970, 21.2398], [81.2970, 21.2636],
        [81.2814, 21.2636], [81.2814, 21.2398],
    ]],
}


@pytest.fixture(scope="module")
def sample_bytes() -> bytes:
    return SAMPLE_PATH.read_bytes()


def test_sites_stay_inside_selected_area(sample_bytes):
    area = parse_area(json.dumps(WEST_HALF))
    result = analyze_contour_file(sample_bytes, "contours_1m.kml", area=area)

    assert len(result.pond_sites) > 0
    # allow one grid cell of slack for boundary polygons built from whole cells
    slack_deg = result.terrain.cell_size_m / 111_000
    grown = area.buffer(slack_deg)
    for site in result.pond_sites:
        assert area.contains(Point(site.location.lon, site.location.lat))
        for ring in site.catchment_boundary:
            for p in ring:
                assert grown.contains(Point(p.lon, p.lat))


def test_parse_area_accepts_feature():
    feature = {"type": "Feature", "properties": {}, "geometry": WEST_HALF}
    assert parse_area(json.dumps(feature)).equals(parse_area(json.dumps(WEST_HALF)))


@pytest.mark.parametrize("bad", [
    "not json",
    json.dumps({"type": "Point", "coordinates": [81.29, 21.25]}),
    json.dumps({"type": "Polygon", "coordinates": []}),
])
def test_parse_area_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_area(bad)


def test_api_accepts_area(sample_bytes):
    client = TestClient(app)
    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("contours_1m.kml", sample_bytes, "application/vnd.google-earth.kml+xml")},
        data={"area": json.dumps(WEST_HALF)},
    )
    assert response.status_code == 200
    assert len(response.json()["pond_sites"]) > 0


def test_api_rejects_area_outside_map(sample_bytes):
    far_away = box(0, 0, 0.01, 0.01).__geo_interface__
    client = TestClient(app)
    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("contours_1m.kml", sample_bytes, "application/vnd.google-earth.kml+xml")},
        data={"area": json.dumps(far_away)},
    )
    assert response.status_code == 422
    assert "contour" in response.json()["detail"]
