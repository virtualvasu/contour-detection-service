"""FastAPI app exposing the contour analysis API."""

from __future__ import annotations

import os
import threading

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.catchment import DEFAULT_RAINFALL_MM, DEFAULT_RUNOFF_COEFFICIENT
from app.pipeline import analyze_contour_file, preview_contour_file
from app.schemas import AnalyzeContourResponse, ContourPreviewResponse
from app.selection import parse_area

# Largest contour map accepted, in MB. Parsing a KML takes roughly 8x its
# size in memory, so 20 MB keeps a worker well inside a 512 MB machine
# (the sample map is 6.7 MB).
MAX_UPLOAD_BYTES = int(float(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024)

# How many analyses one worker process runs at the same time. Each one is
# CPU- and memory-heavy, so running many at once just makes all of them slow;
# requests over the limit wait up to ANALYSIS_QUEUE_TIMEOUT_S for a free slot
# and then get a 503 telling the client to retry. Scale out by adding worker
# processes / machines rather than raising this.
MAX_CONCURRENT_ANALYSES = int(os.environ.get("MAX_CONCURRENT_ANALYSES", "2"))
ANALYSIS_QUEUE_TIMEOUT_S = float(os.environ.get("ANALYSIS_QUEUE_TIMEOUT_S", "30"))
_analysis_slots = threading.BoundedSemaphore(MAX_CONCURRENT_ANALYSES)

app = FastAPI(
    title="Contour Detection Service",
    description="Upload a contour map (KML/KMZ) and get back suggested pond "
    "sites with their catchment area and storage volume.",
    version="0.1.0",
)

# Allows the local React frontend (a separate dev server/origin) to call this
# API directly from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Responses are mostly coordinate lists, which compress very well.
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _read_upload(contour_map: UploadFile | None, file: UploadFile | None) -> tuple[str, bytes]:
    """Validate the uploaded contour map and return (filename, contents)."""
    upload = contour_map or file
    if upload is None:
        raise HTTPException(status_code=422, detail="Missing required file field 'contour_map'")

    name = upload.filename or ""
    if not name.lower().endswith((".kml", ".kmz")):
        raise HTTPException(status_code=400, detail="Only .kml or .kmz files are accepted")

    raw_bytes = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large (limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return name, raw_bytes


@app.post("/previewContour", response_model=ContourPreviewResponse)
def preview_contour(
    contour_map: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
) -> ContourPreviewResponse:
    """Parse a contour map and return its outline and simplified contour
    lines, without analyzing it — for showing the map before an area is picked."""
    name, raw_bytes = _read_upload(contour_map, file)
    try:
        return preview_contour_file(raw_bytes, filename=name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Plain `def` (not `async def`) on purpose: the analysis is CPU-heavy, and
# FastAPI runs sync handlers in a thread pool, so one long analysis doesn't
# stall every other request on the same worker.
@app.post("/analyzeContour", response_model=AnalyzeContourResponse)
def analyze_contour(
    contour_map: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
    cell_size_m: float | None = Query(
        None,
        gt=0,
        description="Grid resolution to analyze at, in metres per cell. "
        "Smaller values give more precise pond/catchment boundaries but "
        "take longer to compute. Omit to pick a resolution automatically "
        "based on the map's size.",
    ),
    rainfall_mm: float = Query(
        DEFAULT_RAINFALL_MM,
        gt=0,
        le=10_000,
        description="Rainfall to estimate collectible water for, in mm "
        "(e.g. the area's average annual rainfall).",
    ),
    runoff_coefficient: float = Query(
        DEFAULT_RUNOFF_COEFFICIENT,
        gt=0,
        le=1,
        description="Share of rainfall that runs off the land instead of "
        "soaking in (0-1).",
    ),
    include_contours: bool = Query(
        True,
        description="Also return the (simplified) input contour lines. "
        "Clients that already have them, e.g. from /previewContour, can "
        "pass false for a smaller, faster response.",
    ),
    area: str | None = Form(
        None,
        description="Land area to analyze, as a GeoJSON Polygon or "
        "MultiPolygon in lon/lat. Omit to analyze the whole map.",
    ),
) -> AnalyzeContourResponse:
    name, raw_bytes = _read_upload(contour_map, file)

    if not _analysis_slots.acquire(timeout=ANALYSIS_QUEUE_TIMEOUT_S):
        raise HTTPException(
            status_code=503,
            detail="Server is busy with other analyses, please try again shortly",
            headers={"Retry-After": "5"},
        )
    try:
        selected_area = parse_area(area) if area else None
        return analyze_contour_file(
            raw_bytes,
            filename=name,
            cell_size_m=cell_size_m,
            area=selected_area,
            rainfall_mm=rainfall_mm,
            runoff_coefficient=runoff_coefficient,
            include_contours=include_contours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        _analysis_slots.release()
