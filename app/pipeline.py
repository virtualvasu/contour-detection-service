"""Ties the parser, terrain model and catchment logic together.

This is the one place that runs the full analysis end to end, so the
API route (app/main.py) and any test/CLI script can both call a single
function and get back a plain response object.
"""

from __future__ import annotations

import numpy as np

from app.catchment import build_pond_candidate, find_sink_candidates, mask_to_polygon
from app.kml_parser import parse_contours
from app.schemas import AnalyzeContourResponse, ContourLineOut, LonLat, PondSite, TerrainSummary
from app.terrain import build_dem, compute_flow_model, simplify_contours_for_display

TOP_N_SITES = 3

# How many depressions to evaluate before picking the final ranking. We first
# gather a wider pool ranked by contributing catchment area (a cheap signal
# of "this is a real drainage low point, not noise"), then compute the full
# storage volume for each and re-sort by that, so the top N sites shown are
# the biggest by volume rather than just the biggest by catchment.
CANDIDATE_POOL_SIZE = 10


def _ring_to_lonlat_models(ring: list[tuple[float, float]]) -> list[LonLat]:
    return [LonLat(lon=lon, lat=lat) for lon, lat in ring]


def analyze_contour_file(
    raw_bytes: bytes, filename: str, cell_size_m: float | None = None
) -> AnalyzeContourResponse:
    contours = parse_contours(raw_bytes)

    dem = build_dem(contours, cell_size_m=cell_size_m)
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
                catchment_boundary=catchment_rings,
                pond_boundary=pond_rings,
            )
        )

    valid_elev = dem.elevation[dem.valid_mask]
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

    display_contours = [
        ContourLineOut(elevation_m=elevation, points=_ring_to_lonlat_models(points))
        for elevation, points in simplify_contours_for_display(contours, dem)
    ]

    return AnalyzeContourResponse(
        source_file=filename,
        terrain=terrain_summary,
        pond_sites=pond_sites,
        contours=display_contours,
    )
