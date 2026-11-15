// The guided flood map (/explore): four steps after the landing, one main action each, and two model screens kept
// out of the flow (reachable from "All layers"). The words are here; every number comes from a baked or hand-kept file
// (public/layers/guided/*.json, public/layers/explore/explore.json), read at run time with the field it comes from.

export type StepKey = 'missed' | 'simulation' | 'nisar' | 'coming' | 'exam' | 'rain'

export type Step = {
	key: StepKey
	/** date and place, the small line over the title */
	when: string
	where: string
	title: string
	/** what to do, said once, short */
	hint: string
	/** where the map flies when the step opens: [west, south, east, north] */
	view: [number, number, number, number]
}

/** the core of L'Horta Sud: Torrent's east, Picanya, Paiporta, Sedaví, Alfafar, Massanassa, Catarroja, Benetússer */
const HORTA: [number, number, number, number] = [-0.4655, 39.3895, -0.3545, 39.4535]
/** the Pego-Oliva marsh: the box of the Copernicus EMSR935 flooded area of AOI01 (data/labels), a little wider */
const PEGO: [number, number, number, number] = [-0.099, 38.846, -0.005, 38.893]

/** the guided flow: steps 2 to 5 of the pitch (the landing hero is step 1); ?step=2 to 5 opens one */
export const STEPS: Step[] = [
	{ key: 'missed', when: '29 Oct 2024', where: "L'Horta Sud", title: 'The official map said safe', hint: 'Tap a blue street', view: HORTA },
	{ key: 'simulation', when: '29 Oct 2024', where: "L'Horta Sud", title: 'Our simulation saw it', hint: 'Switch between the two maps', view: HORTA },
	{ key: 'nisar', when: '28 Oct 2026', where: 'Pego-Oliva', title: 'NISAR sees more water', hint: 'Drag the line', view: PEGO },
	{ key: 'coming', when: '29 Oct 2024', where: "L'Horta Sud", title: 'Would we have seen it coming?', hint: 'Switch between the two rains', view: HORTA },
]

/** the marsh model screens, out of the flow: "All layers" opens them (?screen=exam, ?screen=rain) */
export const SCREENS: Step[] = [
	{ key: 'exam', when: 'Oct 2026', where: 'Pego-Oliva', title: 'Did we get it right?', hint: 'Drag the line', view: PEGO },
	{ key: 'rain', when: 'Today', where: 'Pego-Oliva', title: 'What if it rains', hint: 'Slide the rain', view: PEGO },
]

/** the methods of step 3's switch (keys of streets.json methods): step 5 has its own switch, from coming.json */
export const STEP3_METHODS = ['zones', 'sim']

/** the colours of the steps; the blue of the flooded streets is the one of the measured water marks */
export const COLORS = {
	flooded: '#2f8cff',
	floodedGlow: '#9fd0ff',
	zone: '#ff9500',
	sim: '#c76bff',
	hit: '#2fd27a',
	falseAlarm: '#ff4d4f',
	missed: '#ffd23f',
	rain: '#7fe0f0',
}

/** what the swipe of step 4 compares: 'open' (open water only on both sides, public/layers/guided/swipe.json) or
 *  'any' (open water and flooded vegetation on both sides, the /views pictures and numbers of views.json) */
export const SWIPE_WATER: 'open' | 'any' = 'open'

/** how long the flooded streets take to appear when step 2 opens, and how long each of its 16 groups fades in */
export const REVEAL_MS = 4000
export const REVEAL_FADE_MS = 700

export const META = {
	title: 'The flood map · Dancing with the SARs',
	description: 'What the official flood map missed in the Valencia flood of 2024, what our street simulation and NISAR radar saw, and whether the forecast of the night before would have seen it coming.',
}
