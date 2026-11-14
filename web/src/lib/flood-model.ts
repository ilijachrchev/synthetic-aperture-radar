// Time for the flood animation: where the playhead sits between two radar passes, how far the picture has
// travelled, and the hectares it shows. Pure functions over the baked files, no drawing in here.
//
// Three rules keep it honest:
//   1. At a pass the picture is that pass and nothing else (observed 1).
//   2. Between passes the picture is an interpolation (observed 0), and the page says so.
//   3. Where a storm fell between two passes, water rises with the rain and only falls once the rain has stopped,
//      so it never rises under a dry sky and never shrinks while it pours. Elsewhere both run evenly with the clock.
import type { WaterGap, WaterSeries } from './water-layer'

export type RainFile = {
	source: string
	total_mm: number
	hours: { t: string; mm: number }[]
}

const HOUR = 3600e3
/** a gap between two passes follows the rain when at least this much fell in it */
const RAIN_DRIVES_MM = 15
/** the rain counts as over once this share of it has fallen */
const RAIN_DONE = 0.97

export type FloodView = {
	a: number
	b: number
	gain: number
	loss: number
	observed: number
	/** the pass the playhead sits on, if any */
	pass: number | null
	/** true when this gap follows the rain */
	storm: boolean
}

export type FloodModel = ReturnType<typeof floodModel>

const at = (rows: [number, number][], x: number): [number, number] => {
	const f = Math.min(1, Math.max(0, x)) * (rows.length - 1)
	const i = Math.min(rows.length - 2, Math.floor(f))
	const k = f - i
	return [rows[i][0] + (rows[i + 1][0] - rows[i][0]) * k, rows[i][1] + (rows[i + 1][1] - rows[i][1]) * k]
}

export function floodModel(series: WaterSeries, rain: RainFile | null) {
	const frames = series.frames
	const times = frames.map((f) => Date.parse(f.time_utc ?? `${f.date}T12:00:00Z`))
	const first = times[0]
	const last = times[times.length - 1]

	// rain: each value is the rain of the hour that ends at its time
	const rainT = rain ? rain.hours.map((h) => Date.parse(h.t)) : []
	const rainMm = rain ? rain.hours.map((h) => h.mm) : []
	const prefix: number[] = []
	rainMm.reduce((acc, mm, i) => (prefix[i] = acc + mm), 0)
	const rainUpTo = (T: number) => {
		if (!rainT.length || T <= rainT[0]) return 0
		if (T >= rainT[rainT.length - 1]) return prefix[prefix.length - 1]
		const k = Math.floor((T - rainT[0]) / HOUR)
		return prefix[k] + ((T - rainT[k]) / HOUR) * rainMm[k + 1]
	}
	const pairRain = times.slice(0, -1).map((t, i) => rainUpTo(times[i + 1]) - rainUpTo(t))
	// in a storm gap: the moment the rain is over
	const rainEnd = times.slice(0, -1).map((t, i) => {
		if (pairRain[i] < RAIN_DRIVES_MM) return t
		const target = rainUpTo(t) + pairRain[i] * RAIN_DONE
		let lo = t
		let hi = times[i + 1]
		for (let k = 0; k < 40; k++) {
			const mid = (lo + hi) / 2
			if (rainUpTo(mid) < target) lo = mid
			else hi = mid
		}
		return hi
	})

	/** index of the pass at or before T */
	const before = (T: number) => {
		let lo = 0
		let hi = times.length - 1
		while (lo < hi) {
			const mid = (lo + hi + 1) >> 1
			if (times[mid] <= T) lo = mid
			else hi = mid - 1
		}
		return lo
	}

	const viewAt = (T: number): FloodView => {
		const n = times.length - 1
		if (T <= first) return { a: 0, b: Math.min(1, n), gain: 0, loss: 0, observed: 1, pass: 0, storm: false }
		if (T >= last) return { a: Math.max(0, n - 1), b: n, gain: 1, loss: 1, observed: 1, pass: n, storm: false }
		const a = before(T)
		const b = a + 1
		const gap = times[b] - times[a]
		const linear = (T - times[a]) / gap
		const storm = pairRain[a] >= RAIN_DRIVES_MM
		let gain = linear
		let loss = linear
		if (storm) {
			gain = Math.min(1, (rainUpTo(T) - rainUpTo(times[a])) / (pairRain[a] * RAIN_DONE))
			loss = T <= rainEnd[a] ? 0 : (T - rainEnd[a]) / (times[b] - rainEnd[a])
		}
		// "observed" holds for a short while either side of a pass, then gives way to the estimate
		const near = Math.min(T - times[a], times[b] - T)
		const window = Math.min(4 * HOUR, gap * 0.22)
		const x = Math.min(1, near / window)
		const observed = 1 - x * x * (3 - 2 * x)
		const pass = T - times[a] < 60e3 ? a : times[b] - T < 60e3 ? b : null
		return { a, b, gain: Math.min(1, Math.max(0, gain)), loss: Math.min(1, Math.max(0, loss)), observed, pass, storm }
	}

	/** hectares [open water, flooded vegetation] the picture shows at T */
	const areaAt = (T: number): [number, number] => {
		const v = viewAt(T)
		const g: WaterGap = series.between[v.a]
		if (T <= first) return g.both[0]
		if (T >= last) return g.both[g.both.length - 1]
		if (!v.storm) return at(g.both, v.gain)
		return v.loss > 0 ? at(g.loss, v.loss) : at(g.gain, v.gain)
	}

	/** hectares exactly at pass i, as the picture draws it */
	const areaOfPass = (i: number): [number, number] => {
		if (i < series.between.length) return series.between[i].both[0]
		const rows = series.between[series.between.length - 1].both
		return rows[rows.length - 1]
	}

	return { times, first, last, rainT, rainMm, rainUpTo, pairRain, rainEnd, viewAt, areaAt, areaOfPass, before }
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "22 Oct 2026" in UTC */
export function utcDay(T: number, year = true) {
	const d = new Date(T)
	return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${year ? ` ${d.getUTCFullYear()}` : ''}`
}

/** "06:09 UTC" */
export function utcClock(T: number) {
	const d = new Date(T)
	return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} UTC`
}

export const PLATFORMS: Record<string, string> = {
	S1A: 'Sentinel-1A',
	S1C: 'Sentinel-1C',
	S1D: 'Sentinel-1D',
	NISAR: 'NISAR',
}
