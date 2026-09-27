# API Documentation

Interactive Swagger UI is also served at `/docs` (and OpenAPI JSON at
`/openapi.json`) whenever the app is running.

## POST /analyzeContour

Analyzes an uploaded contour map and returns suggested pond sites with
their catchment area and estimated storage volume.

**Request**

- Content type: `multipart/form-data`
- Field: `contour_map` (also accepted: `file`) — a `.kml` or `.kmz`
  contour map, where each contour line is a `Placemark` whose `<name>`
  contains the elevation value (this is the standard shape produced by
  common contour-generation tools, including the sample file in
  `samples/`).
- Query parameter `cell_size_m` (optional, float, must be `> 0`) — the
  size of one grid cell in metres, i.e. how fine a resolution the terrain
  is analyzed at. Smaller values give more precise pond/catchment
  boundaries but take longer to compute (see table below). If omitted, a
  resolution is picked automatically from the map's size (targeting
  ~300 cells along the longer side). Whatever value is requested, the
  grid is still capped between 40 and `MAX_GRID_SIDE` (default 1000)
  cells per side as a safety limit, so an extreme request degrades to the
  closest allowed resolution rather than running out of time or memory.
- Query parameters `rainfall_mm` (optional, default `1200`, `0 < x ≤ 10000`)
  and `runoff_coefficient` (optional, default `0.3`, `0 < x ≤ 1`) — the
  rainfall and the share of it that runs off the land, used to estimate
  how much water each site can expect to collect. The defaults are a
  typical annual rainfall for central India and a common coefficient for
  rural, partly cultivated land; pass the values for the area being
  planned for better estimates.
- Query parameter `include_contours` (optional, default `true`) — pass
  `false` to leave `contours` empty in the response, e.g. when the client
  already has them from `/previewContour`. On the sample map this shrinks
  the gzipped response from ~90 KB to ~1.5 KB.
- Form field `area` (optional) — the land area to analyze, as a GeoJSON
  `Polygon` or `MultiPolygon` (or a `Feature` wrapping one) in lon/lat.
  Contour lines are clipped to it, and pond sites and catchments are only
  looked for inside it. Omit it to analyze the whole map. Selecting a
  smaller area also makes the analysis faster.
- Form field `exclude` (optional) — land to leave out, in the same GeoJSON
  forms as `area`; typically the rivers, lakes and ponds returned by
  `GET /waterBodies`. It is cut out of `area` (or the whole map), so no
  pond site, pond or catchment is placed in it. Without it, a river bed —
  the lowest ground around — is readily picked as a pond site.

Example — default resolution:

```bash
curl -X POST http://localhost:8000/analyzeContour \
  -F "contour_map=@samples/contours_1m.kml"
```

Example — analyze only a selected area:

```bash
curl -X POST http://localhost:8000/analyzeContour \
  -F "contour_map=@samples/contours_1m.kml" \
  -F 'area={"type":"Polygon","coordinates":[[[81.2814,21.2398],[81.2970,21.2398],[81.2970,21.2636],[81.2814,21.2636],[81.2814,21.2398]]]}'
```

Example — request finer 3m cells:

```bash
curl -X POST "http://localhost:8000/analyzeContour?cell_size_m=3" \
  -F "contour_map=@samples/contours_1m.kml"
```

Rough timing and peak worker memory on the sample map (6.7 MB KML, 1355
contour lines, 159k vertices), whole map, one worker:

| `cell_size_m` | Grid size | Time | Peak memory |
|---|---|---|---|
| ~10.8 (default) | 243 × 300 | ~2.5 s | ~280 MB |
| 5 | 525 × 648 | ~3.2 s | ~285 MB |
| 3.2 or less (hits the 1000-cell cap) | 810 × 1000 | ~6 s | ~295 MB |

Actual times depend on the size and density of the uploaded map, not
just the requested cell size. Selecting a smaller area is faster.

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
  "runoff": { "rainfall_mm": 1200.0, "runoff_coefficient": 0.3 },
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
      "expected_runoff_m3": 15678.3,
      "collectible_volume_m3": 5662.8,
      "catchment_boundary": [ [ { "lon": 81.299, "lat": 21.259 }, "..." ] ],
      "pond_boundary": [ [ { "lon": 81.300, "lat": 21.260 }, "..." ] ]
    }
  ],
  "contours": [
    { "elevation_m": 277.0, "points": [ { "lon": 81.286, "lat": 21.263 }, "..." ] }
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
| `runoff` | The rainfall and runoff coefficient the estimates below were computed with |
| `pond_sites[].expected_runoff_m3` | Rainfall runoff expected to reach the site: catchment area × rainfall × runoff coefficient |
| `pond_sites[].collectible_volume_m3` | Water that can actually be collected: the smaller of the expected runoff and the storage volume |
| `pond_sites[].catchment_boundary` / `pond_boundary` | Polygon ring(s) in `[lon, lat]`, one outer ring per disconnected patch |
| `contours` | The input contour lines themselves (elevation + point path), simplified for display — for drawing the pond/catchment boundaries in context on the original map, e.g. on a canvas/SVG in a UI |

Sites are returned ranked (`rank` 1 = best), ordered by estimated
storage volume (largest first), up to 3 sites. Candidates are first
shortlisted by contributing catchment area (to filter out
interpolation-noise depressions), then the shortlist is re-ranked by
volume for the final result.

`contours` is simplified (Douglas-Peucker, tolerance ~half a grid cell)
so it's light enough to send back on every request — on the sample map
it cuts ~159k source points down to ~17k while keeping the same shape at
the analysis grid's resolution.

**Error responses**

| Status | Cause |
|---|---|
| `400` | File extension is not `.kml`/`.kmz`, or the uploaded file is empty |
| `413` | File is larger than `MAX_UPLOAD_MB` (default 20 MB) |
| `422` | No file was sent under `contour_map` (or `file`), the file could not be parsed as valid KML/KMZ, `area` is not a valid GeoJSON polygon or contains no contour lines, the area has more than `MAX_CONTOUR_VERTICES` contour points (select a smaller area), or no usable contour lines / no plausible pond depressions were found |
| `503` | The worker is already busy with its maximum number of analyses/previews and no slot freed up in time; retry after the `Retry-After` header's number of seconds |

## GET /waterBodies

Rivers, canals, lakes, reservoirs and existing ponds within some bounds,
looked up on OpenStreetMap (through the public Overpass API), as one
geometry to pass as `exclude` to `/analyzeContour`. A 10 m margin is kept
around each; rivers and canals mapped only as a centre line are widened
to 15 m and 5 m each side. Small streams and drains are not included,
since farm ponds and check dams are often built on them.

**Request** — query parameters `min_lon`, `min_lat`, `max_lon`, `max_lat`
(at most 0.5° per side).

**Response** — `200 OK`:

```jsonc
{
  "status": "found",          // or "none" (no mapped water) or "unavailable"
  "geometry": { "type": "MultiPolygon", "coordinates": [ "..." ] }   // null unless "found"
}
```

`"unavailable"` means no Overpass server answered in time; the analysis
still works without `exclude`. The public servers take ~2–20 s and are
sometimes overloaded, so each configured server is tried in turn, answers
are cached per area, and after all servers fail, lookups pause for 10 s.
The API machines need internet access for this endpoint.

## POST /previewContour

Parses an uploaded contour map just far enough to draw it — no terrain
model or analysis — so a client can show the map and let the user pick an
area before calling `/analyzeContour`. Takes ~0.4 s on the sample map.

**Request** — same file field as `/analyzeContour` (`contour_map`, or
`file`), no other parameters.

**Response** — `200 OK`:

```jsonc
{
  "source_file": "contours_1m.kml",
  "bounds": { "min_lon": 81.2814, "min_lat": 21.2398, "max_lon": 81.3126, "max_lat": 21.2636 },
  "min_elevation_m": 267.0,
  "max_elevation_m": 298.0,
  "contour_interval_m": 1.0,
  "contour_line_count": 1355,
  "contours": [
    { "elevation_m": 277.0, "points": [ { "lon": 81.286, "lat": 21.263 }, "..." ] }
  ]
}
```

Contours are simplified the same way as in `/analyzeContour` at its
default resolution. Error responses are the same as for `/analyzeContour`
(`400`, `413`, `422`, `503`). Previews share the worker's slot limit with
analyses, since both parse the whole map.

## Limits and configuration

The defaults are sized for machines with 512 MB of RAM: a worker uses
~100 MB idle and stays under ~330 MB while working (checked under a 380 MB
memory cap with the heaviest requests the limits allow). Set through
environment variables on the API process:

| Variable | Default | Meaning |
|---|---|---|
| `MAX_UPLOAD_MB` | `20` | Largest accepted upload; parsing takes roughly 8× the KML's size in memory |
| `MAX_CONTOUR_VERTICES` | `200000` | Most contour points analyzed at once, counted after clipping to the selected area (the sample map has 159k); triangulating them is most of an analysis's memory |
| `MAX_GRID_SIDE` | `1000` | Largest analysis grid, in cells per side |
| `MAX_CONCURRENT_ANALYSES` | `1` | Analyses and previews one worker process runs at once |
| `ANALYSIS_QUEUE_TIMEOUT_S` | `30` | How long a request waits for a free slot before getting `503` |
| `OVERPASS_URLS` | overpass-api.de, then maps.mail.ru | Comma-separated Overpass servers `/waterBodies` tries in order |
| `WATER_LOOKUP_TIMEOUT_S` | `20` | How long `/waterBodies` waits for each Overpass server |

KMZ archives whose KML would unzip to more than 20 MB are rejected with
`422`. Responses are gzipped when the client accepts it. On machines with
more memory, raise the limits and run more workers (`WORKERS=4
deploy/run_api.sh`).

## GET /health

Returns `{"status": "ok"}`. Used for liveness checks.
