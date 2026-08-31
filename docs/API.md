# API Documentation

Interactive Swagger UI is also served at `/docs` (and OpenAPI JSON at
`/openapi.json`) whenever the app is running.

## POST /analyzeContour

Analyzes an uploaded contour map and returns suggested pond sites with
their catchment area and estimated storage volume.

**Request**

- Content type: `multipart/form-data`
- Field: `file` — a `.kml` or `.kmz` contour map, where each contour line
  is a `Placemark` whose `<name>` contains the elevation value (this is
  the standard shape produced by common contour-generation tools,
  including the sample file in `samples/`).
- Query parameter `cell_size_m` (optional, float, must be `> 0`) — the
  size of one grid cell in metres, i.e. how fine a resolution the terrain
  is analyzed at. Smaller values give more precise pond/catchment
  boundaries but take longer to compute (see table below). If omitted, a
  resolution is picked automatically from the map's size (targeting
  ~300 cells along the longer side). Whatever value is requested, the
  grid is still capped between 40 and 1500 cells per side as a safety
  limit, so an extreme request degrades to the closest allowed
  resolution rather than hanging.

Example — default resolution:

```bash
curl -X POST http://localhost:8000/analyzeContour \
  -F "file=@samples/contours_1m.kml"
```

Example — request finer 3m cells:

```bash
curl -X POST "http://localhost:8000/analyzeContour?cell_size_m=3" \
  -F "file=@samples/contours_1m.kml"
```

Rough timing on the sample map (6.7MB KML, ~1355 contour lines):

| `cell_size_m` | Grid size | Time |
|---|---|---|
| ~10.8 (default) | 243 × 300 | ~2.2s |
| 5 | 525 × 648 | ~2.5s |
| 3 | 875 × 1081 | ~4.8s |
| ~1.6 (near the 1500-side cap) | 1620 × 2000 | ~6.7s |

Actual times depend on the size and density of the uploaded map, not
just the requested cell size.

**Response** — `200 OK`, JSON body:

```jsonc
{
  "source_file": "contours_1m.kml",
  "terrain": {
    "min_elevation_m": 267.0,
    "max_elevation_m": 298.0,
    "contour_interval_m": 1.0,
    "contour_line_count": 1355,
    "grid_rows": 243,
    "grid_cols": 300,
    "cell_size_m": 10.8,
    "projected_crs": "EPSG:32644"
  },
  "pond_sites": [
    {
      "rank": 1,
      "location": { "lon": 81.30009, "lat": 21.25960 },
      "elevation_m": 274.3,
      "spill_elevation_m": 279.3,
      "max_depth_m": 5.0,
      "catchment_area_m2": 43550.8,
      "catchment_area_hectares": 4.36,
      "pond_area_m2": 2568.7,
      "estimated_volume_m3": 5662.8,
      "catchment_boundary": [ [ { "lon": 81.299, "lat": 21.259 }, "..." ] ],
      "pond_boundary": [ [ { "lon": 81.300, "lat": 21.260 }, "..." ] ]
    }
  ]
}
```

**Field reference**

| Field | Meaning |
|---|---|
| `terrain.contour_interval_m` | Vertical spacing between input contour lines, detected from the file |
| `terrain.cell_size_m` | Resolution of the internal elevation grid used for analysis |
| `terrain.projected_crs` | UTM zone auto-selected from the map's location, used for area/volume math |
| `pond_sites[].location` | Lowest point of the candidate pond (the "pour point") |
| `pond_sites[].spill_elevation_m` | Water level at which the pond would overflow (`elevation_m + max_depth_m`, capped) |
| `pond_sites[].catchment_area_*` | Area of land whose runoff drains to this site |
| `pond_sites[].pond_area_m2` | Surface area of the pond itself at `spill_elevation_m` |
| `pond_sites[].estimated_volume_m3` | Estimated storage volume at `spill_elevation_m` |
| `pond_sites[].catchment_boundary` / `pond_boundary` | Polygon ring(s) in `[lon, lat]`, one outer ring per disconnected patch |

Sites are returned ranked (`rank` 1 = best), ordered by contributing
catchment area, up to 3 sites.

**Error responses**

| Status | Cause |
|---|---|
| `400` | File extension is not `.kml`/`.kmz`, or the uploaded file is empty |
| `422` | File could not be parsed as valid KML/KMZ, or no usable contour lines / no plausible pond depressions were found in it |

## GET /health

Returns `{"status": "ok"}`. Used for liveness checks.
