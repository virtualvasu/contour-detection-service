"""Checks for the expected-runoff and collectible-volume figures."""

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.catchment import expected_runoff_m3
from app.main import app

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "samples" / "contours_1m.kml"


def test_expected_runoff_formula():
    # 1 ha catchment, 1000 mm of rain, half of it running off -> 5000 m3
    assert expected_runoff_m3(10_000, 1000, 0.5) == pytest.approx(5000)


def test_api_reports_runoff_and_collectible_volume():
    client = TestClient(app)
    with open(SAMPLE_PATH, "rb") as f:
        response = client.post(
            "/analyzeContour",
            params={"rainfall_mm": 800, "runoff_coefficient": 0.4},
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["runoff"] == {"rainfall_mm": 800, "runoff_coefficient": 0.4}
    for site in body["pond_sites"]:
        assert site["expected_runoff_m3"] == pytest.approx(site["catchment_area_m2"] * 0.8 * 0.4)
        assert site["collectible_volume_m3"] == pytest.approx(
            min(site["expected_runoff_m3"], site["estimated_volume_m3"])
        )


@pytest.mark.parametrize("params", [
    {"rainfall_mm": 0},
    {"runoff_coefficient": 0},
    {"runoff_coefficient": 1.5},
])
def test_api_rejects_bad_runoff_params(params):
    client = TestClient(app)
    response = client.post(
        "/analyzeContour",
        params=params,
        files={"contour_map": ("x.kml", b"<kml/>", "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 422
