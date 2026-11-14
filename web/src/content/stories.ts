// The stories the water page can tell. A story is a place, a span of days, the radar series to play and what stands
// around them. Everything that is a measurement comes from the baked files under public/layers/<site>/; what is
// written here was checked against its source on 14 Nov 2026, and the sources are named beside each entry.

export type Story = {
	key: string
	/** folder under public/layers/ */
	root: string
	title: string
	place: string
	/** 'storm': water rises with the rain between two passes. 'season': water comes and goes pass by pass.
	    'fire': burned ground the radar confirms, which only grows */
	kind: 'storm' | 'season' | 'fire'
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
	/** one reference line of its own (outline.json), shown from a day on */
	outline?: { key: string; label: string; from: string }
	/** the moment the story turns on, marked on the time axis; the last pass before it is the reference.
	 *  `until` is when its record was last updated: by then everything in the record had happened */
	event?: { t: string; until?: string; label: string }
	/** words and colours when the layer is not water */
	layer?: { unit: string; main: string; toggle: string; rgb: { open: [number, number, number]; glow: [number, number, number]; edge: [number, number, number]; fill: number; line: number } }
	/** the short credit line that is always on screen, and the full list behind "Sources" */
	credit: string
	credits: { what: string; who: string }[]
	meta: { title: string; description: string }
}

const BASE = { what: 'Base map', who: 'EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2017), CC BY 4.0' }
const NISAR = { what: 'NISAR water', who: 'NASA-ISRO NISAR L2 GCOV (NASA ASF DAAC), water mapped by the team CV model' }
const PICTURES = { what: 'Pictures', who: 'Contains modified Copernicus Sentinel data 2026 (Sentinel-2 L2A, Earth Search)' }

/** passes of one track over a site, from the granule names in NASA CMR (data/catalog/<site>.json) */
const onTrack = (track: string, times: string[]) => times.map((t) => ({ t, track }))

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
	otherNisar: [
		...onTrack('058 A', [
			'2026-06-18T05:06:55Z', '2026-06-30T05:06:50Z', '2026-07-12T05:06:53Z', '2026-07-24T05:06:53Z',
			'2026-08-17T05:06:52Z', '2026-08-29T05:06:52Z', '2026-09-10T05:06:51Z', '2026-09-22T05:06:51Z',
			'2026-10-04T05:06:52Z', '2026-10-16T05:06:52Z', '2026-10-28T05:06:52Z',
		]),
		...onTrack('167 D', [
			'2026-06-25T19:01:07Z', '2026-07-07T19:01:06Z', '2026-07-19T19:01:06Z', '2026-08-24T19:01:04Z',
			'2026-09-05T19:01:04Z', '2026-09-17T19:01:03Z', '2026-09-29T19:01:03Z', '2026-10-11T19:01:03Z',
			'2026-10-23T19:01:04Z',
		]),
	],
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

export const FIRE: Story = {
	key: 'fire',
	root: '/layers/espada',
	title: 'Espadà fire',
	place: "Serra d'Espadà, Castelló",
	kind: 'fire',
	series: ['burn_058_A_022'],
	window: { from: '2026-06-14T00:00:00Z', to: '2026-11-01T00:00:00Z' },
	camera: { center: [-0.262, 39.89], zoom: 11.55 },
	// no NISAR pass on any track between 24 Jul and 17 Aug: the fire fell in the gap
	otherNisar: [
		...onTrack('066 D', [
			'2026-06-18T18:52:48Z', '2026-06-30T18:52:47Z', '2026-07-12T18:52:46Z', '2026-07-24T18:52:46Z',
			'2026-08-17T18:52:44Z', '2026-08-29T18:52:44Z', '2026-09-10T18:52:44Z', '2026-09-22T18:52:44Z',
			'2026-10-04T18:52:44Z', '2026-10-16T18:52:44Z', '2026-10-28T18:52:44Z',
		]),
		...onTrack('167 D', [
			'2026-06-25T19:01:07Z', '2026-07-07T19:01:06Z', '2026-07-19T19:01:06Z', '2026-08-24T19:01:04Z',
			'2026-09-05T19:01:04Z', '2026-09-17T19:01:03Z', '2026-09-29T19:01:03Z', '2026-10-11T19:01:03Z',
			'2026-10-23T19:01:04Z',
		]),
	],
	// EFFIS burnt area 570518: fire date 25 Jul 2026 09:09 local time (07:09 UTC), last update 26 Jul 08:55 local
	// time (06:55 UTC), 9,222 ha. The outline is shown from that last update on.
	event: { t: '2026-07-25T07:09:00Z', until: '2026-07-26T06:55:42Z', label: 'fire starts, 25 Jul (EFFIS)' },
	outline: { key: 'effis', label: 'EFFIS burnt area', from: '2026-07-26T06:55:42Z' },
	layer: {
		unit: 'burned ground',
		main: 'Burn the radar confirms',
		toggle: 'Radar burn',
		rgb: { open: [0.42, 0.07, 0.01], glow: [1.0, 0.42, 0.1], edge: [1.0, 0.66, 0.24], fill: 0.86, line: 0.5 },
	},
	places: [
		{ name: 'Onda', at: [-0.2603, 39.9634] },
		{ name: 'Nules', at: [-0.1563, 39.8532] },
		{ name: 'Eslida', at: [-0.3046, 39.8822] },
	],
	credit: 'NISAR: NASA-ISRO · Sentinel-2: Copernicus · Burnt area: EFFIS, © European Union · EOX',
	credits: [
		{ what: 'NISAR burn', who: 'NASA-ISRO NISAR L2 GCOV (NASA ASF DAAC): the cross-polarised echo at least 1.5 dB below the last pass before the fire, on two passes in a row (the team CV method)' },
		PICTURES,
		{ what: 'Burnt area', who: 'EFFIS, European Forest Fire Information System, © European Union, CC BY 4.0' },
		BASE,
	],
	meta: {
		title: "Serra d'Espadà fire · Dancing with the SARs",
		description: "The burn scar of the July 2026 fire in the Serra d'Espadà, as NISAR confirms it pass after pass, over real satellite pictures.",
	},
}

export const STORIES: Record<string, Story> = { dana: DANA, rice: RICE, fire: FIRE }
