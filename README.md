# Contour Detection Service

Upload a contour map (KML/KMZ), select a stretch of land on the map, and
get back suggested pond sites, each with its catchment area, storage
volume and the rainwater it can be expected to collect, drawn on the map
— for pond planning / rainwater-harvesting site selection.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run the API

```bash
source venv/bin/activate
uvicorn app.main:app --reload
```

The API is now at `http://127.0.0.1:8000`. Interactive docs at
`http://127.0.0.1:8000/docs`.

Try it with the provided sample map:

```bash
curl -X POST http://127.0.0.1:8000/analyzeContour \
  -F "contour_map=@samples/contours_1m.kml"
```

See [docs/API.md](docs/API.md) for the full request/response reference.

## Run the frontend

A React + Leaflet app: load a contour map, select the land on the map,
and see the suggested pond sites drawn over it.

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The dev server forwards `/api` to the API
at `http://127.0.0.1:8000` (make sure that's running too); set
`API_PROXY_TARGET` to point it elsewhere.

Using the app:

1. **Load a contour map** — choose a `.kml`/`.kmz` file. Its contour
   lines appear on the map (every fifth one drawn heavier).
2. **Select the land** — draw a rectangle (click two opposite corners),
   draw a free shape (click each corner, then the first one again), or
   take the whole map. Esc stops drawing.
3. **Rainfall and land cover** — the annual rainfall and the kind of
   land, which sets how much of the rain runs off to a pond; optionally a
   finer analysis grid.
4. **Find pond sites** — each suggested site is drawn on the map with its
   catchment (dashed outline in the site's colour), its pond footprint
   (blue) and a numbered pin at the pond location, and listed with the
   water it can collect, its catchment area, pond size and depth.
   Selecting a site zooms to it. Street/satellite base maps and the
   layers can be switched from the map's layer control.

## Run tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## How it works

0. **Select** — if an area was selected on the map, contour lines are
   clipped to it and everything below only considers land inside it
   (`app/selection.py`).
1. **Parse** — read every elevation-labelled contour line out of the
   uploaded KML/KMZ (`app/kml_parser.py`).
2. **Build terrain model** — reproject the contour points to metres
   (auto-picking the correct UTM zone) and interpolate them into a
   regular elevation grid, a DEM (`app/terrain.py`).
3. **Route water** — for every grid cell, find its steepest downhill
   neighbour (D8 flow direction), then compute how much upstream area
   drains through each cell (flow accumulation) — same file.
4. **Pick pond sites** — rank natural depressions (cells with no
   downhill neighbour) by how much land drains into them, and delineate
   each one's full catchment by walking the flow map upstream
   (`app/catchment.py`).
5. **Estimate volume** — raise the water level at each site step by
   step (using the contour interval detected from the input) and track
   how the flooded area grows, then integrate area vs. elevation to get
   a storage volume. The rise is capped at a realistic pond depth (5 m)
   since a pond is a built structure, not a lake filled to its natural
   rim.
6. **Expected water** — the runoff reaching each site is its catchment
   area × rainfall × runoff coefficient (the share of rain that runs off
   rather than soaking in); the water that can actually be collected is
   the smaller of that and the pond's storage volume.
7. **Respond** — return ranked pond sites as JSON, each with its
   location, catchment area, pond footprint, and estimated volume
   (`app/pipeline.py`, `app/schemas.py`, `app/main.py`).

Nothing in the pipeline is specific to the sample map: grid resolution,
UTM zone, contour interval, and candidate sites are all derived from
whatever file is uploaded, so it should generalize to other contour
maps in the same KML/KMZ style.

## Project layout

```
app/
  kml_parser.py   # KML/KMZ -> contour lines
  selection.py    # selected area (GeoJSON) -> clipped contour lines
  terrain.py      # contour lines -> DEM + flow model
  catchment.py    # flow model -> pond sites, catchments, volumes, runoff
  pipeline.py     # wires the above together (analysis and map preview)
  schemas.py      # API response models
  main.py         # FastAPI app, routes and resource limits
tests/            # pipeline, API, selection, runoff and parser tests
samples/
  contours_1m.kml # sample contour map used for development/testing
docs/
  API.md          # API reference, limits and configuration
frontend/
  src/App.jsx     # the step-by-step panel
  src/MapView.jsx # Leaflet map: contours, area drawing, result overlays
  src/Results.jsx # ranked pond site list
  src/api.js      # calls to the API
deploy/
  run_api.sh            # start the API on a backend machine
  start_gateway.sh      # start nginx in front of the API machines
  nginx.conf.template   # gateway config (frontend + load balancing)
loadtest/
  load_test.py    # stress test at increasing numbers of users
```

## Deploying on the lab machines

The deployment targets four machines with 512 MB of RAM each. The API is
stateless (every request carries the contour map), so any machine can
answer any request and capacity grows by adding machines:

```
                 browser
                    |
        machine 1: nginx (:8080) -- serves frontend/dist
          |        |        |        |
        API      API      API      API      (one per machine, :8000)
     machine 1 machine 2 machine 3 machine 4
```

1. **Every machine** — clone the repo, create the venv (see *Setup*), then
   start the API:

   ```bash
   deploy/run_api.sh          # PORT=8000, one worker
   ```

   One worker handles one analysis at a time (~100 MB idle, ~300 MB while
   working), leaving room for the OS within 512 MB. Further requests wait
   in a short queue, then get `503` so the gateway can try another machine.

2. **On your own machine** — build the frontend (npm needs more memory
   than the lab machines have) and copy `frontend/dist` to machine 1:

   ```bash
   cd frontend && npm ci && npm run build
   scp -r dist <user>@<machine-1>:<repo>/frontend/
   ```

3. **Machine 1** — start the gateway with all four API addresses:

   ```bash
   deploy/start_gateway.sh 10.1.75.53:8000 <machine-2>:8000 <machine-3>:8000 <machine-4>:8000
   ```

   It runs nginx without root from `deploy/`, serves the app on port 8080
   (`LISTEN_PORT` to change) and sends each `/api` request to the least
   busy machine, retrying on another one if a machine is busy or down.

Memory limits (upload size, contour points per analysis, grid size) are
listed in `docs/API.md`; they keep a worker inside 512 MB, and were
checked under a 380 MB memory cap.

## Load testing

`loadtest/load_test.py` simulates increasing numbers of users each
uploading the map and waiting for the result, and reports throughput,
latency percentiles and busy/failed requests per level:

```bash
source venv/bin/activate
python loadtest/load_test.py --url http://<machine-1>:8080/api --levels 1,4,8,16 --requests 16
```

Run it from a machine other than the lab machines so the test itself
doesn't take their memory. Pass `--area area.geojson` to test with a
selected area instead of the whole map.

## Known limitations / next-phase ideas

- Only the KML/KMZ "elevation in placemark name" convention is
  supported; other contour export formats would need a new parser.
- Grid resolution can be controlled via the `cell_size_m` query
  parameter (the "Detail" option in the app), trading precision for
  compute time; it is capped at 40–1000 cells per side to bound time and
  memory.
- Maps with more than 200k contour points can't be analyzed whole on a
  512 MB machine; select part of the map instead (or raise
  `MAX_CONTOUR_VERTICES` on a bigger machine).
- Pond depth is capped at a fixed 5 m assumption; this could become a
  request parameter.
- Rainfall and runoff coefficient are single values for the whole area;
  land cover could vary per catchment.
- Only the top-ranked depressions become candidates; multi-pond
  trade-off optimization (e.g. maximizing total storage for a given
  number of ponds) is not yet done.
