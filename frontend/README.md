# Pond Site Finder — frontend

React + Leaflet app for the contour analysis API: load a contour map,
select the land on the map, and see the suggested pond sites, their
catchments and the water they can collect drawn over it.

```bash
npm install
npm run dev      # http://127.0.0.1:5173, forwards /api to http://127.0.0.1:8000
npm run build    # production bundle in dist/, served by the gateway
npm run lint
```

`API_PROXY_TARGET` changes where the dev server forwards `/api`;
`VITE_API_BASE_URL` changes the API path baked into a build (default
`/api`, which the nginx gateway in `../deploy` serves).

## Files

- `src/App.jsx` — the step-by-step panel and app state
- `src/MapView.jsx` — the map: base layers, contours, area drawing and
  result overlays
- `src/Results.jsx` — ranked pond site list, legend and terrain details
- `src/api.js` — calls to `/previewContour` and `/analyzeContour`
- `src/geo.js`, `src/format.js`, `src/palette.js` — geometry, number
  formatting and map colours
