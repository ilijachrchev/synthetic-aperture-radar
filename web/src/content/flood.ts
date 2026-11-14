// The DANA Adam flood at the Pego-Oliva marsh: what the page needs that is not in the baked files.
// Every time and figure here was checked against its source on 14 Nov 2026; the sources are named beside each one.

export const FLOOD = {
	site: 'pego_oliva',
	root: '/layers/pego_oliva',
	title: 'DANA Adam',
	place: 'Pego-Oliva marsh, Valencia',
	/** radar series in order of preference: the first one the baked files hold opens the page */
	series: ['nisar_066_D_069', 's1'],
	/** the days the time axis shows */
	window: { from: '2026-10-15T12:00:00Z', to: '2026-11-11T06:00:00Z' },
	/** the two days of rain (hourly rain in rain.json). The last pass before it is the reference: water that is not
	    in that pass is drawn as new */
	storm: { from: '2026-10-18T00:00:00Z', to: '2026-10-20T00:00:00Z' },
	camera: { center: [-0.066, 38.87] as [number, number], zoom: 12.45 },
	region: { center: [-0.6, 39.3] as [number, number], zoom: 6.4 },
	/** NISAR GCOV passes over the marsh on tracks the animation does not run on (NASA CMR granule times) */
	otherNisar: [
		{ t: '2026-10-16T05:06:52Z', track: '058 A' },
		{ t: '2026-10-23T19:01:37Z', track: '167 D', note: 'covers 63 % of the site' },
		{ t: '2026-10-28T05:06:52Z', track: '058 A' },
	],
	/** the Copernicus EMS outline is drawn from imagery of these days (EMSR935 product metadata) */
	ems: { from: '2026-10-20T00:00:00Z', to: '2026-10-21T23:59:59Z' },
	/** NASA GIBS daily true colour of the storm day, for the view from far out (VIIRS on NOAA-20) */
	space: {
		day: '2026-10-18',
		tiles: 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/2026-10-18/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg',
	},
	places: [
		{ name: 'Pego', at: [-0.1178, 38.8431] as [number, number] },
		{ name: 'Oliva', at: [-0.1211, 38.9197] as [number, number] },
		{ name: 'Gandia', at: [-0.1806, 38.968] as [number, number] },
		{ name: 'El Verger', at: [0.0098, 38.8436] as [number, number] },
	],
}

export const CREDITS = [
	{ what: 'NISAR water', who: 'NASA-ISRO NISAR L2 GCOV (NASA ASF DAAC), water mapped by the team CV model' },
	{ what: 'Sentinel-1 water', who: 'OPERA Dynamic Surface Water Extent from Sentinel-1, version 1 (NASA JPL, PO.DAAC). Contains modified Copernicus Sentinel data 2026' },
	{ what: 'Pictures', who: 'Contains modified Copernicus Sentinel data 2026 (Sentinel-2 L2A, Earth Search)' },
	{ what: 'Storm view', who: 'Imagery provided by services from NASA Global Imagery Browse Services (GIBS), part of NASA ESDIS: VIIRS on NOAA-20' },
	{ what: 'Flood outline', who: 'Copernicus Emergency Management Service, EMSR935' },
	{ what: 'Footprint and depths', who: 'Generalitat Valenciana' },
	{ what: 'Rain', who: 'Weather data by Open-Meteo.com (Meteo-France AROME), modelled' },
	{ what: 'Base map', who: 'EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2017), CC BY 4.0' },
]
