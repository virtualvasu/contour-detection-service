import { useCallback, useRef, useState } from 'react'
import { analyzeArea, previewMap } from './api'
import { formatArea, formatMetres } from './format'
import { boundsToPolygon, geometryArea, ringsBounds } from './geo'
import MapView from './MapView'
import Results from './Results'
import './App.css'

// Precision presets mapped to the API's cell_size_m (metres per grid cell).
// Smaller cells give sharper boundaries but take longer.
const PRECISION_OPTIONS = [
  { label: 'Automatic', value: '' },
  { label: 'Coarse, 20 m grid (fastest)', value: '20' },
  { label: 'Medium, 10 m grid', value: '10' },
  { label: 'Fine, 5 m grid', value: '5' },
  { label: 'Very fine, 2 m grid (slowest)', value: '2' },
]

// Typical runoff coefficients by land cover: the share of rain that runs
// off rather than soaking in.
const LAND_COVER_OPTIONS = [
  { label: 'Forest (0.15)', value: '0.15' },
  { label: 'Grassland or pasture (0.2)', value: '0.2' },
  { label: 'Farmland (0.3)', value: '0.3' },
  { label: 'Bare or rocky ground (0.5)', value: '0.5' },
  { label: 'Built-up or paved (0.8)', value: '0.8' },
]

const DRAW_HINTS = {
  Rectangle: 'Click one corner on the map, then click the opposite corner.',
  Polygon: 'Click on the map to add corners. Click the first corner again to finish.',
}

function Step({ number, title, enabled = true, children }) {
  return (
    <li className={`step${enabled ? '' : ' is-disabled'}`}>
      <h2 className="step-title"><span className="step-number">{number}</span>{title}</h2>
      {enabled && <div className="step-body">{children}</div>}
    </li>
  )
}

export default function App() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)

  const [selection, setSelection] = useState(null)
  const [drawMode, setDrawMode] = useState(null)

  const [rainfall, setRainfall] = useState('1200')
  const [runoffCoefficient, setRunoffCoefficient] = useState('0.3')
  const [precision, setPrecision] = useState('')

  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [activeRank, setActiveRank] = useState(null)
  const [flyTarget, setFlyTarget] = useState(null)
  const [error, setError] = useState(null)

  const requestRef = useRef(null)
  const mapPaneRef = useRef(null)

  function startRequest() {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    return controller
  }

  function clearResults() {
    setResult(null)
    setActiveRank(null)
    setFlyTarget(null)
  }

  async function handleFileChange(event) {
    const chosen = event.target.files?.[0]
    if (!chosen) return
    const controller = startRequest()
    setFile(chosen)
    setPreview(null)
    setSelection(null)
    setDrawMode(null)
    setAnalyzing(false)
    clearResults()
    setError(null)
    setPreviewing(true)
    try {
      setPreview(await previewMap(chosen, controller.signal))
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      if (requestRef.current === controller) setPreviewing(false)
    }
  }

  const handleSelect = useCallback((geometry) => {
    setSelection(geometry)
    setDrawMode(null)
    setResult(null)
    setActiveRank(null)
    setError(null)
  }, [])

  const handleDrawEnd = useCallback(() => setDrawMode(null), [])

  function handleSelectSite(rank) {
    const site = result.pond_sites.find((s) => s.rank === rank)
    setActiveRank(rank)
    setFlyTarget({ bounds: ringsBounds([...site.catchment_boundary, ...site.pond_boundary]) })
    // On phones the map sits above the list, so bring it back into view.
    if (window.matchMedia('(max-width: 800px)').matches) {
      mapPaneRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  async function handleAnalyze(event) {
    event.preventDefault()
    const controller = startRequest()
    setAnalyzing(true)
    setError(null)
    clearResults()
    const started = performance.now()
    try {
      const body = await analyzeArea({
        file,
        area: selection,
        cellSize: precision,
        rainfallMm: rainfall,
        runoffCoefficient,
        signal: controller.signal,
      })
      setResult({ ...body, elapsedSeconds: (performance.now() - started) / 1000 })
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      if (requestRef.current === controller) setAnalyzing(false)
    }
  }

  function handleCancel() {
    requestRef.current?.abort()
    setAnalyzing(false)
  }

  const rainfallValid = Number(rainfall) > 0 && Number(rainfall) <= 10000
  const canAnalyze = preview && selection && rainfallValid && !analyzing

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <h1>Pond Site Finder</h1>
          <p>
            Pick a stretch of land on a contour map to see where a farm pond would catch the most
            rain, how much land drains to it, and how much water it can collect.
          </p>
        </header>

        <form onSubmit={handleAnalyze}>
          <ol className="steps">
            <Step number={1} title="Load a contour map">
              <label className="file-picker">
                <input type="file" accept=".kml,.kmz" onChange={handleFileChange} />
                <span className="button button-secondary">{file ? 'Choose another file' : 'Choose KML or KMZ file'}</span>
              </label>
              {previewing && <p className="status">Reading {file.name}…</p>}
              {preview && (
                <p className="status">
                  <strong>{preview.source_file}</strong>: {preview.contour_line_count.toLocaleString('en-IN')} contour
                  lines from {formatMetres(preview.min_elevation_m)} to {formatMetres(preview.max_elevation_m)},
                  every {formatMetres(preview.contour_interval_m)}.
                </p>
              )}
            </Step>

            <Step number={2} title="Select the land" enabled={Boolean(preview)}>
              <div className="button-row">
                <button type="button" className="button button-secondary"
                  aria-pressed={drawMode === 'Rectangle'}
                  onClick={() => setDrawMode(drawMode === 'Rectangle' ? null : 'Rectangle')}>
                  Draw rectangle
                </button>
                <button type="button" className="button button-secondary"
                  aria-pressed={drawMode === 'Polygon'}
                  onClick={() => setDrawMode(drawMode === 'Polygon' ? null : 'Polygon')}>
                  Draw shape
                </button>
                <button type="button" className="button button-secondary"
                  onClick={() => handleSelect(boundsToPolygon(preview.bounds))}>
                  Whole map
                </button>
              </div>
              {drawMode && <p className="status">{DRAW_HINTS[drawMode]} Press Esc to stop.</p>}
              {!drawMode && selection && (
                <p className="status">
                  <strong>{formatArea(geometryArea(selection))}</strong> selected.{' '}
                  <button type="button" className="link-button" onClick={() => handleSelect(null)}>
                    Clear selection
                  </button>
                </p>
              )}
              {!drawMode && !selection && <p className="status">Draw the area to analyse on the map.</p>}
            </Step>

            <Step number={3} title="Rainfall and land cover" enabled={Boolean(preview)}>
              <label className="field">
                <span>Annual rainfall, mm</span>
                <input type="number" min="1" max="10000" step="1" inputMode="numeric" required
                  value={rainfall} onChange={(e) => setRainfall(e.target.value)}
                  aria-invalid={!rainfallValid} />
                <small>Use the local average. 1200 mm is typical of central India.</small>
              </label>
              <label className="field">
                <span>Land cover</span>
                <select value={runoffCoefficient} onChange={(e) => setRunoffCoefficient(e.target.value)}>
                  {LAND_COVER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                <small>Sets how much of the rain runs off to the pond.</small>
              </label>
              <label className="field">
                <span>Detail</span>
                <select value={precision} onChange={(e) => setPrecision(e.target.value)}>
                  {PRECISION_OPTIONS.map((opt) => (
                    <option key={opt.label} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </label>
            </Step>
          </ol>

          {preview && (
            <div className="actions">
              {analyzing ? (
                <>
                  <button type="button" className="button" disabled>Analysing…</button>
                  <button type="button" className="button button-secondary" onClick={handleCancel}>Cancel</button>
                </>
              ) : (
                <button type="submit" className="button" disabled={!canAnalyze}>Find pond sites</button>
              )}
            </div>
          )}
        </form>

        {error && <p className="error" role="alert">{error}</p>}

        {result && <Results result={result} activeRank={activeRank} onSelectSite={handleSelectSite} />}
      </aside>

      <main className="map-pane" ref={mapPaneRef}>
        <MapView
          preview={preview}
          selection={selection}
          drawMode={drawMode}
          onSelect={handleSelect}
          onDrawEnd={handleDrawEnd}
          sites={result?.pond_sites ?? []}
          activeRank={activeRank}
          onSiteClick={handleSelectSite}
          flyTarget={flyTarget}
        />
        {!preview && (
          <p className="map-empty">{previewing ? 'Loading the contour map…' : 'Load a contour map to begin.'}</p>
        )}
      </main>
    </div>
  )
}
