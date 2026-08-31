# Contour-Based Pond Catchment Analysis — Report

> Draft skeleton. Fill in each section before submission.

## 1. GitHub Repository

- Repo link: TODO

## 2. Working API

- Route: `POST /analyzeContour`
- Base URL (local / deployed): TODO
- Interactive docs: `<base-url>/docs`

## 3. Catchment Estimation Approach

TODO — summarize the pipeline (see `README.md` for the current technical
write-up to draw from):
1. Parse elevation-labelled contour lines from the uploaded KML/KMZ.
2. Reproject to metres and interpolate a DEM raster.
3. Compute D8 flow direction and flow accumulation.
4. Rank natural depressions by contributing drainage area to pick pond
   site(s).
5. Delineate each site's catchment via upstream traversal of the flow
   graph.
6. Estimate pond storage volume via flood-fill + area-elevation method,
   capped at a realistic pond depth.

## 4. Demonstration (sample contour map)

TODO — include: request example, response JSON (or summarized table of
pond sites), and ideally a map screenshot of the catchment boundary.

## 5. API Documentation

TODO — see `docs/API.md` for the endpoint reference; summarize or embed
the key parts here.

## 6. Extensibility Notes (future phases)

TODO — call out what is already generic (projection, grid resolution,
contour interval detection, sink ranking) vs. what would need work for
very different terrain types or non-KML formats.
