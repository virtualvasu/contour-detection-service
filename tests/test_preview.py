"""Checks for the /previewContour endpoint."""

import pathlib

from fastapi.testclient import TestClient

from app.main import app

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "samples" / "contours_1m.kml"


def test_preview_returns_bounds_and_contours():
    client = TestClient(app)
    with open(SAMPLE_PATH, "rb") as f:
        response = client.post(
            "/previewContour",
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert response.status_code == 200
    body = response.json()
    bounds = body["bounds"]
    assert bounds["min_lon"] < bounds["max_lon"]
    assert bounds["min_lat"] < bounds["max_lat"]
    assert body["max_elevation_m"] > body["min_elevation_m"]
    assert body["contour_line_count"] == len(body["contours"])
    for line in body["contours"]:
        for p in line["points"]:
            assert bounds["min_lon"] - 1e-6 <= p["lon"] <= bounds["max_lon"] + 1e-6
            assert bounds["min_lat"] - 1e-6 <= p["lat"] <= bounds["max_lat"] + 1e-6


def test_preview_rejects_wrong_extension():
    client = TestClient(app)
    response = client.post(
        "/previewContour",
        files={"contour_map": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
