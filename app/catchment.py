"""Pick pond sites and work out their catchment area and storage volume.

We compute two different areas for each candidate site:

* the **catchment** — all the land whose runoff flows into the site. We
  find this by walking the flow map (built in terrain.py) backwards from
  the site, collecting every cell that eventually drains to it.
* the **pond footprint** — the low ground right around the site that
  would actually be under water at a given water level. We find this by
  raising the water level step by step (one contour interval at a time)
  and seeing how far it spreads. The area at each step gives us a volume
  estimate (area-elevation method).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from app.terrain import FlowModel

MIN_CATCHMENT_CELLS = 15  # discard sinks whose catchment is likely interpolation noise
MAX_FLOOD_LEVELS = 200    # safety cap on how many contour steps we flood-fill upward

# A pond is a built structure (an earthen bund/check-dam), not a lake left to
# fill an entire depression to its natural rim. Real farm ponds are normally
# a few metres deep, so we cap how high the flood-fill is allowed to rise
# above the lowest point. This is a design assumption about ponds in
# general, not something read from any specific map.
MAX_POND_DEPTH_M = 5.0

# Defaults for the collectible-water estimate. Annual rainfall is a typical
# figure for central India; the runoff coefficient (share of rain that runs
# off instead of soaking in) is a common value for rural, partly cultivated
# land. Both can be overridden per request.
DEFAULT_RAINFALL_MM = 1200.0
DEFAULT_RUNOFF_COEFFICIENT = 0.3


@dataclass
class PondCandidate:
    row: int
    col: int
    elevation: float
    catchment_cells: np.ndarray       # bool mask, shape of the DEM
    catchment_area_m2: float
    pond_mask: np.ndarray              # bool mask of the flooded depression footprint
    pond_area_m2: float
    spill_elevation: float
    volume_m3: float
    max_depth_m: float


def find_sink_candidates(flow_model: FlowModel, top_n: int = 3) -> list[tuple[int, int]]:
    """Return the `top_n` low points (sinks), sorted by how much land drains into them."""
    flow_to = flow_model.flow_to
    valid = flow_model.dem.valid_mask

    # Sinks right on the edge of the grid or of the selected area are
    # usually just where the terrain was cut off, not real depressions.
    interior = ndimage.binary_erosion(flow_model.dem.area_mask, structure=np.ones((3, 3)))

    is_sink = (flow_to == -1) & valid & interior
    sink_rows, sink_cols = np.where(is_sink)
    if sink_rows.size == 0:
        raise ValueError("No depressions found in the terrain that could hold water")

    accum = flow_model.flow_accum_cells[sink_rows, sink_cols]
    order = np.argsort(-accum)
    ranked = [(int(sink_rows[i]), int(sink_cols[i])) for i in order]
    ranked = [rc for rc in ranked if flow_model.flow_accum_cells[rc] >= MIN_CATCHMENT_CELLS]
    if not ranked:
        raise ValueError(
            "Depressions were found but none had a large enough contributing "
            "area to be a plausible pond site"
        )
    return ranked[:top_n]


def _delineate_catchment(flow_model: FlowModel, sink: tuple[int, int]) -> np.ndarray:
    rows, cols = flow_model.flow_to.shape
    flow_to_flat = flow_model.flow_to.ravel()
    n = flow_to_flat.size

    sources = np.where(flow_to_flat != -1)[0]
    targets = flow_to_flat[sources]
    order = np.argsort(targets)
    sorted_targets = targets[order]
    sorted_sources = sources[order]
    boundaries = np.searchsorted(sorted_targets, np.arange(n + 1))

    reached = np.zeros(n, dtype=bool)
    sink_flat = sink[0] * cols + sink[1]
    stack = [sink_flat]
    reached[sink_flat] = True
    while stack:
        cur = stack.pop()
        preds = sorted_sources[boundaries[cur]:boundaries[cur + 1]]
        for p in preds:
            if not reached[p]:
                reached[p] = True
                stack.append(int(p))

    return reached.reshape(rows, cols)


def _flood_fill_basin(flow_model: FlowModel, sink: tuple[int, int]):
    """Grow a connected flooded region from `sink`, one elevation step at a
    time, and return (masks_by_level, areas, elevations, spill_elevation).

    The flood stops the step *before* the region would spill out to the
    raster boundary or merge with terrain outside the current catchment
    (taken as the natural rim of the depression), or once it reaches
    MAX_POND_DEPTH_M above the lowest point, whichever comes first.
    """
    dem = flow_model.dem
    elevation = dem.elevation
    rows, cols = elevation.shape
    step = dem.contour_interval
    sink_elev = elevation[sink]

    catchment_mask = _delineate_catchment(flow_model, sink)

    areas = []
    elevations = []
    prev_mask = None
    level_elev = sink_elev
    spill_elevation = sink_elev
    final_mask = np.zeros_like(elevation, dtype=bool)

    for _ in range(MAX_FLOOD_LEVELS):
        flood_candidates = (elevation <= level_elev + 1e-6) & catchment_mask
        labeled, _ = ndimage.label(flood_candidates, structure=np.ones((3, 3)))
        sink_label = labeled[sink]
        region = labeled == sink_label if sink_label != 0 else np.zeros_like(flood_candidates)

        touches_edge = (
            region[0, :].any() or region[-1, :].any() or
            region[:, 0].any() or region[:, -1].any()
        )

        areas.append(int(region.sum()) * dem.cell_size ** 2)
        elevations.append(float(level_elev))
        final_mask = region
        spill_elevation = level_elev

        reached_full_catchment = prev_mask is not None and region.sum() >= catchment_mask.sum()
        reached_max_depth = (level_elev - sink_elev) >= MAX_POND_DEPTH_M - 1e-6
        if touches_edge or reached_full_catchment or reached_max_depth:
            break
        prev_mask = region
        level_elev += step

    return final_mask, areas, elevations, spill_elevation


def mask_to_polygon(mask: np.ndarray, dem) -> list[list[tuple[float, float]]]:
    """Union the grid cells in `mask` into polygon ring(s), in lon/lat.

    Cells are merged in integer (col, row) grid units and only then scaled to
    metres. Doing the union directly in projected metres leaves hairline
    floating-point gaps between neighbouring rows, so a single catchment came
    back as a stack of one-cell-tall strips.
    """
    rows, cols = np.where(mask)
    if rows.size == 0:
        return []
    squares = [box(c, r, c + 1, r + 1) for r, c in zip(rows.tolist(), cols.tolist())]
    merged = unary_union(squares).simplify(0.5, preserve_topology=True)

    # grid units -> projected metres: col 0's left edge / row 0's top edge
    left = dem.x_coords[0] - dem.cell_size / 2
    top = dem.y_coords[0] + dem.cell_size / 2

    polygons = [merged] if isinstance(merged, Polygon) else list(merged.geoms)
    rings = []
    for poly in polygons:
        gx, gy = (np.asarray(v) for v in poly.exterior.coords.xy)
        xs = left + gx * dem.cell_size
        ys = top - gy * dem.cell_size
        lons, lats = dem.transformer_to_lonlat.transform(xs, ys)
        rings.append(list(zip(np.asarray(lons).tolist(), np.asarray(lats).tolist())))
    return rings


def expected_runoff_m3(catchment_area_m2: float, rainfall_mm: float, runoff_coefficient: float) -> float:
    """Rational-method runoff: the rain falling on the catchment that runs off to the site."""
    return catchment_area_m2 * (rainfall_mm / 1000.0) * runoff_coefficient


def build_pond_candidate(flow_model: FlowModel, sink: tuple[int, int]) -> PondCandidate:
    dem = flow_model.dem
    catchment_mask = _delineate_catchment(flow_model, sink)
    catchment_area_m2 = float(catchment_mask.sum()) * dem.cell_size ** 2

    pond_mask, areas, elevations, spill_elevation = _flood_fill_basin(flow_model, sink)
    pond_area_m2 = float(pond_mask.sum()) * dem.cell_size ** 2

    volume_m3 = 0.0
    for i in range(len(areas) - 1):
        volume_m3 += (areas[i] + areas[i + 1]) / 2.0 * (elevations[i + 1] - elevations[i])

    return PondCandidate(
        row=sink[0],
        col=sink[1],
        elevation=float(dem.elevation[sink]),
        catchment_cells=catchment_mask,
        catchment_area_m2=catchment_area_m2,
        pond_mask=pond_mask,
        pond_area_m2=pond_area_m2,
        spill_elevation=spill_elevation,
        volume_m3=float(volume_m3),
        max_depth_m=float(spill_elevation - dem.elevation[sink]),
    )
