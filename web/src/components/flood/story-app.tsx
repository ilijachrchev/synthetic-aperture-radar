'use client'

// One story on the map: where it flooded, where it burned. The map is the page. On it: a small title with the switch
// between stories, the date with one number, at most a few labels that point at their thing, one short sentence and
// a thin time strip. Everything else sits behind the Layers button.
//
// What is drawn stays what the radar measured: at a pass the picture is that pass, between two passes it is an
// estimate and the readout says so in one word.

import 'maplibre-gl/dist/maplibre-gl.css'
import { Layers, Pause, Play } from 'lucide-react'
import type { Map as MapLibreMap, Marker as MapLibreMarker, MapMouseEvent } from 'maplibre-gl'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { STORIES, type Story } from '@/content/stories'
import { type FloodModel, type RainFile, floodModel, utcDay } from '@/lib/flood-model'
import type { Bounds } from '@/lib/gl-quad'
import { LikelihoodLayer } from '@/lib/likelihood-layer'
import { PictureLayer } from '@/lib/picture-layer'
import { PREDICTION_SITES, type Prediction, type SpotResult, fileUrl, inspectAt, loadPrediction, warmInspect } from '@/lib/prediction'
import { FAR_BASE, TERRAIN, addFarBase, emptyLayer, farView, flyIn, set3d, setSky, warmUp } from '@/lib/scene3d'
import { maxZoomOf, tileCount, tilesOf, transformTile } from '@/lib/tiles'
import { warmStory, whenIdle } from '@/lib/warm'
import { WaterLayer, type WaterMeta, type WaterSeries } from '@/lib/water-layer'
import { ThemeSwitch } from '../theme-switch'
import { RainSlider } from './rain-slider'
import { SpotPanel } from './spot-panel'
import './story.css'
import './prediction.css'

/** MapLibre is the largest file of the page: fetch it as soon as this code runs in the browser, while the story's
 *  data is on its way, and start its workers right away. Nothing happens on the server. */
const maplibre =
	typeof window === 'undefined'
		? null
		: import('maplibre-gl').then((m) => {
				m.setWorkerUrl(`/maplibre/maplibre-gl-worker.mjs?v=${m.getVersion()}`)
				// the tiles come from this site over one connection: more of them at once
				m.setMaxParallelImageRequests(32)
				m.prewarm()
				return m
			})

type Scene = { day: string; file: string; time_utc: string; cloud_pct?: number; scenes: { cloud_pct: number }[] }
type Optical = { bounds: Bounds; credit: string; scenes: Scene[] }
type Label = { id: string; at: [number, number]; title: string; value: string }
type Shape = { type: 'Feature'; geometry: { type: string; coordinates: unknown }; properties: { name: string; detail?: string; area_ha: number } }
/** story.json (scripts/bake_story.py): where the labels go, the official map as one shape, the measured depths */
type Extra = {
	labels: Label[]
	official: Shape | null
	depth: { type: 'FeatureCollection'; features: { properties: { m: number } }[] }
	/** how much of what is new lies inside the official map */
	inside_official?: { new_ha: number; inside_ha: number; share: number } | null
	/** what the new ground was before, by ESA WorldCover class, largest first */
	landcover?: { name: string; ha: number }[]
	/** the clear picture days for the state before and the state after */
	photos?: { before: string; after: string }
}
type Data = { meta: WaterMeta; rain: RainFile | null; optical: Optical; extra: Extra | null }
/** the days of a story as numbers */
type Days = { t0: number; t1: number; storm0: number | null; storm1: number | null; event: number | null; eventEnd: number | null }
/** one radar series cut to the days of the story, with its clock and what "new" is measured against */
type Active = {
	series: WaterSeries
	/** the series as the layer loads it: the passes, then the frame of the water that is always there */
	layerSeries: WaterSeries
	model: FloodModel
	twoClass: boolean
	/** frame of the layer the picture is compared with, -1 for none */
	ref: number
	/** hectares in the reference */
	refHa: number
}
type Photo = 'clear' | 'day'
/** what the map shows: the radar passes as they were, or the model's map of where the water would go */
type Mode = 'radar' | 'model'

const HOUR = 3600e3
const DAY = 24 * HOUR
/** the cloudless picture of EOX around the place; its tiles for the stories are in the app (lib/tiles.ts) */
const BASE_TILES = tilesOf('base')
/** coast lines, borders and place names, shown only from far out so the way in can be read */
const NAMES_TILES = tilesOf('names')
/** the zoom from which the names are gone: closer in the layer is hidden, so its tiles are not even fetched */
const NAMES_UNTIL = 8.4
/** how often the light on still water moves on, in milliseconds */
const SHIMMER_MS = 83
/** the longest side a satellite picture is decoded at: about its own 10 m on the ground, a third of the bytes of 4096 */
const PICTURE_PX = { desktop: 2560, phone: 2048 }
/** the hold on every pass while playing, and how long a whole story takes to play */
const DWELL_MS = 420
const PLAY_SECONDS = { storm: 9, season: 13, fire: 11 }
/** while playing, the day a fire burns takes this long, or it would be over in a tenth of a second */
const EVENT_MS = 1500
/** while playing a storm: the days before it, the storm itself, and all the days after it until the last pass */
const STORM_MS = { before: 900, storm: 3200, after: 1800 }
/** a measured depth of 1 m stands this many metres tall: the columns compare the points, they are not to scale */
const COLUMN_M = 200
/** a picture with less cloud than this counts as clear */
const CLEAR_PCT = 12

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const ha = (x: number) => Math.round(x).toLocaleString('en-US')
const frameTime = (f: { time_utc?: string; date?: string }) => Date.parse(f.time_utc ?? `${f.date}T12:00:00Z`)
/** the cloud share of a picture: that of the Sentinel-2 scene that fills most of it */
const cloud = (s: Scene) => s.cloud_pct ?? Math.max(...s.scenes.map((x) => x.cloud_pct))
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
/** `?story` alone plays the film. An old link to the retired explorer arrives as `?story=fire`: that one opens the
 *  page as the app it is. */
const asFilm = (q: URLSearchParams) => q.get('story') === ''
/** the resting view of a story on this screen: a narrow, upright screen has a view of its own */
const viewOf = (story: Story): Story['view'] => (window.matchMedia('(max-width: 820px)').matches ? { ...story.view, zoom: story.view.zoom - 1.2, ...story.phone } : story.view)
/** how long the map takes to go from the radar to the model and back */
const MODE_MS = 650

/** prediction.json of a story that has one, once the first view is up: the page never waits for it */
function usePrediction(story: Story, ready: boolean, onLoad: (p: Prediction) => void) {
	const [pred, setPred] = useState<Prediction | null>(null)
	const loaded = useRef(onLoad)
	useEffect(() => {
		loaded.current = onLoad
	}, [onLoad])
	useEffect(() => {
		if (!story.predict || !ready) return
		let gone = false
		loadPrediction(story.root).then((p) => {
			if (gone || !p || !p.scenarios.length) return
			setPred(p)
			loaded.current(p)
		})
		return () => {
			gone = true
		}
	}, [story, ready])
	return pred
}

function useData(story: Story) {
	const [data, setData] = useState<Data | null>(null)
	const [error, setError] = useState<string | null>(null)
	useEffect(() => {
		let gone = false
		const get = (name: string) =>
			fetch(`${story.root}/${name}`).then((r) => {
				if (!r.ok) throw new Error(`${name}: ${r.status}`)
				return r.json()
			})
		// the page still tells its story without story.json, only without labels
		Promise.all([get('meta.json'), get('optical.json'), story.storm ? get('rain.json') : null, get('story.json').catch(() => null)])
			.then(([meta, optical, rain, extra]: [WaterMeta, Optical, RainFile | null, Extra | null]) => !gone && setData({ meta, rain, optical, extra }))
			.catch((e: Error) => !gone && setError(e.message))
		return () => {
			gone = true
		}
	}, [story])
	return { data, error }
}

/** a series with only the passes inside the days of the story */
function inWindow(series: WaterSeries, days: Days): WaterSeries {
	const times = series.frames.map(frameTime)
	const i0 = times.findIndex((t) => t >= days.t0)
	let i1 = times.length - 1
	while (i1 >= 0 && times[i1] > days.t1) i1--
	if (i0 < 0 || i1 < i0) return { ...series, frames: [], between: [] }
	return { ...series, frames: series.frames.slice(i0, i1 + 1), between: series.between.slice(i0, i1) }
}

/** the northernmost point of a shape: a calm place for its label */
function topOf(shape: Shape): [number, number] {
	let best: [number, number] = [0, -90]
	const walk = (c: unknown) => {
		if (Array.isArray(c) && typeof c[0] === 'number') {
			if ((c[1] as number) > best[1]) best = [c[0] as number, c[1] as number]
		} else if (Array.isArray(c)) c.forEach(walk)
	}
	walk(shape.geometry.coordinates)
	return best
}

function Toggle({ label, on, set }: { label: string; on: boolean; set: (v: boolean) => void }) {
	return (
		<button type="button" className="st-toggle" role="switch" aria-checked={on} onClick={() => set(!on)}>
			<span>{label}</span>
			<i />
		</button>
	)
}

export function StoryApp({ story }: { story: Story }) {
	const { data, error } = useData(story)
	const mapEl = useRef<HTMLDivElement>(null)
	const mapRef = useRef<MapLibreMap | null>(null)
	const water = useRef<WaterLayer | null>(null)
	const pic = useRef<PictureLayer | null>(null)
	const track = useRef<HTMLDivElement>(null)
	const head = useRef<HTMLDivElement>(null)
	const el = useRef<Record<string, HTMLElement | null>>({})
	const labels = useRef<Record<string, { box: HTMLElement; value: HTMLElement; at: [number, number] }>>({})
	const st = useRef({ T: 0, playing: false, dwell: 0, now: 0, shown: Number.NaN, beat: -1, zoomFade: -1, hold: false, columns: 0, sky: '', lit: 0, up: false, radar: 1 })
	const speed = useRef(1)
	/** true once the style of the map is read: before that the map takes no sky, no terrain, no layers */
	const styled = useRef(false)

	const [mapReady, setMapReady] = useState(false)
	const [ready, setReady] = useState(false)
	const [playing, setPlaying] = useState(false)
	const [seriesId, setSeriesId] = useState<string | null>(null)
	const [photo, setPhoto] = useState<Photo>('clear')
	const [official, setOfficial] = useState(false)
	const [depth, setDepth] = useState(false)
	const [exact, setExact] = useState(false)
	const [relief, setRelief] = useState(true)
	const [menu, setMenu] = useState(false)
	const [credits, setCredits] = useState(false)
	const [cinema, setCinema] = useState(false)
	const [veil, setVeil] = useState(false)
	const opt = useRef({ photo, official, depth, relief })
	opt.current = { photo, official, depth, relief }

	// the model's map of where the water would go, beside the radar passes (story.predict)
	const [mode, setMode] = useState<Mode>('radar')
	const modeRef = useRef<Mode>('radar')
	useEffect(() => {
		modeRef.current = mode
	}, [mode])
	/** the map shows the radar or the model; the passes stop playing when the model comes */
	const chooseMode = useCallback((m: Mode) => {
		if (m === 'model') setPlaying(false)
		modeRef.current = m
		setMode(m)
	}, [])
	const [rainIdx, setRainIdx] = useState(0)
	const rainPos = useRef(0)
	// the stop a page opens on: 100 mm, or the one in the address (?rain=200); ?mode=model opens the model
	const onPrediction = useCallback(
		(p: Prediction) => {
			const list = p.scenarios.filter((s) => s.rain_mm !== null)
			const q = new URLSearchParams(window.location.search)
			const i = list.findIndex((s) => s.rain_mm === Number(q.get('rain') ?? 100))
			const at = i >= 0 ? i : Math.min(list.length - 1, Math.floor(list.length / 2))
			rainPos.current = at
			setRainIdx(at)
			if (q.get('mode') === 'model') chooseMode('model')
		},
		[chooseMode],
	)
	const pred = usePrediction(story, ready, onPrediction)
	const like = useRef<LikelihoodLayer | null>(null)
	/** the rain scenarios in the order of the slider, the stop chosen, and where the handle is (between two stops
	 *  while it is dragged) */
	const rains = useMemo(() => pred?.scenarios.filter((s) => s.rain_mm !== null) ?? [], [pred])
	/** the model map the layer shows, by id: a click reads its values */
	const shownMap = useRef<string | null>(null)
	const [spot, setSpot] = useState<{ result: SpotResult | null; loading: boolean; pred: Prediction | null; at: [number, number] } | null>(null)
	const spotMarker = useRef<MapLibreMarker | null>(null)
	const spotSeq = useRef(0)

	const days = useMemo<Days>(
		() => ({
			t0: Date.parse(story.window.from),
			t1: Date.parse(story.window.to),
			storm0: story.storm ? Date.parse(story.storm.from) : null,
			storm1: story.storm ? Date.parse(story.storm.to) : null,
			event: story.event ? Date.parse(story.event.t) : null,
			eventEnd: story.event?.until ? Date.parse(story.event.until) : null,
		}),
		[story],
	)

	// the radar series the baked files hold for these days
	const choices = useMemo(
		() => (data ? story.series.map((id) => data.meta.series.find((s) => s.id === id)).filter((s): s is WaterSeries => !!s && inWindow(s, days).frames.length > 1) : []),
		[data, story, days],
	)
	const active = useMemo<Active | null>(() => {
		if (!data || !choices.length) return null
		const series = inWindow(choices.find((s) => s.id === seriesId) ?? choices[0], days)
		const model = floodModel(series, data.rain, days.event !== null && days.eventEnd !== null ? { from: days.event, to: days.eventEnd } : null)
		const base = { series, layerSeries: series, model, twoClass: series.frames.some((f) => f.veg_ha > 0) }
		// a storm or a fire is measured against the last pass before it
		const turn = days.storm0 ?? days.event
		if (turn !== null && model.times[0] < turn) {
			const ref = model.before(turn)
			return { ...base, ref, refHa: model.areaOfPass(ref)[0] }
		}
		// a season is measured against the water every pass has: one more frame after the passes
		if (story.kind === 'season' && series.always) {
			const frames = [...series.frames, { file: series.always.file, granules: [], open_ha: series.always.water_ha, veg_ha: 0, seen: 1 }]
			return { ...base, layerSeries: { ...series, frames }, ref: frames.length - 1, refHa: series.always.water_ha }
		}
		return { ...base, ref: -1, refHa: 0 }
	}, [data, choices, seriesId, days, story])

	// The first view waits for its radar frames. Fetch them as soon as the story's data is here, while MapLibre is
	// still on its way, so the layer finds them in the browser's cache when it asks.
	useEffect(() => {
		if (!data || !active) return
		const v = `?v=${encodeURIComponent(data.meta.baked_utc)}`
		const { model, layerSeries, ref } = active
		const at = model.viewAt(model.first)
		const frames = [at.a, at.b, at.b + 1, ref].filter((i) => i >= 0 && i < layerSeries.frames.length).map((i) => layerSeries.frames[i].file)
		for (const file of new Set([data.meta.base, ...frames])) fetch(`${story.root}/${file}${v}`).catch(() => {})
	}, [data, active, story])

	// the story in a few short lines, every number read from the baked files
	const beats = useMemo(() => {
		if (!data || !active) return []
		const { model, series, twoClass, ref } = active
		const last = series.frames.length - 1
		const areas = series.frames.map((_, i) => model.areaOfPass(i)[0])
		const day = (i: number) => utcDay(model.times[i], false)
		if (story.kind === 'fire' && days.event !== null) {
			const first = areas.findIndex((a) => a > 0)
			const list = [{ from: model.first, text: 'Before the fire' }]
			if (first > 0) {
				list.push({ from: days.event, text: `${utcDay(days.event, false)}: the fire starts` })
				list.push({ from: (days.eventEnd ?? days.event) + 6 * HOUR, text: `No radar pass until ${day(first)}: an estimate` })
				list.push({ from: model.times[first] - 3 * HOUR, text: `${day(first)}: the radar confirms ${ha(areas[first])} ha` })
				if (last > first) list.push({ from: model.times[first] + 3 * DAY, text: 'Pass after pass, the radar confirms more' })
				if (last > first) list.push({ from: model.times[last] - 5 * DAY, text: `${ha(areas[last])} ha confirmed by ${day(last)}` })
			}
			return list
		}
		if (story.kind === 'season') {
			const usual = [...areas].sort((a, b) => a - b)[Math.floor(areas.length / 2)]
			const high = areas.indexOf(Math.max(...areas))
			// the first pass from which the water stays well above its usual level
			let rise = areas.length
			for (let i = areas.length - 1; i >= 0 && areas[i] > usual * 1.15; i--) rise = i
			const early = (i: number) => model.times[i] - (model.times[i] - model.times[i - 1]) * 0.45
			const list = [{ from: model.first, text: 'Summer: the lagoon holds the water' }]
			if (rise > 1 && rise < areas.length) list.push({ from: early(rise), text: 'Autumn: farmers flood the rice fields' })
			if (high > rise) list.push({ from: early(high), text: `${day(high)}: ${ha(areas[high])} ha of water. Farm water, not a flood` })
			return list
		}
		const after = Math.min(last, Math.max(0, ref) + 1)
		const rain = data.rain && days.storm0 !== null && days.storm1 !== null ? data.rain.hours.filter((h) => Date.parse(h.t) > days.storm0! && Date.parse(h.t) <= days.storm1!).reduce((a, h) => a + h.mm, 0) : 0
		const what = twoClass ? 'of open water' : 'under water'
		const list = [{ from: model.first, text: 'Before the storm' }]
		if (days.storm0 !== null) list.push({ from: days.storm0, text: `${story.title}: ${ha(rain)} mm of rain in two days (weather model)` })
		// no radar passed during the storm: until the next pass the picture is our estimate, and the page says so
		if (days.storm1 !== null && model.times[after] > days.storm1 + 12 * HOUR) list.push({ from: days.storm1, text: `No radar pass until ${day(after)}: an estimate` })
		list.push({ from: model.times[after] - 3 * HOUR, text: `${day(after)}, the next radar pass: ${ha(areas[after])} ha ${what}` })
		if (last > after && days.storm1 !== null) {
			const weeks = Math.round((model.last - days.storm1) / (7 * DAY))
			list.push({ from: model.times[after] + 30 * HOUR, text: 'The water goes down slowly' })
			list.push({ from: model.last - 4 * DAY, text: twoClass ? `${weeks} weeks on: still ${ha(areas[last])} ha of open water` : `${weeks} weeks on: ${ha(areas[last])} ha still under water` })
		}
		return list
	}, [data, active, story, days])

	/** the pictures a moment may show: the clear ones, or all of them */
	const scenesFor = useCallback(
		(mode: Photo) => {
			if (!data) return []
			// clear pictures only, and none later than the one chosen for the state after: a later one may be clear by its
			// number and still have cloud over the place
			const until = data.extra?.photos?.after
			const clear = data.optical.scenes.filter((s) => cloud(s) < CLEAR_PCT && (!until || s.day <= until))
			return mode === 'clear' && clear.length ? clear : data.optical.scenes
		},
		[data],
	)

	/** say one line, with a small rise so the eye catches the change */
	const say = useCallback((text: string) => {
		const node = el.current.caption
		if (!node || node.textContent === text) return
		node.textContent = text
		node.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 420, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' })
	}, [])

	/** Each label leans away from the others and from the edges of the screen, so they never sit on each other,
	 *  whichever way the camera looks. */
	const lean = useCallback(() => {
		const map = mapRef.current
		if (!map) return
		const shown = Object.values(labels.current)
			.filter((l) => l.box.dataset.show)
			.map((l) => ({ l, p: map.project(l.at) }))
		if (!shown.length) return
		const cx = shown.reduce((a, x) => a + x.p.x, 0) / shown.length
		const cy = shown.reduce((a, x) => a + x.p.y, 0) / shown.length
		const w = map.getContainer().clientWidth
		const h = map.getContainer().clientHeight
		for (const { l, p } of shown) {
			let north = shown.length === 1 || p.y <= cy
			let west = shown.length > 1 && p.x < cx
			if (p.y < 190) north = false
			if (p.y > h - 260) north = true
			// near an edge a label leans inwards; on a narrow screen the edges are close
			const edge = Math.min(250, w * 0.46)
			if (p.x < edge) west = false
			else if (p.x > w - edge) west = true
			const dir = `${north ? 'n' : 's'}${west ? 'w' : 'e'}`
			if (l.box.dataset.lean !== dir) l.box.dataset.lean = dir
		}
	}, [])

	/** draw one moment: the map layers, the readout, the labels, the playhead */
	const apply = useCallback(
		(T: number) => {
			if (!data || !active) return
			const s = st.current
			const { model, ref } = active
			const v = model.viewAt(T)
			water.current?.set({ a: v.a, b: v.b, gain: v.gain, loss: v.loss, observed: v.observed, ref })
			water.current?.want(v.b + 1)

			// the newest picture of this moment: a clear one unless the day's own picture is asked for
			const pool = scenesFor(opt.current.photo)
			const scene = pool.filter((x) => Date.parse(x.time_utc) <= T).pop() ?? pool[0]
			if (scene) pic.current?.show(scene.day)
			// and, once the first view is complete, the next picture is fetched before the playhead gets there
			const next = pool.find((x) => Date.parse(x.time_utc) > T)
			if (next && s.up && pic.current?.current()) pic.current.preload(next.day)

			const e = el.current
			const put = (node: HTMLElement | null | undefined, text: string) => {
				if (node && node.textContent !== text) node.textContent = text
			}
			const [open] = model.areaAt(T)
			const fresh = Math.max(0, open - active.refHa)
			// in the model view the readout, the caption and the labels belong to the model's map (see showModel)
			const radar = modeRef.current === 'radar'
			if (radar) {
				put(e.date, utcDay(T))
				if (e.state) {
					e.state.dataset.pass = v.pass !== null ? 'true' : 'false'
					put(e.state, v.pass !== null ? 'Radar pass' : 'Estimate')
				}
				put(e.num, ha(open))
				const mapped = data.extra?.official?.properties.area_ha
				if (story.kind === 'fire') put(e.delta, open > 0.5 && mapped ? `EU map: ${ha(mapped)} ha` : 'No burn yet')
				else if (story.kind === 'season') put(e.delta, fresh > 50 ? `+${ha(fresh)} ha of farm water` : 'The lagoon')
				else put(e.delta, fresh > 5 && ref >= 0 ? `+${ha(fresh)} ha since ${utcDay(model.times[ref], false)}` : 'Normal for the marsh')
			}
			if (scene) {
				const c = cloud(scene)
				put(e.pic, `Photo: Sentinel-2, ${utcDay(Date.parse(scene.time_utc), false)}${c >= CLEAR_PCT ? `, ${c >= 99.5 ? '100' : c.toFixed(0)} % cloud` : ''} ·`)
			}

			if (!s.hold && radar) {
				let beat = 0
				for (let i = 0; i < beats.length; i++) if (T >= beats[i].from) beat = i
				if (beat !== s.beat) {
					s.beat = beat
					say(beats[beat]?.text ?? '')
				}
			}
			// rain falls on the picture when the weather model says it rains, harder when it rains harder
			const rain = radar ? model.rainAt(T) : 0
			if (e.rain) e.rain.style.opacity = String(Math.min(0.85, rain / 14))
			// and the sky darkens with it
			const map = mapRef.current
			const sky = !opt.current.relief ? '' : rain > 0.6 ? 'storm' : document.documentElement.getAttribute('data-theme') === 'dark' ? 'night' : 'day'
			if (map && styled.current && sky !== s.sky) {
				s.sky = sky
				if (sky) setSky(map, sky as 'day' | 'night' | 'storm')
			}

			// the labels: each one only while its thing is on the map
			const show = (id: string, on: boolean, value?: string) => {
				const l = labels.current[id]
				if (!l) return
				if (on) l.box.dataset.show = 'true'
				else delete l.box.dataset.show
				if (value !== undefined && l.value.textContent !== value) l.value.textContent = value
			}
			// the labels of the passes are radar numbers: the model's map has none
			show('normal', radar, `${ha(active.refHa)} ha`)
			show('new', radar && fresh > 8, `+${ha(fresh)} ha`)
			show('burn', radar && open > 1, `${ha(open)} ha`)
			show('always', radar, `${ha(active.refHa)} ha`)
			show('season', radar && fresh > 300, `+${ha(fresh)} ha`)
			show('deepest', opt.current.depth)
			show('official', opt.current.official)
			lean()

			const k = clamp01((T - model.first) / Math.max(1, model.last - model.first))
			if (head.current) head.current.style.left = `${(k * 100).toFixed(3)}%`
			put(e.tag, utcDay(T, false))
			s.shown = T
		},
		[data, active, beats, story, scenesFor, say, lean],
	)

	// the map, the pictures, the shapes and the labels
	useEffect(() => {
		if (!data || !mapEl.current) return
		let map: MapLibreMap | null = null
		let gone = false
		;(async () => {
			const { Map, Marker } = await (maplibre ?? import('maplibre-gl'))
			if (gone || !mapEl.current) return
			const small = window.matchMedia('(max-width: 820px)').matches
			const q = new URLSearchParams(window.location.search)
			// the page opens a little above the place and comes down onto it, unless a still picture was asked for
			const arrive = !q.has('still') && !asFilm(q) && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
			const view = viewOf(story)
			map = new Map({
				container: mapEl.current,
				// the tiles of the stories are in the app; a tile outside them goes to its own server
				transformRequest: transformTile,
				style: {
					version: 8,
					sources: {
						// the base stops at 12: closer in, our own Sentinel-2 picture covers the place
						base: { type: 'raster', tiles: [BASE_TILES], tileSize: 256, maxzoom: maxZoomOf('base') },
						names: { type: 'raster', tiles: [NAMES_TILES], tileSize: 256, maxzoom: maxZoomOf('names') },
					},
					layers: [
						// from far out the Blue Marble shows alone (scene3d.ts): the base is not even fetched there
						{ id: 'base', type: 'raster', source: 'base', minzoom: 5.2, paint: { 'raster-saturation': -0.3, 'raster-brightness-max': 0.8 } },
						{ id: 'names', type: 'raster', source: 'names', maxzoom: NAMES_UNTIL, paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 3, 0.85, 6.6, 0.8, NAMES_UNTIL, 0] as never } },
					],
				},
				center: view.center,
				zoom: arrive ? view.zoom - 0.9 : view.zoom,
				pitch: arrive ? Math.max(0, view.pitch - 22) : view.pitch,
				bearing: arrive ? view.bearing - 16 : view.bearing,
				minZoom: 2,
				maxZoom: 16,
				maxPitch: 70,
				attributionControl: false,
			})
			mapRef.current = map
			// as soon as the style is read, not on 'load': that one waits for the base tiles of a far server
			map.once('style.load', () => {
				if (gone || !map) return
				// every file of a bake carries its time, so the browser may keep it as long as it likes
				const v = `?v=${encodeURIComponent(data.meta.baked_utc)}`
				const pictures = data.optical.scenes.map((s) => ({ key: s.day, url: `${story.root}/${s.file}${v}` }))
				// a wide feather: a tilted view would show the straight edge of the picture
				pic.current = new PictureLayer({ id: 'pic', bounds: data.optical.bounds, pictures, maxSize: small ? PICTURE_PX.phone : PICTURE_PX.desktop, feather: 0.14 })
				// the picture steps back so the layer on it is the first thing the eye lands on
				for (const sc of data.optical.scenes) pic.current.setDim(sc.day, cloud(sc) > 80 ? 0.6 : 0.72, cloud(sc) > 80 ? 0.5 : 0.7)
				pic.current.setDimmed(true)
				map.addLayer(pic.current.layer)
				const extra = data.extra
				const fade = { duration: 700, delay: 0 }
				// the official map lies under the radar layer: the layer stays crisp and the shape shows around it
				if (extra?.official) {
					map.addSource('official', { type: 'geojson', data: extra.official } as never)
					map.addLayer({ id: 'official-fill', type: 'fill', source: 'official', paint: { 'fill-color': '#ff7ac8', 'fill-opacity': 0, 'fill-opacity-transition': fade } })
					map.addLayer({ id: 'official-line', type: 'line', source: 'official', paint: { 'line-color': '#ffa3da', 'line-width': 2, 'line-opacity': 0, 'line-opacity-transition': fade } })
				}
				// the radar layer goes under this empty layer, the columns over it. It draws nothing, not even into the
				// textures of the terrain (an empty background layer would fill every one of them)
				map.addLayer(emptyLayer('over-water'))

				if (extra?.depth.features.length) {
					map.addSource('depth', { type: 'geojson', data: extra.depth } as never)
					map.addLayer({
						id: 'depth-col',
						type: 'fill-extrusion',
						source: 'depth',
						layout: { visibility: 'none' },
						paint: {
							'fill-extrusion-color': ['interpolate', ['linear'], ['get', 'm'], 0.1, '#ffe6a8', 0.8, '#ffab4a', 1.5, '#ff6a3a'],
							'fill-extrusion-height': 0,
							'fill-extrusion-opacity': 0.94,
						},
					})
				}
				for (const p of story.places) {
					const node = document.createElement('span')
					const name = document.createElement('span')
					name.className = 'st-town'
					name.textContent = p.name
					node.appendChild(name)
					new Marker({ element: node, anchor: 'center' }).setLngLat(p.at).addTo(map)
				}
				// from far out one pin says where the place is
				const pin = document.createElement('span')
				const mark = document.createElement('span')
				mark.className = 'st-pin'
				mark.textContent = story.place
				pin.appendChild(mark)
				new Marker({ element: pin, anchor: 'center' }).setLngLat(view.center).addTo(map)

				// the labels: a dot on the thing, a short line, two words
				labels.current = {}
				const list: Label[] = [...(extra?.labels ?? [])]
				if (extra?.official && !list.some((l) => l.id === 'official')) list.push({ id: 'official', at: topOf(extra.official), title: extra.official.properties.name, value: `${ha(extra.official.properties.area_ha)} ha` })
				for (const l of list) {
					const anchor = document.createElement('span')
					anchor.className = 'st-anchor'
					const box = document.createElement('span')
					box.className = 'st-label'
					box.dataset.id = l.id
					box.dataset.lean = 'ne'
					box.innerHTML = '<i></i><s></s><span><small></small><b></b></span>'
					;(box.querySelector('small') as HTMLElement).textContent = l.title
					const value = box.querySelector('b') as HTMLElement
					value.textContent = l.value
					anchor.appendChild(box)
					// MapLibre fades a marker whose point is behind a ridge: a label has to stay readable
					new Marker({ element: anchor, anchor: 'center', opacityWhenCovered: '1' }).setLngLat(l.at).addTo(map)
					labels.current[l.id] = { box, value, at: l.at }
				}
				// from far out the whole Earth shows under the base map
				addFarBase(map, 'base')
				// the ground stands up: real terrain under the picture and under our layers, a sky, the globe from far out
				if (opt.current.relief) set3d(map, true, { sky: document.documentElement.getAttribute('data-theme') === 'dark' ? 'night' : 'day' })
				map.on('move', lean)
				styled.current = true
				setMapReady(true)
			})
		})()
		return () => {
			gone = true
			styled.current = false
			map?.remove()
			mapRef.current = null
			water.current = null
			pic.current = null
			labels.current = {}
			setMapReady(false)
			setReady(false)
		}
	}, [data, story, lean])

	// keep the place in the part of the map the caption and the strip leave free
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady) return
		const fit = () => map.setPadding({ top: 30, left: 0, right: 0, bottom: window.innerWidth <= 720 ? 190 : 130 })
		fit()
		window.addEventListener('resize', fit)
		return () => window.removeEventListener('resize', fit)
	}, [mapReady])

	// the radar layer of the chosen series, under the shapes
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady || !data || !active) return
		const rgb = story.layer?.rgb
		const layer = new WaterLayer({ id: `water-${active.series.id}`, root: story.root, meta: data.meta, series: active.layerSeries, style: rgb ? { open: rgb.open, glow: rgb.glow, edge: rgb.edge, fill: rgb.fill, line: rgb.line } : undefined })
		layer.onFrame = () => layer.ready() && setReady(true)
		water.current = layer
		map.addLayer(layer.layer, 'over-water')
		const s = st.current
		s.T = Math.min(active.model.last, Math.max(active.model.first, s.T || active.model.first))
		s.shown = Number.NaN
		s.zoomFade = -1
		s.beat = -1
		return () => {
			if (map.getLayer(layer.id)) map.removeLayer(layer.id)
			if (water.current === layer) water.current = null
			setReady(false)
		}
	}, [mapReady, data, active, story])

	// ---------------------------------------------------------------- the model's map of where the water would go

	/** the handle of the rain slider, as a position over the stops: the layer mixes the two maps around it */
	const showRain = useCallback(
		(pos: number) => {
			rainPos.current = pos
			if (!rains.length) return
			const a = Math.max(0, Math.min(rains.length - 1, Math.floor(pos)))
			const b = Math.min(rains.length - 1, a + 1)
			like.current?.set(rains[a].id, rains[b].id, pos - a, rains[a].thresholds.water)
			shownMap.current = rains[Math.round(pos)]?.id ?? null
		},
		[rains],
	)

	// the layer, on the radar layer and under the shapes; it loads its first frame only when it is asked to show
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady || !pred || !map.getLayer('over-water')) return
		const frames = [...pred.scenarios, ...pred.replays].map((m) => ({ key: m.id, url: fileUrl(story.root, pred, m.file) }))
		const layer = new LikelihoodLayer({ id: 'likelihood', frames, bounds: pred.grid.bounds, size: [pred.grid.width, pred.grid.height] })
		like.current = layer
		map.addLayer(layer.layer, 'over-water')
		st.current.zoomFade = -1
		return () => {
			if (map.getLayer(layer.id)) map.removeLayer(layer.id)
			if (like.current === layer) like.current = null
		}
	}, [mapReady, pred, story])

	// the radar and the model take turns on the map
	useEffect(() => {
		const l = like.current
		if (!l || !rains.length) return
		if (mode === 'model') {
			showRain(rainPos.current)
			l.fadeTo(1, MODE_MS)
			// the other rains come in without hurry, so a sweep of the slider never waits
			l.preload(rains.map((r) => r.id))
			warmInspect(story.root, [rains[Math.round(rainPos.current)]?.id ?? ''])
		} else l.fadeTo(0, MODE_MS)
		st.current.shown = Number.NaN
		st.current.beat = -1
	}, [mode, rains, showRain, story, mapReady, pred])

	/** the readout and the caption of the model view: every number from prediction.json, which has it from the
	 *  forecast.json of the scenario (the difference to the dry scenario is the two files' own numbers subtracted) */
	const rain = mode === 'model' ? rains[rainIdx] : undefined
	useEffect(() => {
		if (!rain) return
		const e = el.current
		const put = (node: HTMLElement | null | undefined, text: string) => {
			if (node && node.textContent !== text) node.textContent = text
		}
		const dry = rains.find((s) => s.rain_mm === 0)
		put(e.date, utcDay(Date.parse(rain.target_time_utc)))
		if (e.state) {
			e.state.dataset.pass = 'false'
			put(e.state, 'Model')
		}
		put(e.num, ha(rain.area_ha.likely_water))
		const more = dry ? rain.area_ha.likely_water - dry.area_ha.likely_water : 0
		put(e.delta, !dry || rain === dry ? 'With no more rain' : more >= 0 ? `+${ha(more)} ha more than with no rain` : `${ha(-more)} ha less than with no rain`)
		say(rain.caption.line)
	}, [rain, rains, say])

	/** Read one spot of ground: the model map shown, the NISAR history of the pixel, the soil before the storm and
	 *  the land. A ring marks the spot; a newer click wins over a slower older one. */
	const spotAt = useRef<[number, number] | null>(null)
	const inspect = useCallback(
		async (lngLat: [number, number]) => {
			const map = mapRef.current
			const seq = ++spotSeq.current
			spotAt.current = lngLat
			setSpot((s) => ({ result: s?.result ?? null, loading: true, pred: s?.pred ?? null, at: lngLat }))
			if (map) {
				if (!spotMarker.current) {
					const { Marker } = await (maplibre ?? import('maplibre-gl'))
					const node = document.createElement('span')
					node.className = 'st-spot'
					spotMarker.current = new Marker({ element: node, anchor: 'center', opacityWhenCovered: '1' })
				}
				if (seq !== spotSeq.current) return
				spotMarker.current.setLngLat(lngLat).addTo(map)
			}
			const id = shownMap.current ?? rains[Math.round(rainPos.current)]?.id ?? null
			const result = await inspectAt(lngLat, id)
			const site = result.kind === 'spot' ? PREDICTION_SITES.find((s) => s.site === result.spot.site) : undefined
			const p = site ? await loadPrediction(site.root) : null
			if (seq !== spotSeq.current) return
			setSpot({ result, loading: false, pred: p, at: lngLat })
		},
		[rains],
	)
	const closeSpot = useCallback(() => {
		spotSeq.current++
		spotAt.current = null
		setSpot(null)
		spotMarker.current?.remove()
	}, [])
	// the panel follows the rain: a new stop reads the same spot again
	useEffect(() => {
		if (spotAt.current) inspect(spotAt.current)
	}, [rainIdx, mode, inspect])
	// a click on the ground; a click on a label, a pin or a town name is not one
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady || !story.predict) return
		const click = (e: MapMouseEvent) => {
			if ((e.originalEvent.target as HTMLElement | null)?.closest?.('.maplibregl-marker')) return
			inspect([e.lngLat.lng, e.lngLat.lat])
		}
		map.on('click', click)
		return () => {
			map.off('click', click)
		}
	}, [mapReady, story, inspect])
	/** fly to one of the boxes the model covers */
	const goSite = useCallback(
		(site: string) => {
			closeSpot()
			const root = PREDICTION_SITES.find((s) => s.site === site)?.root
			const to = STORIES.find((s) => s.root === root) ?? story
			mapRef.current?.flyTo({ ...viewOf(to), duration: 2600, curve: 1.4, essential: true })
		},
		[story, closeSpot],
	)

	// one loop: move the playhead while playing, redraw when anything changed
	useEffect(() => {
		if (!active) return
		const { model } = active
		// data time per millisecond: the whole series in a fixed number of seconds
		const pace = (model.last - model.first) / (PLAY_SECONDS[story.kind] * 1000)
		// but time is given to what happens and taken from the days nothing does: each stretch has its own length on screen
		const stretches: { from: number; to: number; ms: number }[] = []
		if (days.storm0 !== null && days.storm1 !== null) {
			stretches.push({ from: model.first, to: days.storm0, ms: STORM_MS.before }, { from: days.storm0, to: days.storm1, ms: STORM_MS.storm }, { from: days.storm1, to: model.last, ms: STORM_MS.after })
		} else if (days.event !== null && days.eventEnd !== null) {
			// the passes before a fire show nothing new: a short run-up, then the day it burns
			stretches.push({ from: model.first, to: days.event, ms: 1400 }, { from: days.event, to: days.eventEnd, ms: EVENT_MS })
		} else if (story.kind === 'season') {
			// a season: the months the water hardly moves go by quickly, the weeks it rises get the time
			const areas = model.times.map((_, i) => model.areaOfPass(i)[0])
			const usual = [...areas].sort((a, b) => a - b)[Math.floor(areas.length / 2)]
			let rise = areas.length - 1
			for (let i = areas.length - 1; i >= 0 && areas[i] > usual * 1.15; i--) rise = i
			const from = model.times[Math.max(0, rise - 1)]
			if (from > model.first) stretches.push({ from: model.first, to: from, ms: 2600 }, { from, to: model.last, ms: 5200 })
		}
		const rate = (T: number) => {
			const x = stretches.find((k) => T >= k.from && T < k.to)
			return x && x.to > x.from ? (x.to - x.from) / x.ms : pace
		}
		st.current.T = Math.min(model.last, Math.max(model.first, st.current.T))
		// a burn does not shimmer, and people who ask for less motion get a still surface
		const alive = story.kind !== 'fire' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
		let raf = 0
		const loop = (now: number) => {
			raf = requestAnimationFrame(loop)
			const s = st.current
			const dt = Math.min(100, now - (s.now || now))
			s.now = now
			if (s.playing) {
				if (s.dwell > 0) s.dwell -= dt
				else {
					const next = s.T + dt * rate(s.T) * speed.current
					const hit = model.times.find((t) => t > s.T + 1 && t <= next)
					if (hit !== undefined) {
						s.T = hit
						s.dwell = DWELL_MS
						water.current?.flash()
					} else s.T = next
					if (s.T >= model.last) {
						s.T = model.last
						s.playing = false
						setPlaying(false)
					}
				}
			}
			const map = mapRef.current
			// the radar layer gives way to the model's map, and back
			const goal = modeRef.current === 'radar' ? 1 : 0
			const radarWas = s.radar
			if (s.radar !== goal) s.radar = goal > s.radar ? Math.min(goal, s.radar + dt / MODE_MS) : Math.max(goal, s.radar - dt / MODE_MS)
			if (map && water.current) {
				// from far out only the coast and the pin show: the layers of the place come in on the way down
				const zf = clamp01((map.getZoom() - 9.2) / 1.5)
				if (Math.abs(zf - s.zoomFade) > 0.004 || s.radar !== radarWas) {
					s.zoomFade = zf
					water.current.setStyle({ opacity: zf * s.radar * s.radar * (3 - 2 * s.radar) })
					pic.current?.setAlpha(zf)
					like.current?.setAlpha(zf)
					mapEl.current?.parentElement?.style.setProperty('--near', String(zf))
				}
			}
			if (s.T !== s.shown) apply(s.T)
			// water is never quite still: the light on it keeps moving while the page is close. It moves slowly, so twelve
			// steps a second are smooth to the eye, and each step draws every terrain tile again (gl-quad.ts)
			if (alive && s.zoomFade > 0.5 && s.radar > 0.01 && now - s.lit > SHIMMER_MS) {
				s.lit = now
				water.current?.repaint()
			}
		}
		raf = requestAnimationFrame(loop)
		return () => cancelAnimationFrame(raf)
	}, [active, apply, story, days])

	// Once the first view is complete (its picture on screen too: on a slow line nothing may get in its way), the
	// rest of the story comes in without hurry: every pass of the series and every picture it may show, so playing
	// it, or a click on the strip, never waits for a file. A little later the first views of the other stories, so
	// the switch between them is quick.
	useEffect(() => {
		st.current.up = ready
		if (!ready || !data) return
		let id = 0
		let stop = () => {}
		const rest = () => {
			if (!pic.current?.current()) {
				id = window.setTimeout(rest, 250)
				return
			}
			water.current?.preloadAll()
			for (const s of scenesFor(opt.current.photo)) pic.current?.preload(s.day)
			id = window.setTimeout(() => {
				stop = whenIdle(() => STORIES.filter((s) => s.key !== story.key).forEach((s) => warmStory(s)), 4000)
			}, 4000)
		}
		id = window.setTimeout(rest, 500)
		return () => {
			window.clearTimeout(id)
			stop()
		}
	}, [ready, data, scenesFor, story])

	// what the buttons switch
	useEffect(() => {
		st.current.playing = playing
		const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		water.current?.setFlow(playing && !calm ? 1 : 0)
	}, [playing, ready])
	useEffect(() => {
		st.current.shown = Number.NaN
	}, [photo, official, depth, ready])
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady) return
		set3d(map, relief, { sky: document.documentElement.getAttribute('data-theme') === 'dark' ? 'night' : 'day' })
		st.current.sky = ''
		st.current.shown = Number.NaN
		// the sky follows the theme of the page
		const mo = new MutationObserver(() => {
			st.current.sky = ''
			st.current.shown = Number.NaN
		})
		mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
		return () => mo.disconnect()
	}, [relief, mapReady])
	useEffect(() => {
		water.current?.setStyle({ soft: exact ? 0 : 0.85 })
	}, [exact, ready])
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady || !map.getLayer('official-fill')) return
		map.setPaintProperty('official-fill', 'fill-opacity', official ? 0.24 : 0)
		map.setPaintProperty('official-line', 'line-opacity', official ? 0.95 : 0)
		// over terrain the ground is kept as tiles that are only drawn again when a layer of ours says so: keep saying
		// so while the shape fades in, or it stays at the first, invisible step of its fade
		const t0 = performance.now()
		let raf = 0
		const again = (now: number) => {
			water.current?.repaint()
			if (now - t0 < 1100) raf = requestAnimationFrame(again)
		}
		raf = requestAnimationFrame(again)
		return () => cancelAnimationFrame(raf)
	}, [official, mapReady])
	// the measured depths rise as columns and sink back
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady || !map.getLayer('depth-col')) return
		const from = st.current.columns
		const to = depth ? 1 : 0
		if (from === to) return
		if (to) map.setLayoutProperty('depth-col', 'visibility', 'visible')
		const t0 = performance.now()
		let raf = 0
		const grow = (now: number) => {
			const k = clamp01((now - t0) / 900)
			const e = 1 - (1 - k) ** 3
			const h = from + (to - from) * e
			st.current.columns = h
			if (map.getLayer('depth-col')) map.setPaintProperty('depth-col', 'fill-extrusion-height', ['*', ['get', 'm'], COLUMN_M * h])
			if (k < 1) raf = requestAnimationFrame(grow)
			else if (!to && map.getLayer('depth-col')) map.setLayoutProperty('depth-col', 'visibility', 'none')
		}
		raf = requestAnimationFrame(grow)
		return () => cancelAnimationFrame(raf)
	}, [depth, mapReady])

	const seek = useCallback(
		(t: number) => {
			if (!active) return
			st.current.T = Math.min(active.model.last, Math.max(active.model.first, t))
			st.current.dwell = 0
			st.current.hold = false
			st.current.beat = -1
		},
		[active],
	)

	/** the strip under the pointer: a time, snapped onto a pass when it is close to one */
	const scrub = useCallback(
		(clientX: number) => {
			if (!track.current || !active) return
			const r = track.current.getBoundingClientRect()
			const { first, last, times } = active.model
			const t = first + clamp01((clientX - r.left) / Math.max(1, r.width)) * (last - first)
			const near = times.reduce((a, b) => (Math.abs(b - t) < Math.abs(a - t) ? b : a))
			seek(Math.abs(near - t) / Math.max(1, last - first) < 9 / Math.max(1, r.width) ? near : t)
		},
		[seek, active],
	)

	const toggle = useCallback(() => {
		if (!active) return
		setPlaying((p) => {
			if (!p && st.current.T >= active.model.last - 1) seek(active.model.first)
			return !p
		})
	}, [active, seek])

	const step = useCallback(
		(dir: 1 | -1) => {
			if (!active) return
			const { times } = active.model
			const i = active.model.before(st.current.T)
			setPlaying(false)
			seek(dir > 0 ? times[Math.min(times.length - 1, i + 1)] : st.current.T > times[i] + 1 ? times[i] : times[Math.max(0, i - 1)])
		},
		[active, seek],
	)

	useEffect(() => {
		const key = (e: KeyboardEvent) => {
			if (e.code === 'Escape') {
				setMenu(false)
				setCinema(false)
				return
			}
			if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(e.target.tagName)) return
			// in the model view the arrows move the rain
			const model = modeRef.current === 'model'
			if (e.code === 'Space') {
				e.preventDefault()
				if (!model) toggle()
			} else if (e.code === 'ArrowRight') {
				if (model) setRainIdx((i) => Math.min(rains.length - 1, i + 1))
				else step(1)
			} else if (e.code === 'ArrowLeft') {
				if (model) setRainIdx((i) => Math.max(0, i - 1))
				else step(-1)
			}
		}
		window.addEventListener('keydown', key)
		return () => window.removeEventListener('keydown', key)
	}, [toggle, step, rains])

	/** The story told by itself, for the demo film: from far out onto the place in one move, the passes played, then
	 *  the official map and the measured depths as the check. */
	const tell = useCallback(async () => {
		const map = mapRef.current
		if (!map || !active || !data) return
		const { model } = active
		const s = st.current
		const done = () => {
			;(window as unknown as { __waterStoryDone?: boolean }).__waterStoryDone = true
		}
		setMenu(false)
		setOfficial(false)
		setDepth(false)
		setPhoto('clear')
		setPlaying(false)
		seek(model.first)
		// behind a veil: visit the way in once, so the flight shows sharp ground and not tiles arriving
		setVeil(true)
		s.hold = true
		say('')
		const view = viewOf(story)
		await warmUp(map, view)
		setCinema(true)
		setVeil(false)
		// 1. the Earth, and one pin on the place: the way in shows what we zoom on
		say(story.far.line)
		await wait(1100)
		// 2. one move onto the pin, the camera tilting as it comes down
		window.setTimeout(() => st.current.hold && say(story.place), 4200)
		await flyIn(map, view, { duration: 6400 })
		await wait(300)
		s.hold = false
		s.beat = -1
		s.shown = Number.NaN
		await wait(1300)
		// 3. the passes, played, while the camera drifts a little so the ground keeps its depth
		map.easeTo({ bearing: view.bearing + 16, duration: PLAY_SECONDS[story.kind] * 1000 + 6000, easing: (t) => t })
		setPlaying(true)
		await new Promise<void>((ok) => {
			const id = window.setInterval(() => {
				if (st.current.T >= model.last) {
					window.clearInterval(id)
					ok()
				}
			}, 80)
		})
		await wait(1300)
		// 4. the check: what the official map shows, and what was measured on the ground
		const shape = data.extra?.official
		const cover = data.extra?.landcover?.[0]
		const all = data.extra?.landcover?.reduce((a, c) => a + c.ha, 0) ?? 0
		// what the new ground was before, when one kind of land clearly leads (not for the rice fields: the land cover map calls them wetland)
		if (cover && all > 0 && cover.ha / all > 0.6 && story.kind !== 'season') {
			const land = ({ Cropland: 'farmland', 'Tree cover': 'forest' } as Record<string, string>)[cover.name] ?? cover.name.toLowerCase()
			s.hold = true
			say(story.kind === 'fire' ? `Most of the burn was ${land}: ${ha(cover.ha)} ha` : `Most of the new water lies on ${land}: ${ha(cover.ha)} ha`)
			await wait(2300)
		}
		if (shape) {
			s.hold = true
			setOfficial(true)
			say(`${shape.properties.name}: ${ha(shape.properties.area_ha)} ha`)
			await wait(2300)
			const inside = data.extra?.inside_official
			if (inside) {
				say(`${Math.round(inside.share * 100)} % of what the radar found lies inside it`)
				await wait(2300)
			}
		}
		const deepest = data.extra?.labels.find((l) => l.id === 'deepest')
		if (deepest && data.extra?.depth.features.length) {
			s.hold = true
			setDepth(true)
			say(`Measured on the ground: up to ${deepest.value} deep`)
			await wait(2800)
		}
		await wait(600)
		done()
	}, [active, data, seek, story, say])

	// a small handle on the page for the still shots and the film recording (scripts/shoot_flood.py, record_flood.py)
	useEffect(() => {
		if (!data || !active) return
		const api = {
			times: active.model.times.map((t) => new Date(t).toISOString()),
			current: active.series.id,
			series: (id: string) => setSeriesId(id),
			seek: (when: string | number) => {
				seek(typeof when === 'string' ? Date.parse(when) : when)
				setPlaying(false)
			},
			play: () => setPlaying(true),
			pause: () => setPlaying(false),
			photo: (mode: Photo) => setPhoto(mode),
			official: (on: boolean) => setOfficial(on),
			depth: (on: boolean) => setDepth(on),
			exact: (on: boolean) => setExact(on),
			relief: (on: boolean) => setRelief(on),
			cinema: (on: boolean) => setCinema(on),
			menu: (on: boolean) => setMenu(on),
			say: (text: string) => {
				st.current.hold = true
				say(text)
			},
			story: tell,
			home: () => {
				mapRef.current?.stop()
				mapRef.current?.jumpTo(viewOf(story))
			},
			far: () => mapRef.current?.jumpTo({ ...farView(viewOf(story)), pitch: 0, bearing: 0 }),
			view: (to: Partial<Story['view']>, ms = 0) => {
				if (ms > 0) mapRef.current?.flyTo({ ...to, duration: ms, curve: 1.3, essential: true })
				else mapRef.current?.jumpTo(to)
			},
			map: () => mapRef.current,
			settled: () => !!water.current?.ready() && !!pic.current?.current() && !!mapRef.current?.loaded() && !mapRef.current?.isMoving(),
			/** everything this moment needs has arrived (tiles, radar frames, picture), also while the camera moves: the
			 *  films are made frame by frame on this (scripts/record_flood.py --steady) */
			complete: () => !!water.current?.ready() && !!pic.current?.current() && !!mapRef.current?.areTilesLoaded(),
			/** tiles served by the app and tiles that had to go to their own server */
			tiles: () => ({ ...tileCount }),
			/** the model view: 'radar' or 'model', the stop of the rain slider (0 is the driest), a click on a spot */
			mode: (m: Mode) => chooseMode(m),
			rain: (i: number) => setRainIdx(i),
			inspect: (lng: number, lat: number) => inspect([lng, lat]),
			/** the model layer has its frames on the card and has drawn */
			modelReady: () => !!like.current?.ready(),
		}
		const host = window as unknown as { __flood?: typeof api }
		host.__flood = api
		return () => {
			delete host.__flood
		}
	}, [data, active, seek, tell, say, inspect, chooseMode])

	// once the page is ready it plays by itself: ?story plays the film, otherwise the passes run once
	const told = useRef(false)
	useEffect(() => {
		if (!ready || told.current) return
		told.current = true
		const q = new URLSearchParams(window.location.search)
		if (asFilm(q)) {
			tell()
			return
		}
		// people who ask for less motion, and scripts that take stills (?still), get a still picture
		if (q.has('still') || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
		// come down onto the place, then play
		mapRef.current?.easeTo({ ...viewOf(story), duration: 2800, easing: (t) => 1 - (1 - t) ** 3 })
		const id = window.setTimeout(() => setPlaying(true), 2400)
		return () => window.clearTimeout(id)
	}, [ready, tell, story])

	const drag = useCallback(
		(e: React.PointerEvent<HTMLDivElement>) => {
			setPlaying(false)
			scrub(e.clientX)
			const move = (ev: PointerEvent) => scrub(ev.clientX)
			const up = () => {
				window.removeEventListener('pointermove', move)
				window.removeEventListener('pointerup', up)
			}
			window.addEventListener('pointermove', move)
			window.addEventListener('pointerup', up)
			e.preventDefault()
		},
		[scrub],
	)

	const set = (name: string) => (node: HTMLElement | null) => {
		el.current[name] = node
	}
	const model = active?.model
	const at = (t: number) => (model ? `${(clamp01((t - model.first) / Math.max(1, model.last - model.first)) * 100).toFixed(3)}%` : '0%')
	// the one thing that happened, on the strip: the storm as a band, the fire as a tick
	const band = model && days.storm0 !== null && days.storm1 !== null ? { from: days.storm0, to: days.storm1, name: 'storm' } : model && days.event !== null ? { from: days.event, to: days.eventEnd ?? days.event, name: story.event?.label ?? '' } : null
	const hasDepth = !!data?.extra?.depth.features.length

	return (
		<div className="st" data-kind={story.kind} data-mode={mode} data-ready={ready || undefined} data-cinema={cinema || undefined} data-veil={veil || undefined}>
			<div ref={mapEl} className="st-map" />
			{story.storm && <div ref={set('rain')} className="st-rain" aria-hidden />}

			<header className="st-top">
				<Link href="/" className="st-brand">
					Dancing with the SARs
				</Link>
				<nav className="st-tabs" aria-label="Stories">
					{STORIES.map((s) => (
						<Link key={s.key} href={s.path} aria-current={s.key === story.key ? 'page' : undefined}>
							{s.tab}
						</Link>
					))}
				</nav>
				<h1 className="display st-title">{story.title}</h1>
				<p className="st-place">{story.place}</p>
			</header>

			<section className="st-read" aria-live="off">
				<p className="st-when">
					<span ref={set('date')} className="mono">
						&nbsp;
					</span>
					<i ref={set('state')} className="st-state" data-pass="true" />
				</p>
				<p className="st-big">
					<b ref={set('num')} className="display">
						0
					</b>
					<span>{mode === 'model' ? 'ha likely under water' : active?.twoClass ? 'ha of open water' : story.unit}</span>
				</p>
				<p ref={set('delta')} className="st-delta" />
			</section>

			<footer className="st-bottom">
				{rains.length > 0 && (
					<div className="st-mode" role="group" aria-label="What the map shows">
						<button type="button" aria-pressed={mode === 'radar'} onClick={() => chooseMode('radar')}>
							Radar passes
						</button>
						<button type="button" aria-pressed={mode === 'model'} onClick={() => chooseMode('model')}>
							What if it rains
						</button>
					</div>
				)}
				<p ref={set('caption')} className="st-caption" />
				{rain && (
					<div className="st-note">
						<span className="st-key">
							<i className="st-ramp" /> less to more likely
						</span>
						<span className="st-key">
							<i className="st-dash" /> likely water
						</span>
						<span className="st-why">{rain.caption.note}</span>
						{rain.caption.warning && <span className="st-warn">{rain.caption.warning}</span>}
					</div>
				)}
				{mode === 'model' && rains.length > 0 && (
					<div className="st-strip st-rainstrip">
						<RainSlider stops={rains.map((r) => ({ label: `${r.rain_mm} mm`, warn: !!r.caption.warning }))} index={rainIdx} onInput={showRain} onStop={setRainIdx} label={`Rain in ${Math.round(rains[rainIdx]?.lead_days ?? 0)} days`} />
					</div>
				)}
				<div className="st-strip st-timestrip">
					<button type="button" className="st-play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'} disabled={!ready}>
						{playing ? <Pause size={18} strokeWidth={2.4} /> : <Play size={18} strokeWidth={2.4} />}
					</button>
					<div ref={track} className="st-track" onPointerDown={drag} role="slider" aria-label="Date" aria-valuemin={0} aria-valuemax={100} aria-valuenow={0} tabIndex={0}>
						<i className="st-rail" />
						{band && model && band.to > model.first && band.from < model.last && (
							<i className="st-band" style={{ left: at(band.from), width: `max(3px, calc(${at(band.to)} - ${at(band.from)}))` }}>
								<small>{band.name}</small>
							</i>
						)}
						{model?.times.map((t) => (
							<i key={t} className="st-pass" style={{ left: at(t) }} />
						))}
						<div ref={head} className="st-head">
							<b ref={set('tag')} className="mono" />
						</div>
						{model && (
							<>
								<small className="st-end" data-side="left">
									{utcDay(model.first, false)}
								</small>
								<small className="st-end" data-side="right">
									{utcDay(model.last, false)}
								</small>
							</>
						)}
					</div>
				</div>
			</footer>

			<div className="st-menu">
				{menu && (
					<div className="st-pop" role="dialog" aria-label="Layers">
						{choices.length > 1 && (
							<div className="st-row">
								<span>Radar</span>
								<div className="st-seg">
									{choices.map((s) => (
										<button key={s.id} type="button" aria-pressed={active?.series.id === s.id} onClick={() => setSeriesId(s.id)}>
											{s.sensor}
										</button>
									))}
								</div>
							</div>
						)}
						{data?.extra?.official && <Toggle label={data.extra.official.properties.name} on={official} set={setOfficial} />}
						{hasDepth && <Toggle label="Measured depth" on={depth} set={setDepth} />}
						<Toggle label="Exact pixels" on={exact} set={setExact} />
						<Toggle label="3D terrain" on={relief} set={setRelief} />
						<div className="st-row">
							<span>Photo</span>
							<div className="st-seg">
								<button type="button" aria-pressed={photo === 'clear'} onClick={() => setPhoto('clear')}>
									Clear
								</button>
								<button type="button" aria-pressed={photo === 'day'} onClick={() => setPhoto('day')}>
									Same day
								</button>
							</div>
						</div>
						<div className="st-row">
							<span>Theme</span>
							<ThemeSwitch />
						</div>
						<div className="st-row st-acts">
							<button type="button" onClick={tell}>
								Play the film
							</button>
							<button type="button" aria-expanded={credits} onClick={() => setCredits((v) => !v)}>
								Sources
							</button>
						</div>
						{credits && (
							<ul className="st-sources">
								{[...story.credits, { what: 'From far out', who: FAR_BASE.credit }, ...(relief ? [{ what: 'Terrain', who: TERRAIN.credit }] : [])].map((c) => (
									<li key={c.what}>
										<b>{c.what}</b> {c.who}
									</li>
								))}
							</ul>
						)}
					</div>
				)}
				<button type="button" className="st-layers" aria-expanded={menu} onClick={() => setMenu((v) => !v)}>
					<Layers size={16} strokeWidth={2.2} /> Layers
				</button>
			</div>

			<SpotPanel result={spot?.result ?? null} loading={!!spot?.loading} prediction={spot?.pred ?? null} onClose={closeSpot} onGo={goSite} />

			<p className="st-credit">
				<span ref={set('pic')} /> {story.credit} · From far out: NASA Blue Marble
				{relief ? ` · ${TERRAIN.creditShort}` : ''}
			</p>
			{error && <p className="st-error">The layers did not load: {error}</p>}
		</div>
	)
}
