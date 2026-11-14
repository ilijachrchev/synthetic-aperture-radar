// Landing copy. Facts come from the repository README and the real pass list (src/data/passes.json); nothing here
// claims a result the models have not produced yet.
import type { SiteKey } from '@/lib/radar'

export const HERO = {
	eyebrow: 'NASA-ISRO NISAR · L-band radar · Valencia, Spain',
	lines: ['Flood, grow,', 'burn and sink.'],
	mark: 'sink.',
	lead: 'One web app that shows how the land around Valencia changes, seen by NISAR radar, and what is likely to come next.',
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
	/** the animated change layer: what it shows, read from the radar previews */
	change: { kind: 'water' | 'fire' | 'sink' | 'quake'; legend: string; event?: string; epicentre?: [number, number] }
}

export const STORIES_HEAD = { title: 'Four stories', line: 'Real NISAR passes over each place. Hover a card to see the pass before.' }

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
		change: { kind: 'water', legend: 'Aqua: ground that reads dark (wet) on each pass. Deep blue: water on almost every pass.' },
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
		change: { kind: 'fire', legend: 'Ember: canopy brightness lost against the passes before the fire began on 25 Jul.', event: '2026-07-25' },
	},
	{
		key: 'sink',
		tab: 'Sinking ground',
		title: 'Sinking ground',
		what: 'Land dropping a few cm a year from groundwater pumping.',
		where: 'Lorca',
		kind: 'Ground motion pairs',
		site: 'lorca',
		compare: [
			{ site: 'lorca', date: '2026-08-12', track: '159' },
			{ site: 'lorca', date: '2026-08-24', track: '159' },
		],
		note: 'Colours show motion toward or away from the satellite between two passes.',
		change: { kind: 'sink', legend: 'Blue and red: motion toward or away from the satellite in each 12-day pair. White lines trace its shape.' },
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
		change: { kind: 'quake', legend: 'Fringes from each pair, set flowing. The pair that spans the quake reveals from the USGS epicentre; the others stay dim.', event: '2026-10-09', epicentre: [-80.7566, 7.6069] },
	},
]

export const MAP_HEAD = {
	lines: ['Every pass,', 'one map.'],
	mark: 'map.',
	line: 'Pick a story, play the season, compare any two passes. Every picture links to its record in NASA’s catalogue.',
	commands: ['Play the season', 'Compare two passes', 'See every place'],
}
