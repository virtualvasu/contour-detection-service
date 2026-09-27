// Small geometry helpers for moving between the API's {lon, lat} points,
// Leaflet's [lat, lng] pairs and GeoJSON's [lon, lat] coordinates.

const EARTH_RADIUS_M = 6378137

const toRad = (deg) => (deg * Math.PI) / 180

// API points -> Leaflet positions.
export function toLatLngs(points) {
  return points.map((p) => [p.lat, p.lon])
}

// Area of one GeoJSON ring on the sphere, in m² (same method as geojson-area).
function ringArea(ring) {
  if (ring.length < 3) return 0
  let sum = 0
  for (let i = 0; i < ring.length; i++) {
    const [lon1, lat1] = ring[i]
    const [lon2, lat2] = ring[(i + 1) % ring.length]
    sum += toRad(lon2 - lon1) * (2 + Math.sin(toRad(lat1)) + Math.sin(toRad(lat2)))
  }
  return Math.abs((sum * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2)
}

function polygonArea(rings) {
  const [outer, ...holes] = rings
  return ringArea(outer) - holes.reduce((total, hole) => total + ringArea(hole), 0)
}

// Area of a GeoJSON Polygon or MultiPolygon, in m².
export function geometryArea(geometry) {
  if (geometry.type === 'Polygon') return polygonArea(geometry.coordinates)
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.reduce((total, rings) => total + polygonArea(rings), 0)
  }
  return 0
}

// The API's {min_lon, ...} bounds as a GeoJSON rectangle, for "use the whole map".
export function boundsToPolygon(b) {
  return {
    type: 'Polygon',
    coordinates: [[
      [b.min_lon, b.min_lat],
      [b.max_lon, b.min_lat],
      [b.max_lon, b.max_lat],
      [b.min_lon, b.max_lat],
      [b.min_lon, b.min_lat],
    ]],
  }
}

// The API's bounds as Leaflet bounds.
export function toLeafletBounds(b) {
  return [[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]]
}

// Leaflet bounds around every point of a set of API rings.
export function ringsBounds(rings) {
  const lats = rings.flatMap((r) => r.map((p) => p.lat))
  const lons = rings.flatMap((r) => r.map((p) => p.lon))
  return [[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]]
}

// Flat lon/lat -> SVG projection, used by the SVG diagrams.
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
