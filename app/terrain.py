"""Turn contour lines into a height grid (DEM) and work out how water flows over it.

Steps done here:
1. Turn the contour line points into a grid of elevation values (the DEM).
2. For every grid cell, find which of its 8 neighbours is the steepest way
   downhill. That neighbour is where water from this cell flows to.
3. Add up, for every cell, how many cells upstream eventually flow into it
   (flow accumulation). A high value means a lot of runoff passes through
   that cell.

Nothing here is specific to the sample map: the projection, grid size,
resolution and elevation range are all worked out from whatever contour
lines are passed in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from scipy.interpolate import griddata

from app.kml_parser import ContourLine

# The 8 neighbour cells around a grid cell (row, col offsets), used to find
# which direction water flows downhill.
_NEIGHBOR_OFFSETS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

# Default number of cells along the longer side of the bounding box, used
# when the caller doesn't ask for a specific resolution.
_TARGET_GRID_SIDE = 300

# Hard floor/ceiling on grid size, in cells per side. These apply even when
# the caller asks for a specific cell size, so a request for very fine
# detail can't make the analysis run for an unbounded amount of time.
_MIN_GRID_SIDE = 40
_MAX_GRID_SIDE = 1500


def _utm_crs_for_lonlat(lon: float, lat: float) -> CRS:
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


@dataclass
class Dem:
    elevation: np.ndarray          # (rows, cols) float grid, NaN outside data extent
    valid_mask: np.ndarray         # bool grid, True where elevation is real (not extrapolated)
    cell_size: float               # metres per cell (square cells)
    x_coords: np.ndarray           # (cols,) cell-center x in projected metres
    y_coords: np.ndarray           # (rows,) cell-center y in projected metres, descending
    transformer_to_lonlat: Transformer
    crs: CRS
    contour_interval: float        # vertical spacing between input contour lines, in metres


def _detect_contour_interval(contours: list[ContourLine]) -> float:
    """Work out the spacing between contour lines from the input file itself.

    We read this from the elevations on the original contour lines, not
    from the interpolated grid, because interpolation produces a smooth
    range of values with no fixed step.
    """
    levels = sorted(set(round(c.elevation, 6) for c in contours))
    gaps = [b - a for a, b in zip(levels, levels[1:]) if b - a > 1e-6]
    return min(gaps) if gaps else 1.0


@dataclass
class FlowModel:
    dem: Dem
    flow_to: np.ndarray            # (rows, cols) int, flat index of downhill neighbour, -1 if sink/no-data
    flow_accum_cells: np.ndarray   # (rows, cols) int, number of cells (incl. self) draining through this cell
    order_desc: np.ndarray         # flat indices of valid cells sorted by elevation, high -> low


def build_dem(contours: list[ContourLine], cell_size_m: float | None = None) -> Dem:
    """Build the elevation grid.

    `cell_size_m` lets the caller ask for a specific grid resolution
    (smaller = more detail, but slower to compute). If left as None, a
    resolution is picked automatically from the map's size. Either way,
    the resulting grid is still kept between _MIN_GRID_SIDE and
    _MAX_GRID_SIDE cells per side, so requests for extremely fine detail
    are capped rather than left unbounded.
    """
    if cell_size_m is not None and cell_size_m <= 0:
        raise ValueError("cell_size_m must be greater than 0")

    all_lons = np.concatenate([np.array([p[0] for p in c.points]) for c in contours])
    all_lats = np.concatenate([np.array([p[1] for p in c.points]) for c in contours])
    all_elevs = np.concatenate(
        [np.full(len(c.points), c.elevation) for c in contours]
    )

    center_lon, center_lat = float(np.mean(all_lons)), float(np.mean(all_lats))
    crs = _utm_crs_for_lonlat(center_lon, center_lat)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    to_lonlat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    xs, ys = to_utm.transform(all_lons, all_lats)
    xs, ys = np.asarray(xs), np.asarray(ys)

    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()
    width, height = x_max - x_min, y_max - y_min
    longer_side = max(width, height)

    if cell_size_m is not None:
        cell_size = cell_size_m
    else:
        cell_size = longer_side / _TARGET_GRID_SIDE if longer_side > 0 else 1.0
    n_cols = int(np.clip(round(width / cell_size), _MIN_GRID_SIDE, _MAX_GRID_SIDE))
    n_rows = int(np.clip(round(height / cell_size), _MIN_GRID_SIDE, _MAX_GRID_SIDE))
    # Recompute cell_size from the clamped grid so cells stay square and cover the extent.
    cell_size = max(width / n_cols, height / n_rows)

    x_coords = x_min + (np.arange(n_cols) + 0.5) * cell_size
    y_coords = y_max - (np.arange(n_rows) + 0.5) * cell_size  # descending: row 0 = north
    grid_x, grid_y = np.meshgrid(x_coords, y_coords)

    points = np.column_stack([xs, ys])
    elevation = griddata(points, all_elevs, (grid_x, grid_y), method="linear")
    valid_mask = ~np.isnan(elevation)

    # Fill extrapolation gaps (outside the convex hull of contour vertices)
    # with nearest-neighbour values so the grid has no holes, but keep
    # valid_mask so downstream steps know which cells are interpolated vs filled.
    if not valid_mask.all():
        nearest = griddata(points, all_elevs, (grid_x, grid_y), method="nearest")
        elevation = np.where(valid_mask, elevation, nearest)

    return Dem(
        elevation=elevation,
        valid_mask=valid_mask,
        cell_size=float(cell_size),
        x_coords=x_coords,
        y_coords=y_coords,
        transformer_to_lonlat=to_lonlat,
        crs=crs,
        contour_interval=_detect_contour_interval(contours),
    )


def compute_flow_model(dem: Dem) -> FlowModel:
    rows, cols = dem.elevation.shape
    elevation = dem.elevation
    flat_elev = elevation.ravel()
    n = flat_elev.size

    flow_to = np.full(n, -1, dtype=np.int64)

    row_idx, col_idx = np.indices((rows, cols))
    row_idx = row_idx.ravel()
    col_idx = col_idx.ravel()

    diag_dist = dem.cell_size * np.sqrt(2)

    steepest_drop = np.zeros(n, dtype=np.float64)
    for dr, dc in _NEIGHBOR_OFFSETS:
        nr, nc = row_idx + dr, col_idx + dc
        in_bounds = (nr >= 0) & (nr < rows) & (nc >= 0) & (nc < cols)
        dist = diag_dist if (dr != 0 and dc != 0) else dem.cell_size

        neighbor_flat = np.where(in_bounds, nr * cols + nc, 0)
        neighbor_elev = np.where(in_bounds, flat_elev[neighbor_flat], np.inf)
        drop = (flat_elev - neighbor_elev) / dist
        drop = np.where(in_bounds, drop, -np.inf)

        better = drop > steepest_drop
        flow_to = np.where(better, neighbor_flat, flow_to)
        steepest_drop = np.where(better, drop, steepest_drop)

    # A cell with no positive-drop neighbour is a sink (local depression) or a no-data cell.
    flow_to = np.where(steepest_drop > 0, flow_to, -1)

    order_desc = np.argsort(-flat_elev, kind="stable")

    flow_accum_cells = np.ones(n, dtype=np.int64)
    for idx in order_desc:
        target = flow_to[idx]
        if target != -1:
            flow_accum_cells[target] += flow_accum_cells[idx]

    return FlowModel(
        dem=dem,
        flow_to=flow_to.reshape(rows, cols),
        flow_accum_cells=flow_accum_cells.reshape(rows, cols),
        order_desc=order_desc,
    )
