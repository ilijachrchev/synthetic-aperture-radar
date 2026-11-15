// The model's prediction of where the water goes (pipeline/prediction/spatial), as the app reads it:
// public/layers/<site>/prediction.json and prediction/* (scripts/bake_prediction.py).
//
// A click reads its numbers from the baked planes with the page's own code (inflated with DecompressionStream),
// not back from a canvas: browsers that guard against fingerprinting add noise to pixels read from a canvas, and
// every number on the panel has to be the one in the result file.
import type { Bounds } from './gl-quad'
import { mercX, mercY } from './gl-quad'

export type PredictionMap = {
	id: string
	/** 'scenario': hypothetical rain after the latest radar map. 'reconstruction': a replay with the rain that fell */
	mode: 'scenario' | 'reconstruction'
	rain_mm: number | null
	file: string
	bytes: number
	data: string
	data_bytes: number
	data_planes: string[]
	issued_from_pass: string | null
	/** 'Sentinel-1', 'NISAR' or 'radar': the map the prediction starts from */
	issued_from_sensor?: string
	issue_time_utc: string
	target_time_utc: string
	target_nisar_granule?: string | null
	lead_days: number
	rain: { rain_prior_7d_mm: number; rain_prior_30d_mm: number; rain_between_mm: number; rain_between_max1d_mm: number; days_since_rain_peak: number }
	rain_source: string
	rain_seen_in_training?: { max: number; p99: number; p90: number; targets_over_100mm: number; inside_training_range: boolean } | null
	thresholds: { water: number; new_water: number }
	area_ha: { likely_water: number; likely_new_water: number; counted_on: string }
	area_ha_drawn: { likely_water: number; likely_new_water: number }
	mode_note: string
	validation_status: string
	caption: { title: string; line: string; note: string; warning: string | null }
	sources: Record<string, unknown>
}

type Pass = { plane: number; time_utc?: string; date?: string; granule?: string | null }

export type Prediction = {
	site: string
	baked_utc: string
	source: { folder: string; ref: string | null; commit: string | null; index: string; model_sha256_16?: string }
	grid: { width: number; height: number; bounds: Bounds; zoom: number; pixel_m: number }
	model: string
	score: string
	evidence: Record<string, string>
	attribution: string
	scenarios: PredictionMap[]
	replays: PredictionMap[]
	inspect: {
		file: string
		bytes: number
		planes: number
		landcover?: { plane: number; source: string; product: string; classes: Record<string, string>; nodata: number }
		soil?: { plane: number; date: string; source: string; product: string; maturity: string; unit: string; scale: number; nodata: number; median_m3m3: number | null; resolution_m: number }
		history?: { series: string; sensor: string; product: string; source: string; bounds: Bounds; passes: Pass[] }
	}
}

/** the places the model covers; their files are read only when someone clicks in their box. `note` is what a
 *  reader of that place must know before reading its water history */
export const PREDICTION_SITES: { site: string; name: string; root: string; path: string; note?: string }[] = [
	{ site: 'pego_oliva', name: 'Pego-Oliva', root: '/layers/pego_oliva', path: '/flood' },
	{
		site: 'albufera',
		name: 'Albufera',
		root: '/layers/albufera',
		path: '/rice',
		note: 'In autumn farmers flood the harvested rice fields here, so new water after October is often farm water, not a flood. The NISAR water model was also trained on this site.',
	},
]

const jsons = new Map<string, Promise<Prediction | null>>()

/** prediction.json of a site; null when the site has none */
export function loadPrediction(root: string): Promise<Prediction | null> {
	let p = jsons.get(root)
	if (!p) {
		p = fetch(`${root}/prediction.json`)
			.then((r) => (r.ok ? (r.json() as Promise<Prediction>) : null))
			.catch(() => null)
		jsons.set(root, p)
	}
	return p
}

/** the address of a baked file, with the time of the bake so a new bake is never taken from the browser's cache */
export const fileUrl = (root: string, p: Prediction, file: string) => `${root}/${file}?v=${encodeURIComponent(p.baked_utc)}`

/** the pixel of the grid under a point, or null outside it */
export function pixelAt(grid: Prediction['grid'], lngLat: [number, number]): { row: number; col: number } | null {
	const [west, south, east, north] = grid.bounds
	const x = (mercX(lngLat[0]) - mercX(west)) / (mercX(east) - mercX(west))
	const y = (mercY(lngLat[1]) - mercY(north)) / (mercY(south) - mercY(north))
	if (!(x >= 0 && x < 1 && y >= 0 && y < 1)) return null
	return { row: Math.min(grid.height - 1, Math.floor(y * grid.height)), col: Math.min(grid.width - 1, Math.floor(x * grid.width)) }
}

export function inBounds(b: Bounds, lngLat: [number, number]) {
	return lngLat[0] >= b[0] && lngLat[0] <= b[2] && lngLat[1] >= b[1] && lngLat[1] <= b[3]
}

// ---------------------------------------------------------------- the planes of one file (format PLN1)

type Planes = { width: number; height: number; planes: number; rows: number; bands: number; offsets: Uint32Array; data: Uint8Array }

const files = new Map<string, Promise<Planes>>()
const bandCache = new Map<string, Promise<Uint8Array>>()
const BAND_CACHE = 64

/** fetch a planes file once; `low` fetches it without hurry, ahead of a click */
export function loadPlanes(url: string, low = false): Promise<Planes> {
	let p = files.get(url)
	if (!p) {
		p = fetch(url, low ? { priority: 'low' } : undefined)
			.then((r) => {
				if (!r.ok) throw new Error(`${url}: ${r.status}`)
				return r.arrayBuffer()
			})
			.then((buf) => {
				const head = new DataView(buf)
				const magic = String.fromCharCode(...new Uint8Array(buf, 0, 4))
				if (magic !== 'PLN1') throw new Error(`${url}: not a planes file`)
				const [width, height, planes, rows, bands] = [4, 8, 12, 16, 20].map((o) => head.getUint32(o, true))
				const n = planes * bands + 1
				const offsets = new Uint32Array(n)
				for (let i = 0; i < n; i++) offsets[i] = head.getUint32(24 + 4 * i, true)
				return { width, height, planes, rows, bands, offsets, data: new Uint8Array(buf, 24 + 4 * n) }
			})
		p.catch(() => files.delete(url))
		files.set(url, p)
	}
	return p
}

async function inflate(bytes: Uint8Array): Promise<Uint8Array> {
	const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream('deflate'))
	return new Uint8Array(await new Response(stream).arrayBuffer())
}

/** one band of one plane, inflated once and kept a while */
function bandOf(url: string, f: Planes, plane: number, band: number): Promise<Uint8Array> {
	const key = `${url}#${plane}#${band}`
	let b = bandCache.get(key)
	if (!b) {
		const i = plane * f.bands + band
		b = inflate(f.data.subarray(f.offsets[i], f.offsets[i + 1]))
		bandCache.set(key, b)
		if (bandCache.size > BAND_CACHE) bandCache.delete(bandCache.keys().next().value!)
	}
	return b
}

/** the bytes of every plane of a file at one pixel */
export async function readPixel(url: string, row: number, col: number, wanted?: number[]): Promise<number[]> {
	const f = await loadPlanes(url)
	const band = Math.floor(row / f.rows)
	const inBand = (row - band * f.rows) * f.width + col
	const list = wanted ?? Array.from({ length: f.planes }, (_, i) => i)
	return Promise.all(list.map(async (plane) => (await bandOf(url, f, plane, band))[inBand]))
}

// ---------------------------------------------------------------- one spot of ground

export type Spot = {
	site: string
	name: string
	note?: string
	lngLat: [number, number]
	/** the model's map the page shows now, and what it says here */
	model: { map: PredictionMap; evidence: number; water: number | null; dryBefore: boolean | null } | null
	/** NISAR, pass by pass: 0 not seen, 1 dry, 2 water under plants, 3 open water; null outside the story's box */
	history: { time: string; state: number }[] | null
	soil: { value: number | null; date: string; median: number | null } | null
	land: { code: number; name: string } | null
}

export type SpotResult = { kind: 'spot'; spot: Spot } | { kind: 'outside' } | { kind: 'error'; message: string }

/**
 * What the files say about one point: the model's likelihood under the map shown (by id), the NISAR water history
 * of the pixel, the soil moisture before the storm and the land type. `outside` when no covered box holds it.
 */
export async function inspectAt(lngLat: [number, number], mapId: string | null): Promise<SpotResult> {
	for (const s of PREDICTION_SITES) {
		const p = await loadPrediction(s.root)
		if (!p || !inBounds(p.grid.bounds, lngLat)) continue
		const px = pixelAt(p.grid, lngLat)
		if (!px) continue
		try {
			const all = [...p.scenarios, ...p.replays]
			const map = all.find((m) => m.id === mapId) ?? p.scenarios.find((m) => m.rain_mm === 100) ?? all[0]
			const [model, info] = await Promise.all([
				map ? readPixel(fileUrl(s.root, p, map.data), px.row, px.col) : Promise.resolve(null),
				readPixel(fileUrl(s.root, p, p.inspect.file), px.row, px.col),
			])
			let m: Spot['model'] = null
			if (map && model) {
				const plane = (name: string) => map.data_planes.indexOf(name)
				const ev = model[plane('evidence')]
				const w = model[plane('water_likelihood_pct')]
				const dryI = plane('dry_before')
				const newI = plane('new_water_likelihood_pct')
				const dry = dryI >= 0 ? model[dryI] === 1 : newI >= 0 ? model[newI] !== 255 : null
				m = { map, evidence: ev, water: w === 255 ? null : w, dryBefore: w === 255 ? null : dry }
			}
			const { landcover, soil, history } = p.inspect
			const lc = landcover ? info[landcover.plane] : 0
			const sm = soil ? info[soil.plane] : 255
			const inStory = history ? inBounds(history.bounds, lngLat) : false
			return {
				kind: 'spot',
				spot: {
					site: s.site,
					name: s.name,
					note: s.note,
					lngLat,
					model: m,
					history: history && inStory ? history.passes.map((x) => ({ time: x.time_utc ?? `${x.date}T12:00:00Z`, state: info[x.plane] })) : null,
					soil: soil ? { value: sm === 255 ? null : sm / soil.scale, date: soil.date, median: soil.median_m3m3 } : null,
					land: landcover && lc ? { code: lc, name: landcover.classes[String(lc)] ?? `class ${lc}` } : null,
				},
			}
		} catch (e) {
			return { kind: 'error', message: (e as Error).message }
		}
	}
	return { kind: 'outside' }
}

/** fetch what a click reads, without hurry, so the first click answers at once */
export function warmInspect(root: string, mapIds: string[]) {
	loadPrediction(root).then((p) => {
		if (!p) return
		loadPlanes(fileUrl(root, p, p.inspect.file), true).catch(() => {})
		for (const m of [...p.scenarios, ...p.replays]) if (mapIds.includes(m.id)) loadPlanes(fileUrl(root, p, m.data), true).catch(() => {})
	})
}
