// Draws a small, self-contained shape diagram for one pond site: the
// catchment outline (the land draining into the site) and the pond
// footprint (the area that would actually be under water), both already
// computed by the backend as lon/lat polygons.

import { makeProjector, ringToPath } from './geo'

const SIZE = 220
const PADDING = 16

export default function BoundaryDiagram({ site }) {
  const points = [
    ...site.catchment_boundary.flatMap((r) => r.map((p) => [p.lon, p.lat])),
    ...site.pond_boundary.flatMap((r) => r.map((p) => [p.lon, p.lat])),
  ]
  if (points.length === 0) {
    return <p className="diagram-empty">No boundary geometry returned for this site.</p>
  }

  const project = makeProjector(points, { width: SIZE, height: SIZE, padding: PADDING })
  const catchmentPath = site.catchment_boundary.map((ring) => ringToPath(ring, project)).join(' ')
  const pondPath = site.pond_boundary.map((ring) => ringToPath(ring, project)).join(' ')
  const [siteX, siteY] = project([site.location.lon, site.location.lat])

  return (
    <div className="diagram">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width={SIZE} height={SIZE} role="img"
        aria-label={`Catchment and pond boundary for site ${site.rank}`}>
        <path d={catchmentPath} className="catchment-shape">
          <title>Catchment boundary — {site.catchment_area_hectares.toFixed(2)} ha</title>
        </path>
        <path d={pondPath} className="pond-shape">
          <title>Pond footprint — {site.pond_area_m2.toFixed(0)} m², {site.max_depth_m.toFixed(1)} m deep</title>
        </path>
        <circle cx={siteX} cy={siteY} r={3.5} className="site-marker">
          <title>Pour point — {site.location.lat.toFixed(5)}, {site.location.lon.toFixed(5)}</title>
        </circle>
      </svg>
      <div className="diagram-legend">
        <span><i className="swatch catchment-swatch" /> Catchment (drains here)</span>
        <span><i className="swatch pond-swatch" /> Pond footprint (dig here)</span>
      </div>
    </div>
  )
}
