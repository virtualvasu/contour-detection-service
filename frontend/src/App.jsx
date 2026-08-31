import { useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// Human-friendly precision presets mapped to the backend's cell_size_m
// (metres per grid cell). Smaller cell size = more detail, slower to run.
const PRECISION_OPTIONS = [
  { label: 'Auto (recommended)', value: '' },
  { label: 'Fast (20m cells)', value: '20' },
  { label: 'Balanced (10m cells)', value: '10' },
  { label: 'Precise (5m cells)', value: '5' },
  { label: 'Very precise (2m cells) — slower', value: '2' },
]

function extractErrorMessage(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  }
  return 'Something went wrong while analyzing the file.'
}

function PondSiteCard({ site }) {
  return (
    <div className="card">
      <h3>Site #{site.rank}</h3>
      <dl>
        <dt>Location</dt>
        <dd>{site.location.lat.toFixed(5)}, {site.location.lon.toFixed(5)}</dd>

        <dt>Ground elevation</dt>
        <dd>{site.elevation_m.toFixed(2)} m</dd>

        <dt>Spill elevation</dt>
        <dd>{site.spill_elevation_m.toFixed(2)} m</dd>

        <dt>Max depth</dt>
        <dd>{site.max_depth_m.toFixed(2)} m</dd>

        <dt>Catchment area</dt>
        <dd>{site.catchment_area_hectares.toFixed(2)} ha</dd>

        <dt>Pond surface area</dt>
        <dd>{site.pond_area_m2.toFixed(0)} m²</dd>

        <dt>Estimated storage volume</dt>
        <dd>{site.estimated_volume_m3.toLocaleString(undefined, { maximumFractionDigits: 0 })} m³</dd>
      </dl>
    </div>
  )
}

function TerrainSummary({ terrain }) {
  return (
    <div className="card">
      <h3>Terrain summary</h3>
      <dl>
        <dt>Elevation range</dt>
        <dd>{terrain.min_elevation_m} m – {terrain.max_elevation_m} m</dd>

        <dt>Contour interval</dt>
        <dd>{terrain.contour_interval_m} m</dd>

        <dt>Contour lines parsed</dt>
        <dd>{terrain.contour_line_count}</dd>

        <dt>Analysis grid</dt>
        <dd>{terrain.grid_rows} × {terrain.grid_cols} cells ({terrain.cell_size_m.toFixed(2)} m/cell)</dd>

        <dt>Projection</dt>
        <dd>{terrain.projected_crs}</dd>
      </dl>
    </div>
  )
}

export default function App() {
  const [file, setFile] = useState(null)
  const [precision, setPrecision] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!file) {
      setError('Please choose a .kml or .kmz file first.')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    const url = new URL('/analyzeContour', API_BASE)
    if (precision) url.searchParams.set('cell_size_m', precision)

    try {
      const response = await fetch(url, { method: 'POST', body: formData })
      const body = await response.json()
      if (!response.ok) {
        throw new Error(extractErrorMessage(body.detail))
      }
      setResult(body)
    } catch (err) {
      setError(err.message || 'Failed to reach the analysis API.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header>
        <h1>Contour Catchment Analyzer</h1>
        <p>Upload a contour map (KML/KMZ) to find candidate pond sites and their catchment area.</p>
      </header>

      <form onSubmit={handleSubmit} className="upload-form">
        <label className="field">
          <span>Contour map (.kml or .kmz)</span>
          <input
            type="file"
            accept=".kml,.kmz"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <label className="field">
          <span>Precision</span>
          <select value={precision} onChange={(e) => setPrecision(e.target.value)}>
            {PRECISION_OPTIONS.map((opt) => (
              <option key={opt.label} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>

        <button type="submit" disabled={loading}>
          {loading ? 'Analyzing…' : 'Analyze'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {result && (
        <section className="results">
          <p className="source-file">Source file: {result.source_file}</p>
          <TerrainSummary terrain={result.terrain} />
          <h2>Pond sites ({result.pond_sites.length})</h2>
          <div className="site-grid">
            {result.pond_sites.map((site) => (
              <PondSiteCard key={site.rank} site={site} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
