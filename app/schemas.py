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


class AnalyzeContourResponse(BaseModel):
    source_file: str
    terrain: TerrainSummary
    pond_sites: list[PondSite]
    contours: list[ContourLineOut]
