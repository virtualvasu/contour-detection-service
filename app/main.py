"""FastAPI app exposing the contour analysis API."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.catchment import DEFAULT_RAINFALL_MM, DEFAULT_RUNOFF_COEFFICIENT
from app.pipeline import analyze_contour_file
from app.schemas import AnalyzeContourResponse
from app.selection import parse_area

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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
    area: str | None = Form(
        None,
        description="Land area to analyze, as a GeoJSON Polygon or "
        "MultiPolygon in lon/lat. Omit to analyze the whole map.",
    ),
) -> AnalyzeContourResponse:
    upload = contour_map or file
    if upload is None:
        raise HTTPException(status_code=422, detail="Missing required file field 'contour_map'")

    name = upload.filename or ""
    if not name.lower().endswith((".kml", ".kmz")):
        raise HTTPException(status_code=400, detail="Only .kml or .kmz files are accepted")

    raw_bytes = upload.file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        selected_area = parse_area(area) if area else None
        return analyze_contour_file(
            raw_bytes,
            filename=name,
            cell_size_m=cell_size_m,
            area=selected_area,
            rainfall_mm=rainfall_mm,
            runoff_coefficient=runoff_coefficient,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
