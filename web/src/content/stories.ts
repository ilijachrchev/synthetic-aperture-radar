// The stories the map page can tell. A story is a place, a span of days, the radar series to play and what stands
// around them. Everything that is a measurement comes from the baked files under public/layers/<site>/; what is
// written here was checked against its source on 14 Nov 2026, and the sources are named beside each entry.

export type Story = {
	key: string
	/** the address of the page, and the word on the switch between stories */
	path: string
	tab: string
	/** folder under public/layers/ */
	root: string
	title: string
	place: string
	/** 'storm': water rises with the rain between two passes. 'season': water comes and goes pass by pass.
	    'fire': burned ground the radar confirms, which only grows */
	kind: 'storm' | 'season' | 'fire'
	/** radar series in order of preference: the first one the baked files hold opens the page */
	series: string[]
	/** the days the story covers */
	window: { from: string; to: string }
	/** the days of rain (hourly rain in rain.json). The last pass before it is the reference for "new" water */
	storm?: { from: string; to: string }
	/** where the camera rests: tilted, so the ground has depth */
	view: { center: [number, number]; zoom: number; pitch: number; bearing: number }
	/** what changes on a screen held upright: the place has to fit a narrow, tall view */
	phone?: Partial<{ center: [number, number]; zoom: number; pitch: number; bearing: number }>
	/** the line that says where we are while the film is still far out */
	far: { line: string }
	/** the words after the number in the readout */
	unit: string
	places: { name: string; at: [number, number] }[]
	/** the moment the story turns on, marked on the time strip; the last pass before it is the reference.
	 *  `until` is when its record was last updated: by then everything in the record had happened */
	event?: { t: string; until?: string; label: string }
	/** colours and strengths of the layer when it is not water */
	layer?: { rgb: { open: [number, number, number]; glow: [number, number, number]; edge: [number, number, number]; fill: number; line: number } }
	/** the page also shows the model's map of where the water would go (prediction.json in the root, from
	 *  scripts/bake_prediction.py): a rain slider over its scenarios */
	predict?: boolean
	/** the short credit line that is always on screen, and the full list behind "Sources" */
	credit: string
	credits: { what: string; who: string }[]
	meta: { title: string; description: string }
}

const BASE = { what: 'Base map', who: 'EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2017), CC BY 4.0' }
const NAMES = { what: 'Names from far out', who: 'Overlay bright: data © OpenStreetMap contributors, rendering © EOX and MapServer' }
const NISAR = { what: 'NISAR water', who: 'NASA-ISRO NISAR L2 GCOV (NASA ASF DAAC), water mapped by the team CV model' }
const PICTURES = { what: 'Pictures', who: 'Contains modified Copernicus Sentinel data 2026 (Sentinel-2 L2A, Earth Search)' }
const COVER = { what: 'Land cover', who: '© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium, CC BY 4.0' }

export const DANA: Story = {
	key: 'dana',
	path: '/flood',
	tab: 'Flood',
	root: '/layers/pego_oliva',
	title: 'DANA Adam',
	place: 'Pego-Oliva marsh, Valencia',
	kind: 'storm',
	series: ['nisar_066_D_069', 's1'],
	window: { from: '2026-10-15T12:00:00Z', to: '2026-11-11T06:00:00Z' },
	storm: { from: '2026-10-18T00:00:00Z', to: '2026-10-20T00:00:00Z' },
	// from over the sea, looking inland: the marsh lies in front of its mountains
	view: { center: [-0.064, 38.87], zoom: 12.8, pitch: 58, bearing: -110 },
	// upright the marsh runs up the screen: north-west at the top
	phone: { center: [-0.058, 38.872], zoom: 11.75, pitch: 44, bearing: -42 },
	far: { line: 'Valencia coast, Spain' },
	unit: 'ha under water',
	predict: true,
	places: [
		{ name: 'Pego', at: [-0.1178, 38.8431] },
		{ name: 'Oliva', at: [-0.1211, 38.9197] },
	],
	credit: 'NISAR: NASA-ISRO · Sentinel-1, Sentinel-2: Copernicus · OPERA DSWx-S1: NASA JPL · Flood map: Copernicus EMS · Depths: Generalitat Valenciana · Rain: Open-Meteo · Land cover: ESA WorldCover · EOX · OpenStreetMap',
	credits: [
		NISAR,
		{ what: 'Sentinel-1 water', who: 'OPERA Dynamic Surface Water Extent from Sentinel-1, version 1 (NASA JPL, PO.DAAC). Contains modified Copernicus Sentinel data 2026' },
		PICTURES,
		{ what: 'EU flood map', who: 'Copernicus Emergency Management Service, EMSR935, imagery of 20 to 21 Oct 2026, drawn here as one generalised shape' },
		{ what: 'Measured depths', who: 'Generalitat Valenciana, Servicio de Gestión de Riesgos en el Territorio. The columns are far taller than the water: their height only compares the points' },
		{ what: 'Rain', who: 'Weather data by Open-Meteo.com (Meteo-France AROME), modelled, not gauged' },
		{ what: 'Where the water would go', who: 'The team spatial model (LightGBM) trained on OPERA DSWx-S1 water maps, with terrain (ASF GLO-30 HAND, Copernicus DEM GLO-30), rain (Open-Meteo, ECMWF IFS 9 km, CC BY 4.0), ESA WorldCover 2021 and JRC Global Surface Water. A relative likelihood, not depth' },
		{ what: 'Soil moisture', who: 'NASA-ISRO NISAR L3 SME2, provisional (NASA ASF DAAC), 200 m' },
		COVER,
		BASE,
		NAMES,
	],
	meta: {
		title: 'DANA Adam flood · Dancing with the SARs',
		description: 'The October 2026 flood at the Pego-Oliva marsh: where the water was before and after the storm, from real radar passes over real satellite pictures.',
	},
}

export const FIRE: Story = {
	key: 'fire',
	path: '/fire',
	tab: 'Fire',
	root: '/layers/espada',
	title: 'Espadà fire',
	place: "Serra d'Espadà, Castelló",
	kind: 'fire',
	series: ['burn_058_A_022'],
	window: { from: '2026-06-14T00:00:00Z', to: '2026-11-01T00:00:00Z' },
	// the burned slopes face the camera
	view: { center: [-0.262, 39.885], zoom: 11.75, pitch: 60, bearing: -25 },
	phone: { zoom: 10.55, pitch: 48 },
	far: { line: 'Castelló, Spain' },
	unit: 'ha burned',
	// EFFIS burnt area 570518: fire date 25 Jul 2026 09:09 local time (07:09 UTC), last update 26 Jul 08:55 local
	// time (06:55 UTC), 9,222 ha. No NISAR pass on any track between 24 Jul and 17 Aug: the fire fell in the gap.
	event: { t: '2026-07-25T07:09:00Z', until: '2026-07-26T06:55:42Z', label: 'fire' },
	layer: { rgb: { open: [0.42, 0.07, 0.01], glow: [1.0, 0.42, 0.1], edge: [1.0, 0.66, 0.24], fill: 0.86, line: 0.5 } },
	places: [
		{ name: 'Onda', at: [-0.2603, 39.9634] },
		{ name: 'Nules', at: [-0.1563, 39.8532] },
		{ name: 'Eslida', at: [-0.3046, 39.8822] },
	],
	credit: 'NISAR: NASA-ISRO · Sentinel-2: Copernicus · Burnt area map: EFFIS, © European Union · Land cover: ESA WorldCover · EOX · OpenStreetMap',
	credits: [
		{ what: 'NISAR burn', who: 'NASA-ISRO NISAR L2 GCOV (NASA ASF DAAC): the cross-polarised echo at least 1.5 dB below the last pass before the fire, on two passes in a row (the team CV method)' },
		PICTURES,
		{ what: 'EU burnt area map', who: 'EFFIS, European Forest Fire Information System, © European Union, CC BY 4.0. Fire of 25 Jul 2026, record of 26 Jul' },
		COVER,
		BASE,
		NAMES,
	],
	meta: {
		title: "Serra d'Espadà fire · Dancing with the SARs",
		description: "The burn scar of the July 2026 fire in the Serra d'Espadà, as NISAR confirms it pass after pass, over real satellite pictures.",
	},
}

export const RICE: Story = {
	key: 'rice',
	path: '/rice',
	tab: 'Not a flood',
	root: '/layers/albufera',
	title: 'Rice season',
	place: 'Albufera, Valencia',
	kind: 'season',
	series: ['nisar_066_D_069'],
	window: { from: '2026-06-14T00:00:00Z', to: '2026-11-01T00:00:00Z' },
	// the lagoon behind its rice fields, the city on the horizon
	view: { center: [-0.33, 39.3], zoom: 11.25, pitch: 50, bearing: -8 },
	phone: { center: [-0.33, 39.29], zoom: 10.35, pitch: 42 },
	far: { line: 'Valencia, Spain' },
	unit: 'ha of water',
	places: [
		{ name: 'València', at: [-0.3763, 39.4699] },
		{ name: 'Sueca', at: [-0.3111, 39.2026] },
		{ name: 'El Palmar', at: [-0.3172, 39.3122] },
	],
	credit: 'NISAR: NASA-ISRO · Sentinel-2: Copernicus · EOX · OpenStreetMap',
	credits: [NISAR, PICTURES, BASE, NAMES],
	meta: {
		title: 'Rice season at the Albufera · Dancing with the SARs',
		description: 'Every autumn farmers flood the rice fields around the Albufera lagoon. NISAR maps it on every pass: farm water, not a flood.',
	},
}

/** in the order of the switch */
export const STORIES: Story[] = [DANA, FIRE, RICE]
