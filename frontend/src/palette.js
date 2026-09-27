// Map colours, borrowed from topographic survey sheets: sienna contours,
// blue water, a red dashed line for the surveyed (selected) area.
export const CONTOUR = '#a0522d'
export const WATER = '#1769aa'
export const SELECTION = '#c62828'

// One colour per ranked site, used for its catchment outline, map pin and
// entry in the results list. Kept clear of the contour, water and selection
// colours so every layer stays tellable apart.
const SITE_COLORS = ['#2b8a3e', '#7048e8', '#d6336c', '#0c8599', '#e67700']

export const siteColor = (rank) => SITE_COLORS[(rank - 1) % SITE_COLORS.length]
