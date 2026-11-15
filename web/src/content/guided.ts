// The guided flood map (/explore): five steps, one main action each. The words are here; every number comes from a
// baked file (public/layers/guided/*.json, public/layers/pego_oliva/views.json, public/layers/explore/explore.json,
// public/layers/pego_oliva/prediction.json), read at run time with the field it comes from.

export type StepKey = 'missed' | 'simulation' | 'nisar' | 'exam' | 'rain'

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
/** the Pego-Oliva marsh, on the Copernicus EMS flood of Oct 2026 */
const PEGO: [number, number, number, number] = [-0.135, 38.85, -0.035, 38.93]

export const STEPS: Step[] = [
	{ key: 'missed', when: '29 Oct 2024', where: "L'Horta Sud", title: 'The official map said safe', hint: 'Tap a blue street', view: HORTA },
	{ key: 'simulation', when: '29 Oct 2024', where: "L'Horta Sud", title: 'Our simulation saw it', hint: 'Switch between the two maps', view: HORTA },
	{ key: 'nisar', when: '28 Oct 2026', where: 'Pego-Oliva', title: 'NISAR sees more water', hint: 'Drag the line', view: PEGO },
	{ key: 'exam', when: 'Oct 2026', where: 'Pego-Oliva', title: 'Did we get it right?', hint: 'Drag the line', view: PEGO },
	{ key: 'rain', when: 'Today', where: 'Pego-Oliva', title: 'What if it rains', hint: 'Slide the rain', view: PEGO },
]

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

/** how long the flooded streets take to appear when step 2 opens, and how long each of its 16 groups fades in */
export const REVEAL_MS = 4000
export const REVEAL_FADE_MS = 700

export const META = {
	title: 'The flood map · Dancing with the SARs',
	description: 'What the official flood map missed in the Valencia flood of 2024, what our simulation and NISAR radar saw, and how our model did on the next flood.',
}
