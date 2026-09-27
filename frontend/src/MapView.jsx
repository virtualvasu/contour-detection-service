// The interactive map: base layers, the uploaded contour lines, the area the
// user selects, and the analysis results (catchments, pond footprints and
// site pins) drawn on top.

import { useEffect, useMemo } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  GeoJSON,
  LayerGroup,
  LayersControl,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import { formatArea, formatVolume } from './format'
import { toLatLngs, toLeafletBounds } from './geo'
import { CONTOUR, EXCLUDED, SELECTION, WATER, siteColor } from './palette'

// Before a map is loaded, show central India, where the tool is aimed.
const START_CENTER = [22.5, 79]
const START_ZOOM = 5

const SELECTION_STYLE = { color: SELECTION, weight: 2, dashArray: '8 6', fillColor: SELECTION, fillOpacity: 0.05 }
const EXCLUDED_STYLE = { color: EXCLUDED, weight: 1, fillColor: EXCLUDED, fillOpacity: 0.45 }

// Every fifth contour is an "index contour", drawn heavier, as on printed maps.
const INDEX_EVERY = 5

// Draw a site's disconnected patches as one multi-polygon; a plain list of
// rings would make Leaflet treat every ring after the first as a hole.
const toMultiPolygon = (rings) => rings.map((ring) => [toLatLngs(ring)])

function FitToBounds({ bounds }) {
  const map = useMap()
  useEffect(() => {
    if (bounds) map.fitBounds(toLeafletBounds(bounds), { padding: [24, 24] })
  }, [map, bounds])
  return null
}

function FlyTo({ target }) {
  const map = useMap()
  useEffect(() => {
    if (target) map.flyToBounds(target.bounds, { padding: [48, 48], duration: 0.6 })
  }, [map, target])
  return null
}

// Lets the user draw the selection straight on the map. 'Rectangle' takes
// two clicks on opposite corners; 'Polygon' takes a click per corner and
// finishes when the first corner is clicked again. Esc stops drawing. The
// finished shape goes to onSelect as GeoJSON; the selection itself is
// rendered from state, so the in-progress outline is removed afterwards.
const CLOSE_DISTANCE_PX = 12

function DrawController({ drawMode, onSelect, onDrawEnd }) {
  const map = useMap()

  useEffect(() => {
    if (!drawMode) return undefined

    const corners = []
    const outline = L.polygon([], { ...SELECTION_STYLE, interactive: false }).addTo(map)
    const start = L.circleMarker([0, 0], {
      radius: 6, color: SELECTION, weight: 2, fillColor: '#fff', fillOpacity: 1, interactive: false,
    })

    const finish = (latlngs) => onSelect(L.polygon(latlngs).toGeoJSON().geometry)

    const rectangleCorners = (a, b) => [a, [a.lat, b.lng], b, [b.lat, a.lng]]

    const handleClick = (e) => {
      if (drawMode === 'Rectangle') {
        if (corners.length === 0) {
          corners.push(e.latlng)
        } else if (map.latLngToContainerPoint(corners[0]).distanceTo(e.containerPoint) >= CLOSE_DISTANCE_PX) {
          finish(rectangleCorners(corners[0], e.latlng))
        }
        return
      }
      if (corners.length === 0) start.setLatLng(e.latlng).addTo(map)
      const closesShape = corners.length >= 3
        && map.latLngToContainerPoint(corners[0]).distanceTo(e.containerPoint) < CLOSE_DISTANCE_PX
      if (closesShape) {
        finish(corners)
      } else {
        corners.push(e.latlng)
        outline.setLatLngs(corners)
      }
    }

    const handleMove = (e) => {
      if (corners.length === 0) return
      outline.setLatLngs(drawMode === 'Rectangle'
        ? rectangleCorners(corners[0], e.latlng)
        : [...corners, e.latlng])
    }

    const handleKey = (e) => {
      if (e.key === 'Escape') onDrawEnd()
    }

    const container = map.getContainer()
    container.classList.add('is-drawing')
    map.doubleClickZoom.disable()
    map.on('click', handleClick)
    map.on('mousemove', handleMove)
    document.addEventListener('keydown', handleKey)

    return () => {
      container.classList.remove('is-drawing')
      map.doubleClickZoom.enable()
      map.off('click', handleClick)
      map.off('mousemove', handleMove)
      document.removeEventListener('keydown', handleKey)
      outline.remove()
      start.remove()
    }
  }, [map, drawMode, onSelect, onDrawEnd])

  return null
}

function ContourLines({ contours, interval, dimmed }) {
  const { index, regular } = useMemo(() => {
    const step = interval * INDEX_EVERY
    const lines = { index: [], regular: [] }
    for (const c of contours) {
      const ratio = c.elevation_m / step
      const isIndex = Math.abs(ratio - Math.round(ratio)) < 1e-6
      lines[isIndex ? 'index' : 'regular'].push(toLatLngs(c.points))
    }
    return lines
  }, [contours, interval])

  // Fade the contours once results are on the map so the sites stand out.
  const fade = dimmed ? 0.45 : 1
  return (
    <>
      <Polyline positions={regular} interactive={false}
        pathOptions={{ color: CONTOUR, weight: 0.8, opacity: 0.75 * fade }} />
      <Polyline positions={index} interactive={false}
        pathOptions={{ color: CONTOUR, weight: 1.8, opacity: 0.9 * fade }} />
    </>
  )
}

function sitePin(rank, active) {
  return L.divIcon({
    className: '',
    html: `<span class="map-pin${active ? ' is-active' : ''}" style="--site:${siteColor(rank)}">${rank}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -14],
  })
}

function SiteLayers({ sites, activeRank, onSiteClick }) {
  return sites.map((site) => {
    const color = siteColor(site.rank)
    const active = site.rank === activeRank
    const select = { click: () => onSiteClick(site.rank) }
    return (
      <LayerGroup key={site.rank}>
        <Polygon positions={toMultiPolygon(site.catchment_boundary)} eventHandlers={select}
          pathOptions={{
            color, weight: active ? 3.5 : 2, dashArray: '6 4',
            fillColor: color, fillOpacity: active ? 0.18 : 0.1,
          }}>
          <Tooltip sticky>Land draining to site {site.rank}: {formatArea(site.catchment_area_m2)}</Tooltip>
        </Polygon>
        <Polygon positions={toMultiPolygon(site.pond_boundary)} eventHandlers={select}
          pathOptions={{ color: WATER, weight: 1.5, fillColor: WATER, fillOpacity: 0.6 }}>
          <Tooltip sticky>Pond at site {site.rank}: {formatArea(site.pond_area_m2)} of water surface</Tooltip>
        </Polygon>
        <Marker position={[site.location.lat, site.location.lon]} icon={sitePin(site.rank, active)}
          eventHandlers={select}>
          <Popup>
            <strong>Pond site {site.rank}</strong>
            <br />
            Collects {formatVolume(site.collectible_volume_m3)}
            <br />
            Catchment {formatArea(site.catchment_area_m2)}
          </Popup>
        </Marker>
      </LayerGroup>
    )
  })
}

export default function MapView({
  preview, selection, excludedWater, drawMode, onSelect, onDrawEnd, sites, activeRank, onSiteClick, flyTarget,
}) {
  return (
    <MapContainer center={START_CENTER} zoom={START_ZOOM} preferCanvas className="map">
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="Street map">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satellite">
          <TileLayer
            attribution="Imagery &copy; Esri, Maxar, Earthstar Geographics"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            maxZoom={19}
          />
        </LayersControl.BaseLayer>

        {preview && (
          <LayersControl.Overlay checked name="Contour lines">
            <LayerGroup>
              <ContourLines contours={preview.contours} interval={preview.contour_interval_m}
                dimmed={sites.length > 0} />
            </LayerGroup>
          </LayersControl.Overlay>
        )}
        {sites.length > 0 && (
          <LayersControl.Overlay checked name="Pond sites">
            <LayerGroup>
              <SiteLayers sites={sites} activeRank={activeRank} onSiteClick={onSiteClick} />
            </LayerGroup>
          </LayersControl.Overlay>
        )}
      </LayersControl>

      {excludedWater && (
        <GeoJSON key={JSON.stringify(excludedWater)} data={excludedWater} style={EXCLUDED_STYLE}>
          <Tooltip sticky>River, lake or pond: left out of the analysis</Tooltip>
        </GeoJSON>
      )}
      {selection && (
        <GeoJSON key={JSON.stringify(selection)} data={selection} style={SELECTION_STYLE} interactive={false} />
      )}

      <FitToBounds bounds={preview?.bounds} />
      <FlyTo target={flyTarget} />
      <DrawController drawMode={drawMode} onSelect={onSelect} onDrawEnd={onDrawEnd} />
    </MapContainer>
  )
}
