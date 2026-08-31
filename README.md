# Contour Detection Service

Upload a contour map (KML/KMZ) and get back suggested pond sites, each
with its catchment area and estimated storage volume — for pond
planning / rainwater-harvesting site selection.

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
  -F "file=@samples/contours_1m.kml"
```

See [docs/API.md](docs/API.md) for the full request/response reference.

## Run the frontend

A small React app to upload a map, pick a precision, and view results
in the browser.

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. It talks to the API at
`http://127.0.0.1:8000` by default (make sure that's running too); set
`VITE_API_BASE_URL` to point it elsewhere.

## Run tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## How it works

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
6. **Respond** — return ranked pond sites as JSON, each with its
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
  terrain.py      # contour lines -> DEM + flow model
  catchment.py    # flow model -> pond sites, catchments, volumes
  pipeline.py     # wires the above together
  schemas.py      # API response models
  main.py         # FastAPI app and routes
tests/
  test_sample.py  # pipeline + API tests against the sample map
samples/
  contours_1m.kml # sample contour map used for development/testing
docs/
  API.md          # API reference
  REPORT.md       # submission report
frontend/
  src/App.jsx     # upload form + results display
```

## Known limitations / next-phase ideas

- Only the KML/KMZ "elevation in placemark name" convention is
  supported; other contour export formats would need a new parser.
- Grid resolution can be controlled via the `cell_size_m` query
  parameter on `/analyzeContour` (see `docs/API.md`), trading precision
  for compute time. It's still capped at 40–1500 cells per side as a
  safety limit against runaway requests.
- Pond depth is capped at a fixed 5 m assumption; this could become a
  request parameter.
- Only the top-ranked depressions become candidates; multi-pond
  trade-off optimization (e.g. maximizing total storage for a given
  number of ponds) is not yet done.
