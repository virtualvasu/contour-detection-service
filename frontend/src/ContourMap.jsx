// Draws the whole uploaded contour map, with every pond site's catchment
// and pond boundary overlaid on top of it — the "show me the real map"
// view, as opposed to BoundaryDiagram's single-site close-up.

import { lineToPath, makeProjector, ringToPath } from './geo'

const WIDTH = 720
const HEIGHT = 560
const PADDING = 20

export default function ContourMap({ contours, pondSites }) {
  const allPoints = [
    ...contours.flatMap((c) => c.points.map((p) => [p.lon, p.lat])),
    ...pondSites.flatMap((s) => s.catchment_boundary.flatMap((r) => r.map((p) => [p.lon, p.lat]))),
  ]

  if (allPoints.length === 0) {
    return <p className="diagram-empty">No map geometry to display.</p>
  }

  const project = makeProjector(allPoints, { width: WIDTH, height: HEIGHT, padding: PADDING })

  return (
    <div className="contour-map">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
        aria-label="Contour map with pond and catchment boundaries overlaid">
        <rect x={0} y={0} width={WIDTH} height={HEIGHT} className="map-background" />

        {contours.map((c, i) => (
          <path key={i} d={lineToPath(c.points, project)} className="contour-line">
            <title>{c.elevation_m.toFixed(1)} m</title>
          </path>
        ))}

        {pondSites.map((site) => (
          <path key={`catchment-${site.rank}`}
            d={site.catchment_boundary.map((r) => ringToPath(r, project)).join(' ')}
            className="catchment-shape">
            <title>Site #{site.rank} catchment — {site.catchment_area_hectares.toFixed(2)} ha</title>
          </path>
        ))}

        {pondSites.map((site) => (
          <path key={`pond-${site.rank}`}
            d={site.pond_boundary.map((r) => ringToPath(r, project)).join(' ')}
            className="pond-shape">
            <title>Site #{site.rank} pond — {site.pond_area_m2.toFixed(0)} m²</title>
          </path>
        ))}

        {pondSites.map((site) => {
          const [x, y] = project([site.location.lon, site.location.lat])
          return (
            <g key={`label-${site.rank}`}>
              <circle cx={x} cy={y} r={4} className="site-marker" />
              <text x={x + 7} y={y - 7} className="site-label">#{site.rank}</text>
            </g>
          )
        })}
      </svg>
      <div className="diagram-legend">
        <span><i className="swatch contour-swatch" /> Contour lines</span>
        <span><i className="swatch catchment-swatch" /> Catchment (drains here)</span>
        <span><i className="swatch pond-swatch" /> Pond footprint (dig here)</span>
      </div>
    </div>
  )
}
