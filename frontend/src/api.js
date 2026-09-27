// Calls to the analysis API. Both endpoints take the contour map as a file
// upload; the API keeps no state between requests, so any backend machine
// behind the load balancer can answer either call.

// In production the frontend and API are served from the same origin (nginx
// proxies /api), so the default is a relative path. In development point it
// at the uvicorn server with VITE_API_BASE_URL.
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

function endpoint(path, params = {}) {
  const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined),
  )
  const qs = query.toString()
  return `${base}${path}${qs ? `?${qs}` : ''}`
}

function errorMessage(status, body) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  if (status === 503) return 'The server is busy with other analyses. Try again in a few seconds.'
  if (status === 413) return 'This file is too large for the server to accept.'
  return `The server returned an error (${status}).`
}

async function request(url, options) {
  let response
  try {
    response = await fetch(url, options)
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error('Could not reach the analysis server. Check that it is running.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(errorMessage(response.status, body))
  return body
}

export function previewMap(file, signal) {
  const formData = new FormData()
  formData.append('contour_map', file)
  return request(endpoint('/previewContour'), { method: 'POST', body: formData, signal })
}

// Rivers, lakes and ponds (from OpenStreetMap) within lon/lat bounds, to
// leave out of the analysis.
export function fetchWater(bounds, signal) {
  return request(endpoint('/waterBodies', bounds), { signal })
}

export function analyzeArea({ file, area, exclude, cellSize, rainfallMm, runoffCoefficient, signal }) {
  const formData = new FormData()
  formData.append('contour_map', file)
  formData.append('area', JSON.stringify(area))
  if (exclude) formData.append('exclude', JSON.stringify(exclude))
  const url = endpoint('/analyzeContour', {
    cell_size_m: cellSize,
    rainfall_mm: rainfallMm,
    runoff_coefficient: runoffCoefficient,
    include_contours: 'false',
  })
  return request(url, { method: 'POST', body: formData, signal })
}
