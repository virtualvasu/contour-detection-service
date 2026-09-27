"""Restrict an analysis to the land area picked on the map.

The selected area comes in as a GeoJSON Polygon or MultiPolygon in
lon/lat. Contour lines are clipped to it before the terrain model is
built, so pond sites and catchments are only looked for inside the
chosen land.
"""

from __future__ import annotations

import json

from shapely import make_valid
from shapely.geometry import LineString, shape
from shapely.geometry.base import BaseGeometry

from app.kml_parser import ContourLine


def parse_area(text: str) -> BaseGeometry:
    """Turn a GeoJSON string into a polygon geometry, or raise ValueError."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Selected area is not valid JSON") from exc

    if isinstance(data, dict) and data.get("type") == "Feature":
        data = data.get("geometry")
    if not isinstance(data, dict) or data.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("Selected area must be a GeoJSON Polygon or MultiPolygon")

    try:
        area = shape(data)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("Selected area has malformed coordinates") from exc

    if not area.is_valid:
        # e.g. a hand-drawn polygon whose edges cross each other
        area = make_valid(area)
    if area.is_empty or area.area == 0:
        raise ValueError("Selected area is empty")
    return area


def clip_contours(contours: list[ContourLine], area: BaseGeometry) -> list[ContourLine]:
    """Keep only the parts of each contour line that fall inside `area`."""
    clipped: list[ContourLine] = []
    for contour in contours:
        line = LineString(contour.points)
        if not area.intersects(line):
            continue
        piece = line.intersection(area)
        for part in getattr(piece, "geoms", [piece]):
            if isinstance(part, LineString) and len(part.coords) >= 2:
                points = [(x, y) for x, y, *_ in part.coords]
                clipped.append(ContourLine(elevation=contour.elevation, points=points))

    if not clipped:
        raise ValueError("The selected area does not contain any contour lines")
    return clipped
