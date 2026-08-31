// Shared helpers for turning lon/lat polygons into SVG paths.
//
// Projection is a simple flat scaling of longitude/latitude to pixels, with
// longitude corrected by cos(latitude) so shapes aren't stretched. Good
// enough for areas a few kilometres across — no need for a real map
// projection library at this scale.

export function makeProjector(points, { width, height, padding = 0 }) {
  const lons = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const midLatRad = ((minLat + maxLat) / 2) * (Math.PI / 180)
  const lonScale = Math.cos(midLatRad)

  const spanX = (maxLon - minLon) * lonScale || 1e-9
  const spanY = maxLat - minLat || 1e-9
  const scale = Math.min(
    (width - 2 * padding) / spanX,
    (height - 2 * padding) / spanY,
  )
  const drawW = spanX * scale
  const drawH = spanY * scale
  const offsetX = (width - drawW) / 2
  const offsetY = (height - drawH) / 2

  return ([lon, lat]) => {
    const x = offsetX + (lon - minLon) * lonScale * scale
    const y = height - offsetY - (lat - minLat) * scale // flip: north = up
    return [x, y]
  }
}

// Closed shape (polygon boundary) -> SVG path.
export function ringToPath(ring, project) {
  if (ring.length === 0) return ''
  const coords = ring.map((p) => project([p.lon, p.lat]))
  return coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ') + ' Z'
}

// Open line (a contour line) -> SVG path.
export function lineToPath(points, project) {
  if (points.length === 0) return ''
  const coords = points.map((p) => project([p.lon, p.lat]))
  return coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
}
