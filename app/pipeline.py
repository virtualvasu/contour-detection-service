"""Ties the parser, terrain model and catchment logic together.

This is the one place that runs the full analysis end to end, so the
API route (app/main.py) and any test/CLI script can both call a single
function and get back a plain response object.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from app.catchment import (
    DEFAULT_RAINFALL_MM,
    DEFAULT_RUNOFF_COEFFICIENT,
    build_pond_candidate,
    expected_runoff_m3,
    find_sink_candidates,
    mask_to_polygon,
)
from app.kml_parser import parse_contours
from app.schemas import (
    AnalyzeContourResponse,
    Bounds,
    ContourLineOut,
    ContourPreviewResponse,
    LonLat,
    PondSite,
    RunoffAssumptions,
    TerrainSummary,
)
from app.selection import clip_contours
from app.terrain import (
    build_dem,
    compute_flow_model,
    detect_contour_interval,
    simplify_contours_for_display,
    simplify_contours_for_preview,
)

TOP_N_SITES = 3

# How many depressions to evaluate before picking the final ranking. We first
# gather a wider pool ranked by contributing catchment area (a cheap signal
# of "this is a real drainage low point, not noise"), then compute the full
# storage volume for each and re-sort by that, so the top N sites shown are
# the biggest by volume rather than just the biggest by catchment.
CANDIDATE_POOL_SIZE = 10


# 6 decimal places of a degree is ~0.1 m, far finer than any grid cell, so
# the extra digits would only make the response bigger.
COORD_DECIMALS = 6


def _ring_to_lonlat_models(ring: list[tuple[float, float]]) -> list[LonLat]:
    return [
        LonLat(lon=round(lon, COORD_DECIMALS), lat=round(lat, COORD_DECIMALS))
        for lon, lat in ring
    ]


def _contour_bounds(contours) -> tuple[float, float, float, float]:
    lons = np.array([p[0] for c in contours for p in c.points])
    lats = np.array([p[1] for c in contours for p in c.points])
    return float(lons.min()), float(lats.min()), float(lons.max()), float(lats.max())


def preview_contour_file(raw_bytes: bytes, filename: str) -> ContourPreviewResponse:
    """Parse a contour map just far enough to draw it, so the user can pick
    an area on it before running the (much slower) analysis."""
    contours = parse_contours(raw_bytes)
    min_lon, min_lat, max_lon, max_lat = _contour_bounds(contours)
    elevations = [c.elevation for c in contours]

    return ContourPreviewResponse(
        source_file=filename,
        bounds=Bounds(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat),
        min_elevation_m=min(elevations),
        max_elevation_m=max(elevations),
        contour_interval_m=detect_contour_interval(contours),
        contour_line_count=len(contours),
        contours=[
            ContourLineOut(elevation_m=elevation, points=_ring_to_lonlat_models(points))
            for elevation, points in simplify_contours_for_preview(contours)
        ],
    )


def analyze_contour_file(
    raw_bytes: bytes,
    filename: str,
    cell_size_m: float | None = None,
    area: BaseGeometry | None = None,
    rainfall_mm: float = DEFAULT_RAINFALL_MM,
    runoff_coefficient: float = DEFAULT_RUNOFF_COEFFICIENT,
    include_contours: bool = True,
    exclude: BaseGeometry | None = None,
) -> AnalyzeContourResponse:
    contours = parse_contours(raw_bytes)

    # Land to leave out, e.g. rivers and lakes: a river bed is the lowest
    # ground around, so left in it would be picked as a pond site.
    if exclude is not None:
        region = area if area is not None else box(*_contour_bounds(contours))
        area = region.difference(exclude)
        if area.is_empty or area.area == 0:
            raise ValueError(
                "Nothing is left of the selected area once water and other "
                "excluded land is removed. Select some land."
            )

    if area is not None:
        contours = clip_contours(contours, area)

    dem = build_dem(contours, cell_size_m=cell_size_m, area=area)
    flow_model = compute_flow_model(dem)

    sinks = find_sink_candidates(flow_model, top_n=CANDIDATE_POOL_SIZE)
    candidates = [build_pond_candidate(flow_model, sink) for sink in sinks]
    candidates.sort(key=lambda c: c.volume_m3, reverse=True)
    candidates = candidates[:TOP_N_SITES]

    pond_sites: list[PondSite] = []
    for rank, candidate in enumerate(candidates, start=1):
        lon, lat = dem.transformer_to_lonlat.transform(
            dem.x_coords[candidate.col], dem.y_coords[candidate.row]
        )
        catchment_rings = [_ring_to_lonlat_models(r) for r in mask_to_polygon(candidate.catchment_cells, dem)]
        pond_rings = [_ring_to_lonlat_models(r) for r in mask_to_polygon(candidate.pond_mask, dem)]
        runoff_m3 = expected_runoff_m3(candidate.catchment_area_m2, rainfall_mm, runoff_coefficient)

        pond_sites.append(
            PondSite(
                rank=rank,
                location=LonLat(lon=float(lon), lat=float(lat)),
                elevation_m=candidate.elevation,
                spill_elevation_m=candidate.spill_elevation,
                max_depth_m=candidate.max_depth_m,
                catchment_area_m2=candidate.catchment_area_m2,
                catchment_area_hectares=candidate.catchment_area_m2 / 10_000,
                pond_area_m2=candidate.pond_area_m2,
                estimated_volume_m3=candidate.volume_m3,
                expected_runoff_m3=runoff_m3,
                # a pond can't hold more than it can store, nor more than drains into it
                collectible_volume_m3=min(runoff_m3, candidate.volume_m3),
                catchment_boundary=catchment_rings,
                pond_boundary=pond_rings,
            )
        )

    valid_elev = dem.elevation[dem.valid_mask & dem.area_mask]
    terrain_summary = TerrainSummary(
        min_elevation_m=float(np.min(valid_elev)),
        max_elevation_m=float(np.max(valid_elev)),
        contour_interval_m=dem.contour_interval,
        contour_line_count=len(contours),
        grid_rows=dem.elevation.shape[0],
        grid_cols=dem.elevation.shape[1],
        cell_size_m=dem.cell_size,
        projected_crs=dem.crs.to_string(),
    )

    display_contours = []
    if include_contours:
        display_contours = [
            ContourLineOut(elevation_m=elevation, points=_ring_to_lonlat_models(points))
            for elevation, points in simplify_contours_for_display(contours, dem)
        ]

    return AnalyzeContourResponse(
        source_file=filename,
        terrain=terrain_summary,
        runoff=RunoffAssumptions(rainfall_mm=rainfall_mm, runoff_coefficient=runoff_coefficient),
        pond_sites=pond_sites,
        contours=display_contours,
    )
