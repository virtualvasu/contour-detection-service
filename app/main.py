"""FastAPI app exposing the contour analysis API."""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from app.pipeline import analyze_contour_file
from app.schemas import AnalyzeContourResponse

app = FastAPI(
    title="Contour Detection Service",
    description="Upload a contour map (KML/KMZ) and get back suggested pond "
    "sites with their catchment area and storage volume.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyzeContour", response_model=AnalyzeContourResponse)
async def analyze_contour(
    file: UploadFile = File(...),
    cell_size_m: float | None = Query(
        None,
        gt=0,
        description="Grid resolution to analyze at, in metres per cell. "
        "Smaller values give more precise pond/catchment boundaries but "
        "take longer to compute. Omit to pick a resolution automatically "
        "based on the map's size.",
    ),
) -> AnalyzeContourResponse:
    name = file.filename or ""
    if not name.lower().endswith((".kml", ".kmz")):
        raise HTTPException(status_code=400, detail="Only .kml or .kmz files are accepted")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        return analyze_contour_file(raw_bytes, filename=name, cell_size_m=cell_size_m)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
