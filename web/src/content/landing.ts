// Landing copy. Facts come from the repository README, docs/MODELS.md and the real pass list (src/data/passes.json);
// headings are those facts set in the 8x grammar: short statements, each ending in a full stop.
import type { SiteKey } from '@/lib/radar'

export const HERO = {
	lines: ['Flood. Grow.', 'Burn. Sink.'],
	accent: ['Sink.'],
	lead: 'One web app that shows how the land around Valencia changes, seen by NISAR radar, and what is likely to come next.',
	source: { label: 'NASA-ISRO NISAR, via NASA ASF DAAC', href: 'https://nisar-docs.asf.alaska.edu/' },
}

export const PASSES = {
	line1: 'One radar.',
	/** the second line for each beat of the pinned mosaic; the last one is filled with the real count */
	beats: ['One pass.', 'Every 12 days.'],
	para: "NISAR's L-band radar sees through cloud, day or night. It passes over the Albufera every 12 days on each of three tracks.",
}

export type StoryKey = 'water' | 'fire' | 'sink' | 'quake'
export type Story = {
	key: StoryKey
	tab: string
	title: string
	what: string
	where: string
	kind: string
	site: SiteKey
	/** two passes to compare (before, after) by last date and track; one pass when there is nothing to compare */
	compare: { site: SiteKey; date: string; track: string }[]
	note: string
}

export const STORIES_HEAD = { lines: ['Four stories.', 'One map.'], line: 'Several kinds of surface change, not just one. Each comes with the real NISAR passes that cover it.' }

export const STORIES: Story[] = [
	{
		key: 'water',
		tab: 'Farm water',
		title: 'Farm water vs storm water',
		what: 'Rice fields flooded on purpose, next to the DANA "Adam" flood of Oct 2026.',
		where: 'Albufera · Pego-Oliva marsh',
		kind: 'Radar brightness',
		site: 'albufera',
		compare: [
			{ site: 'coast', date: '2026-07-12', track: '066' },
			{ site: 'coast', date: '2026-10-28', track: '066' },
		],
		note: 'Flooded paddies read dark: open water sends the pulse away.',
	},
	{
		key: 'fire',
		tab: 'Fire scar',
		title: 'Fire scar',
		what: 'Forest burned in summer 2026.',
		where: "Serra d'Espadà",
		kind: 'Radar brightness',
		site: 'espada',
		compare: [
			{ site: 'espada', date: '2026-07-24', track: '058' },
			{ site: 'espada', date: '2026-08-17', track: '058' },
		],
		note: 'Burned forest loses its canopy, and its brightness drops.',
	},
	{
		key: 'sink',
		tab: 'Sinking ground',
		title: 'Sinking ground',
		what: 'Land dropping a few cm a year from groundwater pumping.',
		where: 'Lorca',
		kind: 'Ground motion pairs',
		site: 'lorca',
		compare: [{ site: 'lorca', date: '2026-08-24', track: '159' }],
		note: 'Colours show motion toward or away from the satellite between two passes.',
	},
	{
		key: 'quake',
		tab: 'Earthquake',
		title: 'Earthquake (global)',
		what: 'Ground moved by the M7.7 quake of 9 Oct 2026.',
		where: 'Panama',
		kind: 'Ground motion pairs',
		site: 'panama',
		compare: [
			{ site: 'panama', date: '2026-09-27', track: '141' },
			{ site: 'panama', date: '2026-10-09', track: '141' },
		],
		note: 'The pair that spans the quake fills with fringes; the pair before it does not.',
	},
]

export const MACHINE = {
	lines: ['You never touch', 'a 7 GB file.'],
	sr: 'How it works: you never touch a 7 GB file.',
	steps: [
		{ n: '01', title: 'Fetch', fig: '7 GB', line: 'A full NISAR file is 1 to 7 GB. Harmony cuts out only our sites and layers.' },
		{ n: '02', title: 'Process', fig: 'dB', line: 'Calibrate to dB, filter speckle, detect change, classify it, forecast.' },
		{ n: '03', title: 'Bake', fig: 'COG', line: 'Export small Cloud-Optimized GeoTIFFs and JSON.' },
		{ n: '04', title: 'Show', fig: '0', line: 'Tile servers. The browser reads the COGs directly.' },
	],
	after: 'Plain language first, with the radar details one click deeper.',
}

export const MODELS = {
	lines: ['Three models.', 'Three questions.'],
	accent: ['questions.'],
	line: 'Each model answers a different question with NISAR data.',
	cards: [
		{ tag: 'CV · surface masks', short: 'Where is the water?', q: 'Where is the water, flooded vegetation or burned ground in this scene?', delivers: 'Mask maps per date + accuracy scores', chips: ['Water', 'Flooded vegetation', 'Burned'] },
		{ tag: 'ML · change classes', short: 'What kind of land?', q: 'What kind of land is this pixel, and how does it change through the season?', delivers: 'Class map + confusion matrix', chips: ['Rice paddy', 'Permanent water', 'Urban', 'Forest', 'Burned'] },
		{ tag: 'Prediction · forecasts', short: 'What happens next?', q: 'What happens next, and how sure are we?', delivers: 'Forecasts with ranges + backtest scores', chips: ['Median', '80% range', '95% range'] },
	],
}

export const DATA = {
	lines: ['Open data.', 'All of it.'],
	line: "NASA's free and open data first, with partner data to check it.",
	sources: [
		{ name: 'NISAR GCOV', from: 'NASA ASF DAAC', href: 'https://nisar-docs.asf.alaska.edu/' },
		{ name: 'NISAR GUNW', from: 'NASA ASF DAAC', href: 'https://nisar-docs.asf.alaska.edu/' },
		{ name: 'OPERA DSWx-S1', from: 'NASA JPL', href: 'https://www.jpl.nasa.gov/go/opera/products' },
		{ name: 'Copernicus EMS', from: 'EMSR935', href: 'https://mapping.emergency.copernicus.eu/activations/EMSR935/' },
		{ name: 'EGMS', from: 'Ground motion', href: 'https://egms.land.copernicus.eu/' },
		{ name: 'USGS', from: 'Earthquakes', href: 'https://earthquake.usgs.gov/earthquakes/eventpage/us6000u18k' },
	],
}

export const CTA = {
	lines: ['The surface never', 'stops dancing.'],
	accent: ['dancing.'],
	line: 'Earth is in a constant waltz. Pick a story and watch it change, pass by pass.',
}
