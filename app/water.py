"""Find rivers, lakes and other water bodies to leave out of an analysis.

A river bed is the lowest ground around, so the terrain analysis on its
own readily picks one as a pond site. Contour lines can't tell a river
channel from a natural hollow, so the water bodies come from
OpenStreetMap instead (through the Overpass API) and are cut out of the
analyzed area.

Rivers, canals, lakes, reservoirs and existing ponds are left out. Small
streams and drains are deliberately kept: those are often exactly where
farm ponds and check dams get built.
"""

from __future__ import annotations

import os
import threading
import time
from functools import lru_cache

import httpx
import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon, box, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, transform, unary_union

OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
USER_AGENT = "contour-detection-service/0.1 (pond site planning)"

# Keep the analysis responsive when OpenStreetMap is slow or down: give up
# after LOOKUP_TIMEOUT_S, and after a failure skip lookups entirely for
# RETRY_AFTER_FAILURE_S instead of making every request wait again.
LOOKUP_TIMEOUT_S = float(os.environ.get("WATER_LOOKUP_TIMEOUT_S", "10"))
RETRY_AFTER_FAILURE_S = 20

# Largest area, in degrees per side, that water is looked up for; keeps
# queries to the shared Overpass servers reasonable.
MAX_LOOKUP_SPAN_DEG = 0.5

# Distance kept from the water's edge, so a pond isn't suggested right on
# the bank.
WATER_MARGIN_M = 10

# Rivers and canals that are only mapped as a centre line get this half
# width. Where OpenStreetMap also has the river's full outline (as for
# most large rivers), that outline is used as well.
LINE_HALF_WIDTH_M = {"river": 15, "canal": 5}


class WaterLookupError(Exception):
    """OpenStreetMap couldn't be asked about water in the area."""


_state_lock = threading.Lock()
_unavailable_until = 0.0


def _is_water_area(tags: dict) -> bool:
    return (
        tags.get("natural") == "water"
        or tags.get("waterway") == "riverbank"
        or tags.get("landuse") == "reservoir"
    )


def _query(bounds: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bounds
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return (
        f"[out:json][timeout:{int(LOOKUP_TIMEOUT_S)}];("
        f'nwr["natural"="water"]({bbox});'
        f'nwr["waterway"="riverbank"]({bbox});'
        f'nwr["landuse"="reservoir"]({bbox});'
        f'way["waterway"~"^(river|canal)$"]({bbox});'
        ");out geom;"
    )


def _fetch_elements(bounds: tuple[float, float, float, float]) -> list[dict]:
    try:
        response = httpx.post(
            OVERPASS_URL,
            data={"data": _query(bounds)},
            headers={"User-Agent": USER_AGENT},
            timeout=LOOKUP_TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json()["elements"]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise WaterLookupError(str(exc)) from exc


def _lonlat(points: list[dict]) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in points]


def water_geometry(elements: list[dict], bounds: tuple[float, float, float, float]) -> BaseGeometry | None:
    """Turn Overpass elements into one lon/lat geometry of the water to
    leave out (margin included), clipped to `bounds`. None if there is none."""
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    zone = int((center_lon + 180) // 6) + 1
    utm = CRS.from_epsg((32600 if center_lat >= 0 else 32700) + zone)
    to_m = Transformer.from_crs("EPSG:4326", utm, always_xy=True).transform
    to_deg = Transformer.from_crs(utm, "EPSG:4326", always_xy=True).transform

    shapes: list[BaseGeometry] = []
    for element in elements:
        tags = element.get("tags", {})
        if element["type"] == "way" and "geometry" in element:
            coords = _lonlat(element["geometry"])
            if _is_water_area(tags) and len(coords) >= 4 and coords[0] == coords[-1]:
                shapes.append(transform(to_m, Polygon(coords)).buffer(WATER_MARGIN_M))
            elif tags.get("waterway") in LINE_HALF_WIDTH_M and len(coords) >= 2:
                half_width = LINE_HALF_WIDTH_M[tags["waterway"]]
                shapes.append(transform(to_m, LineString(coords)).buffer(half_width + WATER_MARGIN_M))
        elif element["type"] == "relation" and tags.get("type") == "multipolygon" and _is_water_area(tags):
            rings = {"outer": [], "inner": []}
            for member in element.get("members", []):
                if member.get("type") == "way" and member.get("role") in rings and len(member.get("geometry", [])) >= 2:
                    rings[member["role"]].append(LineString(_lonlat(member["geometry"])))
            outer = unary_union(list(polygonize(rings["outer"])))
            inner = unary_union(list(polygonize(rings["inner"])))
            if not outer.is_empty:
                shapes.append(transform(to_m, outer.difference(inner)).buffer(WATER_MARGIN_M))

    if not shapes:
        return None
    water = transform(to_deg, unary_union(shapes)).intersection(box(*bounds))
    return None if water.is_empty else water


def water_geojson(geometry: BaseGeometry) -> dict:
    """The polygons of `geometry` as a GeoJSON MultiPolygon, to ~0.1 m."""
    parts = [g for g in getattr(geometry, "geoms", [geometry]) if isinstance(g, (Polygon, MultiPolygon))]
    polygons = [p for part in parts for p in getattr(part, "geoms", [part])]
    return mapping(shapely.set_precision(MultiPolygon(polygons), 1e-6))


@lru_cache(maxsize=32)
def _cached_water(bounds: tuple[float, float, float, float]) -> BaseGeometry | None:
    return water_geometry(_fetch_elements(bounds), bounds)


def find_water(bounds: tuple[float, float, float, float]) -> BaseGeometry | None:
    """Water to leave out within lon/lat `bounds`, or None if there is none.

    Raises WaterLookupError if OpenStreetMap can't be reached, or failed
    recently. Results are cached per area (rounded to ~10 m), since the
    same area is often analyzed repeatedly with different settings.
    """
    global _unavailable_until
    with _state_lock:
        if time.monotonic() < _unavailable_until:
            raise WaterLookupError("OpenStreetMap was unavailable a moment ago")

    # round outwards, so the cached area always covers the requested one
    min_lon, min_lat, max_lon, max_lat = bounds
    rounded = (
        float(np.floor(min_lon * 1e4) / 1e4),
        float(np.floor(min_lat * 1e4) / 1e4),
        float(np.ceil(max_lon * 1e4) / 1e4),
        float(np.ceil(max_lat * 1e4) / 1e4),
    )
    try:
        return _cached_water(rounded)
    except WaterLookupError:
        with _state_lock:
            _unavailable_until = time.monotonic() + RETRY_AFTER_FAILURE_S
        raise
