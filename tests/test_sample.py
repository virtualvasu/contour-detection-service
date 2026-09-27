"""End-to-end checks that run the full pipeline against the sample contour map.

These are sanity checks, not golden-value tests: the sample map can change
and the exact numbers are not something we should pin down. What matters is
that the shape of the output stays valid and physically sensible.
"""

import pathlib
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import analyze_contour_file

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "samples" / "contours_1m.kml"


@pytest.fixture(scope="module")
def sample_bytes() -> bytes:
    return SAMPLE_PATH.read_bytes()


def test_pipeline_runs_on_sample(sample_bytes):
    result = analyze_contour_file(sample_bytes, "contours_1m.kml")

    assert result.terrain.contour_line_count > 0
    assert result.terrain.max_elevation_m > result.terrain.min_elevation_m
    assert result.terrain.contour_interval_m > 0
    assert len(result.pond_sites) > 0

    volumes = [site.estimated_volume_m3 for site in result.pond_sites]
    assert volumes == sorted(volumes, reverse=True), "sites must be ranked by volume, largest first"

    for site in result.pond_sites:
        assert site.catchment_area_m2 > 0
        assert site.pond_area_m2 > 0
        assert site.estimated_volume_m3 > 0
        assert site.max_depth_m > 0
        # the pond footprint cannot be bigger than the land draining into it
        assert site.pond_area_m2 <= site.catchment_area_m2
        assert len(site.catchment_boundary) > 0
        assert len(site.pond_boundary) > 0


def test_api_analyze_contour_endpoint():
    client = TestClient(app)
    with open(SAMPLE_PATH, "rb") as f:
        response = client.post(
            "/analyzeContour",
            files={"file": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["source_file"] == "contours_1m.kml"
    assert len(body["pond_sites"]) > 0


def test_api_analyze_contour_endpoint_accepts_contour_map_field():
    client = TestClient(app)
    with open(SAMPLE_PATH, "rb") as f:
        response = client.post(
            "/analyzeContour",
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["source_file"] == "contours_1m.kml"
    assert len(body["pond_sites"]) > 0


def test_api_rejects_missing_file_field():
    client = TestClient(app)
    response = client.post("/analyzeContour")
    assert response.status_code == 422
    assert "contour_map" in response.json()["detail"]


def test_api_rejects_wrong_extension():
    client = TestClient(app)
    response = client.post(
        "/analyzeContour",
        files={"file": ("notacontour.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_api_rejects_invalid_kml():
    client = TestClient(app)
    response = client.post(
        "/analyzeContour",
        files={"file": ("broken.kml", b"not xml at all", "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 422


def test_api_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr("app.main.MAX_UPLOAD_BYTES", 10)
    client = TestClient(app)
    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("big.kml", b"x" * 11, "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 413


def test_api_returns_503_when_all_analysis_slots_are_busy(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    slots.acquire()  # another analysis is holding the only slot
    monkeypatch.setattr("app.main._analysis_slots", slots)
    monkeypatch.setattr("app.main.ANALYSIS_QUEUE_TIMEOUT_S", 0.01)

    client = TestClient(app)
    with open(SAMPLE_PATH, "rb") as f:
        response = client.post(
            "/analyzeContour",
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_api_can_leave_out_contours():
    client = TestClient(app)
    with open(SAMPLE_PATH, "rb") as f:
        response = client.post(
            "/analyzeContour",
            params={"include_contours": "false"},
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["contours"] == []
    assert len(body["pond_sites"]) > 0
