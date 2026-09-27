// Ranked list of suggested pond sites, plus the terrain details of the run.

import { useEffect, useRef } from 'react'
import { formatArea, formatCoord, formatMetres, formatVolume } from './format'
import { CONTOUR, SELECTION, WATER, siteColor } from './palette'

// How full the pond gets from one season of runoff, as a fill bar inside
// its storage capacity. This is the number a planner acts on: a pond that
// never fills is oversized, one that overflows could be dug bigger.
function FillGauge({ site }) {
  const capacity = site.estimated_volume_m3
  const runoff = site.expected_runoff_m3
  const share = capacity > 0 ? Math.min(runoff / capacity, 1) : 0
  const overflow = runoff - capacity

  return (
    <div className="gauge">
      <div className="gauge-track" role="img"
        aria-label={`Runoff fills ${Math.round(share * 100)}% of the pond's capacity`}>
        <div className="gauge-fill" style={{ width: `${share * 100}%` }} />
      </div>
      <p className="gauge-caption">
        {overflow > 0
          ? `Fills its ${formatVolume(capacity)} capacity, with ${formatVolume(overflow)} of runoff to spare.`
          : `Runoff fills ${Math.round(share * 100)}% of its ${formatVolume(capacity)} capacity.`}
      </p>
    </div>
  )
}

function SiteItem({ site, active, onSelect }) {
  return (
    <li className={`site${active ? ' is-active' : ''}`} style={{ '--site': siteColor(site.rank) }}>
      <button type="button" className="site-head" onClick={() => onSelect(site.rank)}
        aria-pressed={active}>
        <span className="site-pin">{site.rank}</span>
        <span className="site-title">Pond site {site.rank}</span>
        <span className="site-coord">{formatCoord(site.location)}</span>
      </button>

      <p className="site-yield">
        <strong>{formatVolume(site.collectible_volume_m3)}</strong> of water can be collected
      </p>
      <FillGauge site={site} />

      <dl className="facts">
        <dt>Catchment area</dt>
        <dd>{formatArea(site.catchment_area_m2)}</dd>
        <dt>Expected runoff</dt>
        <dd>{formatVolume(site.expected_runoff_m3)}</dd>
        <dt>Pond surface</dt>
        <dd>{formatArea(site.pond_area_m2)}</dd>
        <dt>Pond depth</dt>
        <dd>{formatMetres(site.max_depth_m)}</dd>
        <dt>Ground level</dt>
        <dd>{formatMetres(site.elevation_m)}</dd>
      </dl>
    </li>
  )
}

function Legend() {
  return (
    <ul className="legend">
      <li><i style={{ borderColor: SELECTION }} className="key key-dashed" /> Selected land</li>
      <li><i style={{ borderColor: '#555' }} className="key key-dashed" /> Catchment: land that drains to a site</li>
      <li><i style={{ background: WATER }} className="key key-fill" /> Pond footprint at full capacity</li>
      <li><i style={{ background: CONTOUR }} className="key key-line" /> Contour line</li>
    </ul>
  )
}

export default function Results({ result, activeRank, onSelectSite }) {
  const { pond_sites: sites, terrain, runoff, elapsedSeconds } = result
  const sectionRef = useRef(null)

  // The results appear below the form, often out of view; bring them in.
  useEffect(() => {
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    sectionRef.current?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
  }, [result])

  return (
    <section className="results" aria-live="polite" ref={sectionRef}>
      <h2>Suggested pond sites</h2>
      {sites.length === 0 ? (
        <p className="note">No low ground that could hold a pond was found in this area. Try selecting a larger area.</p>
      ) : (
        <>
          <p className="note">
            Ranked by how much the pond can store. Collectible water assumes {runoff.rainfall_mm} mm of
            rain with a runoff coefficient of {runoff.runoff_coefficient}. Select a site to zoom to it.
          </p>
          <ol className="site-list">
            {sites.map((site) => (
              <SiteItem key={site.rank} site={site} active={site.rank === activeRank} onSelect={onSelectSite} />
            ))}
          </ol>
        </>
      )}

      <Legend />

      <details className="terrain">
        <summary>Terrain details</summary>
        <dl className="facts">
          <dt>Elevation range</dt>
          <dd>{formatMetres(terrain.min_elevation_m)} to {formatMetres(terrain.max_elevation_m)}</dd>
          <dt>Contour interval</dt>
          <dd>{formatMetres(terrain.contour_interval_m)}</dd>
          <dt>Contour lines used</dt>
          <dd>{terrain.contour_line_count}</dd>
          <dt>Analysis grid</dt>
          <dd>{terrain.grid_rows} × {terrain.grid_cols} cells of {formatMetres(terrain.cell_size_m)}</dd>
          <dt>Projection</dt>
          <dd>{terrain.projected_crs}</dd>
          <dt>Time taken</dt>
          <dd>{elapsedSeconds.toFixed(1)} s</dd>
        </dl>
      </details>
    </section>
  )
}
