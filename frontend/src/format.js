const whole = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const oneDecimal = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 })
const twoDecimals = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const formatVolume = (m3) => `${whole.format(m3)} m³`

// Hectares for anything a hectare or bigger, m² below that.
export function formatArea(m2) {
  return m2 >= 10_000 ? `${twoDecimals.format(m2 / 10_000)} ha` : `${whole.format(m2)} m²`
}

export const formatMetres = (m) => `${oneDecimal.format(m)} m`

export function formatCoord(p) {
  const lat = `${Math.abs(p.lat).toFixed(5)}° ${p.lat >= 0 ? 'N' : 'S'}`
  const lon = `${Math.abs(p.lon).toFixed(5)}° ${p.lon >= 0 ? 'E' : 'W'}`
  return `${lat}, ${lon}`
}
