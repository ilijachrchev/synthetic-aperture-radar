// The flat flood explorer (/explore): a street map of the official flood zones, what really flooded, and our model.
// Every measurement comes from the baked files (scripts/bake_explore.py, scripts/bake_prediction.py); what is written
// here was checked against its source on 15 Nov 2026, and the sources are named beside each entry.

/** Spain's official aerial photographs, IGN PNOA, through its free WMTS. Capabilities checked on 15 Nov 2026: layer
 *  OI.OrthoimageCoverage, JPEG tiles pregenerated to level 19 on GoogleMapsCompatible (EPSG:3857), CORS open,
 *  access constraints "CC BY 4.0 scne.es". Sentinel-2 at small scales, PNOA ortophotos for larger ones. */
export const PNOA = {
	tiles:
		'https://www.ign.es/wmts/pnoa-ma?layer=OI.OrthoimageCoverage&style=default&tilematrixset=GoogleMapsCompatible&Service=WMTS&Request=GetTile&Version=1.0.0&Format=image%2Fjpeg&TileMatrix={z}&TileCol={x}&TileRow={y}',
	maxzoom: 19,
	credit: 'Orthophoto PNOA © Instituto Geográfico Nacional de España (scne.es, CC BY 4.0)',
	short: 'PNOA © IGN',
}

/** The fallback when PNOA does not answer: the Valencian orthophoto of 2024, 25 cm, of the Institut Cartogràfic
 *  Valencià, through its WMTS (0202_2024CVAL0025_3857, layer 01_8bits_01_RGB_05_PNG, GMEPSG3857, to level 19;
 *  checked on 15 Nov 2026, CORS open). It covers the Comunitat Valenciana only, which holds every place of this page. */
export const ICV = {
	tiles: 'https://terramapas.icv.gva.es/0202_2024CVAL0025_3857/wmts/1.0.0/01_8bits_01_RGB_05_PNG/default/GMEPSG3857/{z}/{y}/{x}.png',
	maxzoom: 19,
	credit: 'Ortofoto 2024 de la Comunitat Valenciana © Institut Cartogràfic Valencià, Generalitat (CC BY 4.0)',
	short: 'Orthophoto © ICV',
}

export type Place = { key: string; name: string; when: string; view: { center: [number, number]; zoom: number } }

/** where the page opens, and the places a button flies to */
export const START = { center: [-0.24, 39.16] as [number, number], zoom: 9.2 }
export const PLACES: Place[] = [
	{ key: 'horta', name: "L'Horta Sud", when: 'DANA of 29 Oct 2024', view: { center: [-0.405, 39.425], zoom: 13.2 } },
	{ key: 'pego', name: 'Pego-Oliva', when: 'DANA Adam, Oct 2026', view: { center: [-0.075, 38.875], zoom: 12.6 } },
	{ key: 'albufera', name: 'Albufera', when: 'rice fields and lagoon', view: { center: [-0.33, 39.31], zoom: 11.4 } },
]

/** the zone classes of the official flood maps (SNCZI), in the order of the legend; the colours are the team lead's
 *  choice: red for the frequent zone, orange for the occasional one, yellow for the rare one */
export const ZONES = [
	{ key: 'frequent', label: 'T10', name: 'frequent', detail: 'high probability, 1 in 10 each year', color: '#ff3b30' },
	{ key: 'occasional', label: 'T100', name: 'occasional', detail: 'medium probability, 1 in 100 each year', color: '#ff9500' },
	{ key: 'rare', label: 'T500', name: 'rare', detail: 'low probability, 1 in 500 each year', color: '#ffd60a' },
] as const

export type LayerKey = 'zones' | 'floods2024' | 'buildings2024' | 'marks2024' | 'floods2026' | 'nisar' | 'still' | 'model' | 'sim2024'

/** the classes of the surveyed water marks of 2024 and of the simulated depth (data/streets, PR #39), light to deep */
export const MARK_CLASSES = [
	{ key: 'below 0.2 m', color: '#c6f1ff' },
	{ key: '0.2 to 1 m', color: '#62c4ff' },
	{ key: '1 to 2 m', color: '#2463eb' },
	{ key: 'above 2 m', color: '#7a1fd6' },
] as const
export const SIM_CLASSES = [
	{ key: '0.3 to 1 m', color: '#62c4ff' },
	{ key: '1 to 2 m', color: '#2463eb' },
	{ key: 'above 2 m', color: '#7a1fd6' },
] as const

/** the legend: groups of layers, each with its swatch; `badge` is a word the row carries (SIMULATED) */
export const LEGEND: { title: string; layers: { key: LayerKey; label: string; detail?: string; swatch: string; badge?: string }[] }[] = [
	{ title: 'Official flood zones', layers: [{ key: 'zones', label: 'SNCZI zones', detail: 'T10, T100, T500', swatch: 'zones' }] },
	{
		title: 'What really flooded',
		layers: [
			{ key: 'floods2024', label: '2024, Copernicus EMS', detail: "EMSR773, L'Horta Sud", swatch: 'flood2024' },
			{ key: 'buildings2024', label: '2024, damaged buildings', detail: 'graded by EMSR773', swatch: 'buildings' },
			{ key: 'marks2024', label: '2024, measured water depth', detail: 'marks surveyed after the flood (ICV)', swatch: 'marks' },
			{ key: 'floods2026', label: '2026, Copernicus EMS', detail: 'EMSR935, Pego and Oliva', swatch: 'flood2026' },
			{ key: 'nisar', label: '2026, NISAR water', detail: 'new on 28 Oct, and on both dates', swatch: 'nisar' },
			{ key: 'still', label: '2026, still flooded', detail: 'NISAR, 28 Oct, inside EMSR935', swatch: 'still' },
		],
	},
	{ title: 'Our model', layers: [{ key: 'model', label: 'Where the water would go', detail: 'relative likelihood, with a rain slider', swatch: 'model' }] },
	{
		title: 'Simulated',
		layers: [{ key: 'sim2024', label: '2024, simulated from the measured rain', detail: 'a first physics run, no infiltration, so an upper bound', swatch: 'sim', badge: 'SIMULATED' }],
	},
]

/** what is on when the page opens */
export const DEFAULT_LAYERS: Record<LayerKey, boolean> = {
	zones: true,
	floods2024: true,
	buildings2024: true,
	marks2024: false,
	floods2026: true,
	nisar: false,
	still: false,
	model: false,
	sim2024: false,
}

/** where the model has something to show: the Pego-Oliva marsh and the Albufera's rice fields and lagoon. Elsewhere
 *  (L'Horta Sud's towns, for one) "What if it rains" flies to Pego-Oliva first. West, south, east, north */
export const MODEL_AREAS: [number, number, number, number][] = [
	[-0.25, 38.78, 0.06, 39.02],
	[-0.42, 39.18, -0.25, 39.37],
]

/** the zoom from which the 20 m radar and model pictures fade out: at street level only the sharp outlines stay */
export const STREET_FADE: [number, number] = [14.8, 16.2]

export const CREDITS = [
	{ what: 'Flood zones', who: 'SNCZI, Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO), zones T10, T100 and T500, clipped to 12 municipalities (data/zones)' },
	{ what: 'Floods of 2024', who: 'Copernicus Emergency Management Service, EMSR773 (29 Oct 2024), observed flood and grading of buildings, © European Union' },
	{ what: 'Water marks', who: 'Institut Cartogràfic Valencià, Generalitat Valenciana, DANA 2024 service, CC BY 4.0' },
	{ what: 'Floods of 2026', who: 'Copernicus Emergency Management Service, EMSR935, imagery of 20 to 21 Oct 2026, © European Union' },
	{ what: 'NISAR water', who: 'NASA-ISRO NISAR L2 GCOV (NASA ASF DAAC), open water by the team CV model (v1 U-Net ensemble at 0.3), track 066 D, 16 and 28 Oct 2026' },
	{ what: 'Our model', who: 'The team spatial model (LightGBM) trained on OPERA DSWx-S1 water maps with terrain, rain (Open-Meteo, ECMWF IFS 9 km) and land cover. A relative likelihood, not depth' },
	{ what: 'Soil moisture', who: 'NASA-ISRO NISAR L3 SME2, provisional, 200 m' },
	{ what: 'Land cover', who: '© ESA WorldCover project 2021, CC BY 4.0' },
]

export const META = {
	title: 'Flood explorer · Through the Clouds',
	description: 'A street map of the official flood zones of Valencia, what really flooded in 2024 and 2026, NISAR radar water and our model of where the water would go.',
}
