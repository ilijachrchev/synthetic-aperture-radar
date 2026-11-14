// Section copy. Every sentence is taken from the repository README or docs/RESEARCH.md (the team's words) and only
// shaped into headings and lines. Nothing here claims a result the models have not produced yet.
import type { SiteKey } from '@/lib/radar'

export type Story = {
	key: 'water' | 'fire' | 'sink' | 'quake'
	title: string
	what: string
	where: string
	site: SiteKey
	/** which pass to show: by date (last date of a pass or pair) and track */
	show: { date: string; track: string }
	kind: string
}

export const STORIES_HEAD = { a: 'Several kinds of surface change,', b: 'not just', accent: 'one.' }
export const STORIES_LINE = 'Each story comes with the real NISAR passes that cover it.'

export const STORIES: Story[] = [
	{
		key: 'water',
		title: 'Farm water vs storm water',
		what: 'Rice fields flooded on purpose, next to the DANA "Adam" flood of Oct 2026',
		where: 'Albufera · Pego-Oliva marsh',
		site: 'albufera',
		show: { date: '2026-10-28', track: '066' },
		kind: 'Radar brightness (GCOV)',
	},
	{
		key: 'fire',
		title: 'Fire scar',
		what: 'Forest burned in summer 2026',
		where: "Serra d'Espadà",
		site: 'espada',
		show: { date: '2026-08-17', track: '058' },
		kind: 'Radar brightness (GCOV)',
	},
	{
		key: 'sink',
		title: 'Sinking ground',
		what: 'Land dropping a few cm a year from groundwater pumping',
		where: 'Lorca',
		site: 'lorca',
		show: { date: '2026-08-24', track: '159' },
		kind: 'Ground motion pairs (GUNW)',
	},
	{
		key: 'quake',
		title: 'Earthquake (global)',
		what: 'Ground moved by the M7.7 quake of 9 Oct 2026',
		where: 'Panama',
		site: 'panama',
		show: { date: '2026-10-09', track: '141' },
		kind: 'Ground motion pairs (GUNW)',
	},
]

export const PASSES_HEAD = { a: 'Every 12-day pass,', b: 'not a single', accent: 'snapshot.' }
export const PASSES_LINE = 'The map plays every pass of one track over the Valencia coast, June to October. These are the real NISAR previews.'

// What L-band shows over rice (docs/RESEARCH.md, section 5 and the site table). Expectations, not model output.
export const BEATS = [
	{ months: [6], title: 'Flooded paddies read dark', line: 'Open water sends the radar pulse away, so it comes back very dark.' },
	{ months: [7, 8], title: 'The rice grows and turns bright', line: 'Canopy over water bounces the pulse back: the paddies brighten.' },
	{ months: [9], title: 'Harvest brings a drop', line: 'Cut fields lose their canopy and their brightness.' },
	{ months: [10, 11], title: 'Winter flooding, on purpose', line: 'The big October water here is the farmers (perellonà), not the storm.' },
]

export const HOW_HEAD = { a: 'How it', accent: 'works.' }
export const HOW_LINE = 'Plain language first, with the radar details one click deeper.'
export const STEPS = [
	{ title: 'Fetch', line: 'Harmony cuts each site and the layers we need out of the NISAR files and returns small COGs. A full file is 1 to 7 GB, so we never download whole files.' },
	{ title: 'Process', line: 'Calibrate to dB, filter speckle, detect change, classify it, forecast.' },
	{ title: 'Bake', line: 'Export small Cloud-Optimized GeoTIFFs (COGs) and JSON.' },
	{ title: 'Show', line: 'The browser reads the COGs directly. No tile server or backend is needed for the demo.' },
]
export const MODELS = [
	{ name: 'CV', line: 'finds water, flooded fields and burned ground in each scene.' },
	{ name: 'ML', line: 'labels every pixel by how it behaves through the season.' },
	{ name: 'Prediction', line: 'forecasts sinking and flooding with honest ranges.' },
]

export const DATA_HEAD = { a: 'Open data,', accent: 'all of it.' }
export const SOURCES = [
	{ name: 'NISAR L2 GCOV', what: 'Radar brightness, HH and HV, 20 m', from: 'NASA ASF DAAC', href: 'https://nisar-docs.asf.alaska.edu/' },
	{ name: 'NISAR L2 GUNW', what: '12-day ground-motion pairs, 80 m', from: 'NASA ASF DAAC', href: 'https://nisar-docs.asf.alaska.edu/' },
	{ name: 'OPERA DSWx-S1', what: 'Sentinel-1 surface water maps, training labels and an L-band vs C-band comparison', from: 'NASA JPL', href: 'https://www.jpl.nasa.gov/go/opera/products' },
	{ name: 'Copernicus EMS and EFFIS', what: 'Flood and burnt-area outlines for validation', from: 'Copernicus', href: 'https://mapping.emergency.copernicus.eu/activations/EMSR935/' },
	{ name: 'EGMS', what: 'Years of ground-motion history', from: 'European Ground Motion Service', href: 'https://egms.land.copernicus.eu/' },
	{ name: 'USGS', what: 'Earthquake catalog', from: 'U.S. Geological Survey', href: 'https://earthquake.usgs.gov/earthquakes/eventpage/us6000u18k' },
]

export const CLOSE = {
	a: 'Maps and stories',
	accent: 'anyone can follow.',
	line: 'An open-source, interactive web app that turns NISAR L-band radar data into maps and stories anyone can follow.',
}
