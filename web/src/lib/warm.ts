// Fetch ahead of time, into the browser's cache and without hurry, what a story page shows first: its data, the radar
// frames of its first view and its first picture, plus MapLibre and its worker. The landing warms the flood before
// anyone clicks "Open the map"; each story page warms the other two once its own view is up. Every request is low
// priority, so it never holds up what is on screen. The map tiles are in the app and come fast on their own.
import type { Story } from '@/content/stories'

type Frame = { file: string; time_utc?: string; date?: string }
type Series = { id: string; frames: Frame[]; always?: { file: string } }
type Meta = { base: string; baked_utc: string; series: Series[] }
type Optical = { scenes: { day: string; file: string; cloud_pct?: number; scenes: { cloud_pct: number }[] }[] }

const LOW: RequestInit = { priority: 'low' }
/** a picture with less cloud than this counts as clear (as in story-app.tsx) */
const CLEAR_PCT = 12
const done = new Set<string>()

const json = <T>(url: string) =>
	fetch(url, LOW)
		.then((r) => (r.ok ? (r.json() as Promise<T>) : null))
		.catch(() => null)

/** MapLibre's code and its worker, for a page that has not loaded them yet */
export function warmMaplibre() {
	if (done.has('maplibre')) return
	done.add('maplibre')
	import('maplibre-gl')
		.then((m) => fetch(`/maplibre/maplibre-gl-worker.mjs?v=${m.getVersion()}`, LOW))
		.catch(() => {})
}

/** the files of a story's first view */
export async function warmStory(story: Story) {
	if (done.has(story.key)) return
	done.add(story.key)
	const [meta, optical] = await Promise.all([
		json<Meta>(`${story.root}/meta.json`),
		json<Optical>(`${story.root}/optical.json`),
		json(`${story.root}/story.json`),
		story.storm ? json(`${story.root}/rain.json`) : null,
	])
	if (!meta) return
	const files = [meta.base]
	const series = story.series.map((id) => meta.series.find((s) => s.id === id)).find((s): s is Series => !!s)
	if (series) {
		const time = (f: Frame) => Date.parse(f.time_utc ?? `${f.date}T12:00:00Z`)
		const from = Date.parse(story.window.from)
		const first = series.frames.findIndex((f) => time(f) >= from)
		if (first >= 0) for (const f of series.frames.slice(first, first + 3)) files.push(f.file)
		// what "new" is measured against: the last pass before the storm or the fire, or the water always there
		const turn = story.storm ? Date.parse(story.storm.from) : story.event ? Date.parse(story.event.t) : null
		if (turn !== null) {
			const before = series.frames.filter((f) => time(f) >= from && time(f) < turn).pop()
			if (before) files.push(before.file)
		}
		if (story.kind === 'season' && series.always) files.push(series.always.file)
	}
	const clear = optical?.scenes.find((s) => (s.cloud_pct ?? Math.max(...s.scenes.map((x) => x.cloud_pct))) < CLEAR_PCT)
	if (clear) files.push(clear.file)
	const v = `?v=${encodeURIComponent(meta.baked_utc)}`
	for (const file of new Set(files)) fetch(`${story.root}/${file}${v}`, LOW).catch(() => {})
}

/** run `fn` once the page is idle, or after `ms` at the latest */
export function whenIdle(fn: () => void, ms = 2500) {
	const w = window as unknown as { requestIdleCallback?: (cb: () => void, o: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void }
	if (w.requestIdleCallback) {
		const id = w.requestIdleCallback(fn, { timeout: ms })
		return () => w.cancelIdleCallback?.(id)
	}
	const id = window.setTimeout(fn, Math.min(ms, 1200))
	return () => window.clearTimeout(id)
}
