"""Pydantic models for the /analyzeContour response."""

from __future__ import annotations

from pydantic import BaseModel


class LonLat(BaseModel):
    lon: float
    lat: float


class PondSite(BaseModel):
    rank: int
    location: LonLat
    elevation_m: float
    spill_elevation_m: float
    max_depth_m: float
    catchment_area_m2: float
    catchment_area_hectares: float
    pond_area_m2: float
    estimated_volume_m3: float
    expected_runoff_m3: float
    collectible_volume_m3: float
    catchment_boundary: list[list[LonLat]]
    pond_boundary: list[list[LonLat]]


class ContourLineOut(BaseModel):
    elevation_m: float
    points: list[LonLat]


class TerrainSummary(BaseModel):
    min_elevation_m: float
    max_elevation_m: float
    contour_interval_m: float
    contour_line_count: int
    grid_rows: int
    grid_cols: int
    cell_size_m: float
    projected_crs: str


class RunoffAssumptions(BaseModel):
    rainfall_mm: float
    runoff_coefficient: float


class Bounds(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class ContourPreviewResponse(BaseModel):
    source_file: str
    bounds: Bounds
    min_elevation_m: float
    max_elevation_m: float
    contour_interval_m: float
    contour_line_count: int
    contours: list[ContourLineOut]


class AnalyzeContourResponse(BaseModel):
    source_file: str
    terrain: TerrainSummary
    runoff: RunoffAssumptions
    pond_sites: list[PondSite]
    contours: list[ContourLineOut]
