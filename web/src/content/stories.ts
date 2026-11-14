// The stories the water page can tell. A story is a place, a span of days, the radar series to play and what stands
// around them. Everything that is a measurement comes from the baked files under public/layers/<site>/; what is
// written here was checked against its source on 14 Nov 2026, and the sources are named beside each entry.

export type Story = {
	key: string
	/** folder under public/layers/ */
	root: string
	title: string
	place: string
	/** 'storm': water rises with the rain between two passes. 'season': water comes and goes pass by pass */
	kind: 'storm' | 'season'
	/** radar series in order of preference: the first one the baked files hold opens the page */
	series: string[]
	/** the days the time axis shows */
	window: { from: string; to: string }
	/** the days of rain (hourly rain in rain.json). The last pass before it is the reference for "new" water */
	storm?: { from: string; to: string }
	camera: { center: [number, number]; zoom: number }
	/** the view from far out, with the daily picture of one day from NASA GIBS */
	space?: { center: [number, number]; zoom: number; day: string; tiles: string; label: string; ring: string }
	/** NISAR passes on tracks the animation does not run on (NASA CMR granule times) */
	otherNisar: { t: string; track: string; note?: string }[]
	/** outlines.json holds the Copernicus EMS outline, drawn from imagery of these days */
	ems?: { from: string; to: string }
	places: { name: string; at: [number, number] }[]
	/** the short credit line that is always on screen, and the full list behind "Sources" */
	credit: string
	credits: { what: string; who: string }[]
	meta: { title: string; description: string }
}

const BASE = { what: 'Base map', who: 'EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2017), CC BY 4.0' }
const NISAR = { what: 'NISAR water', who: 'NASA-ISRO NISAR L2 GCOV (NASA ASF DAAC), water mapped by the team CV model' }
const PICTURES = { what: 'Pictures', who: 'Contains modified Copernicus Sentinel data 2026 (Sentinel-2 L2A, Earth Search)' }

export const DANA: Story = {
	key: 'dana',
	root: '/layers/pego_oliva',
	title: 'DANA Adam',
	place: 'Pego-Oliva marsh, Valencia',
	kind: 'storm',
	series: ['nisar_066_D_069', 's1'],
	window: { from: '2026-10-15T12:00:00Z', to: '2026-11-11T06:00:00Z' },
	storm: { from: '2026-10-18T00:00:00Z', to: '2026-10-20T00:00:00Z' },
	camera: { center: [-0.066, 38.87], zoom: 12.45 },
	space: {
		center: [-0.6, 39.3],
		zoom: 6.4,
		day: '2026-10-18',
		tiles: 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/2026-10-18/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg',
		label: 'The storm day from space: VIIRS on NOAA-20, 18 Oct 2026',
		ring: 'Pego-Oliva marsh',
	},
	otherNisar: [
		{ t: '2026-10-16T05:06:52Z', track: '058 A' },
		{ t: '2026-10-23T19:01:37Z', track: '167 D', note: 'covers 63 % of the site' },
		{ t: '2026-10-28T05:06:52Z', track: '058 A' },
	],
	// EMSR935 product metadata: imagery of 20 to 21 Oct
	ems: { from: '2026-10-20T00:00:00Z', to: '2026-10-21T23:59:59Z' },
	places: [
		{ name: 'Pego', at: [-0.1178, 38.8431] },
		{ name: 'Oliva', at: [-0.1211, 38.9197] },
		{ name: 'Gandia', at: [-0.1806, 38.968] },
		{ name: 'El Verger', at: [0.0098, 38.8436] },
	],
	credit: 'NISAR: NASA-ISRO · Sentinel-1, Sentinel-2: Copernicus · OPERA DSWx-S1: NASA JPL · EMSR935: Copernicus EMS · Generalitat Valenciana · Open-Meteo · NASA GIBS · EOX · OpenStreetMap',
	credits: [
		NISAR,
		{ what: 'Sentinel-1 water', who: 'OPERA Dynamic Surface Water Extent from Sentinel-1, version 1 (NASA JPL, PO.DAAC). Contains modified Copernicus Sentinel data 2026' },
		PICTURES,
		{ what: 'Storm view', who: 'Imagery provided by services from NASA Global Imagery Browse Services (GIBS), part of NASA ESDIS: VIIRS on NOAA-20' },
		{ what: 'Flood outline', who: 'Copernicus Emergency Management Service, EMSR935' },
		{ what: 'Footprint and depths', who: 'Generalitat Valenciana' },
		{ what: 'Rain', who: 'Weather data by Open-Meteo.com (Meteo-France AROME), modelled' },
		BASE,
		{ what: 'Names from far out', who: 'Overlay bright: data © OpenStreetMap contributors, rendering © EOX and MapServer' },
	],
	meta: {
		title: 'DANA Adam flood · Dancing with the SARs',
		description: 'The October 2026 flood at the Pego-Oliva marsh, played pass by pass from real radar water maps over real satellite pictures.',
	},
}

export const RICE: Story = {
	key: 'rice',
	root: '/layers/albufera',
	title: 'Rice season',
	place: 'Albufera, Valencia',
	kind: 'season',
	series: ['nisar_066_D_069'],
	window: { from: '2026-06-14T00:00:00Z', to: '2026-11-01T00:00:00Z' },
	camera: { center: [-0.318, 39.288], zoom: 11.3 },
	otherNisar: [],
	places: [
		{ name: 'València', at: [-0.3763, 39.4699] },
		{ name: 'Sueca', at: [-0.3111, 39.2026] },
		{ name: 'El Palmar', at: [-0.3172, 39.3122] },
	],
	credit: 'NISAR: NASA-ISRO · Sentinel-2: Copernicus · EOX',
	credits: [NISAR, PICTURES, BASE],
	meta: {
		title: 'Rice season at the Albufera · Dancing with the SARs',
		description: 'Rice paddies around the Albufera lagoon fill and drain through the 2026 season, mapped by NISAR on every pass.',
	},
}

export const STORIES: Record<string, Story> = { dana: DANA, rice: RICE }
