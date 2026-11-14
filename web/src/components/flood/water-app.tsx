'use client'

import 'maplibre-gl/dist/maplibre-gl.css'
import { Columns2, Globe2, Pause, Play } from 'lucide-react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import Link from 'next/link'
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Story } from '@/content/stories'
import { type FloodModel, PLATFORMS, type RainFile, floodModel, utcClock, utcDay } from '@/lib/flood-model'
import type { Bounds } from '@/lib/gl-quad'
import { PictureLayer } from '@/lib/picture-layer'
import { WaterLayer, type WaterMeta, type WaterSeries } from '@/lib/water-layer'
import { ThemeSwitch } from '../theme-switch'
import './flood.css'

type Scene = { day: string; file: string; time_utc: string; platform: string; cloud_pct?: number; scenes: { id: string; tile: string; cloud_pct: number }[] }
type Optical = { bounds: Bounds; credit: string; scenes: Scene[] }
type Outline = { title: string; when?: string; credit: string; features: unknown[] }
type Outlines = { ems: Outline; generalitat: Outline; depth: Outline }
type Data = { meta: WaterMeta; rain: RainFile | null; optical: Optical; outlines: Outlines | null }
/** the days of a story as numbers */
type Days = { t0: number; t1: number; storm0: number | null; storm1: number | null; ems0: number | null; ems1: number | null }
/** one radar series cut to the days of the story, with its clock and what "new" water is measured against */
type Active = {
	series: WaterSeries
	/** the series as the layer loads it: the passes, then the frame of the water that is always there */
	layerSeries: WaterSeries
	model: FloodModel
	nisar: boolean
	twoClass: boolean
	/** frame of the layer the picture is compared with, -1 for none */
	ref: number
	/** the reference only counts after this moment */
	refFrom: number
	/** hectares of water in the reference */
	refHa: number
	/** true when the reference is the water every pass has, false when it is the last pass before the storm */
	refAlways: boolean
}

const HOUR = 3600e3
const DAY = 24 * HOUR
const BASE_TILES = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2017_3857/default/g/{z}/{y}/{x}.jpg'
/** coast lines, borders and place names, shown only from far out so the picture from space can be read */
const NAMES_TILES = 'https://tiles.maps.eox.at/wmts/1.0.0/overlay_bright_3857/default/g/{z}/{y}/{x}.png'
/** the hold on every pass while playing, and how long a whole story takes to play */
const DWELL_MS = 320
const PLAY_SECONDS = { storm: 23, season: 16 }
const X_PAD = 16
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const ha = (x: number) => Math.round(x).toLocaleString('en-US')
const frameTime = (f: { time_utc?: string; date?: string }) => Date.parse(f.time_utc ?? `${f.date}T12:00:00Z`)
/** the cloud share of a picture: that of the Sentinel-2 scene that fills most of it */
const cloud = (s: Scene) => s.cloud_pct ?? Math.max(...s.scenes.map((x) => x.cloud_pct))

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
		Promise.all([get('meta.json'), get('optical.json'), story.storm ? get('rain.json') : null, story.ems ? get('outlines.json') : null])
			.then(([meta, optical, rain, outlines]: [WaterMeta, Optical, RainFile | null, Outlines | null]) => !gone && setData({ meta, rain, optical, outlines }))
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

/** The time axis of the page: rain on top, the water the picture shows as an area, every pass as a mark. */
const Timeline = memo(function Timeline({ story, days, data, active, others, w }: { story: Story; days: Days; data: Data; active: Active; others: number[]; w: number }) {
	const { model, twoClass, nisar, series } = active
	const { t0, t1 } = days
	const H = 116
	const X = (t: number) => X_PAD + ((t - t0) / (t1 - t0)) * (w - 2 * X_PAD)
	const hourW = Math.max(1, X(t0 + HOUR) - X(t0))
	const long = t1 - t0 > 60 * DAY

	const maxMm = Math.max(1, ...model.rainMm)
	const bars = model.rainT.map((t, i) => ({ t, mm: model.rainMm[i] })).filter((b) => b.mm > 0.05 && b.t > t0 && b.t <= t1)

	// what the picture shows, sampled through every gap with the same timing the animation uses
	const pts: { t: number; open: number; veg: number }[] = []
	for (let i = 0; i < model.times.length - 1; i++) {
		const steps = Math.max(2, Math.round((X(model.times[i + 1]) - X(model.times[i])) / 3))
		for (let k = 0; k < steps; k++) {
			const t = model.times[i] + ((model.times[i + 1] - model.times[i]) * k) / steps
			const [open, veg] = model.areaAt(t)
			pts.push({ t, open, veg })
		}
	}
	const end = model.areaAt(model.last)
	pts.push({ t: model.last, open: end[0], veg: end[1] })
	const top = Math.max(...pts.map((p) => p.open + p.veg))
	const unit = top > 2000 ? 1000 : 200
	const yMax = Math.max(unit, Math.ceil(top / unit) * unit)
	const Y0 = 88
	const Y = (v: number) => Y0 - (v / yMax) * 42
	const line = (f: (p: (typeof pts)[number]) => number) => pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(f(p)).toFixed(1)}`).join('')
	const area = (f: (p: (typeof pts)[number]) => number) => `${line(f)}L${X(model.last).toFixed(1)},${Y0}L${X(model.first).toFixed(1)},${Y0}Z`

	// day marks: every day on a short axis, the 1st and the 15th of each month on a long one
	const marks: { t: number; label: boolean }[] = []
	const every = w > 1100 ? 2 : w > 700 ? 3 : 6
	for (let d = Math.ceil(t0 / DAY) * DAY, i = 0; d <= t1; d += DAY, i++) {
		const dom = new Date(d).getUTCDate()
		if (long) {
			if (dom === 1 || dom === 15) marks.push({ t: d, label: true })
		} else marks.push({ t: d, label: i % every === 0 })
	}
	const nisarMarks = [...(nisar ? model.times : []), ...story.otherNisar.map((n) => Date.parse(n.t))]
	const quiet = model.last + 2 * DAY < t1 && !long

	return (
		<svg className="fl-tl" width={w} height={H} viewBox={`0 0 ${w} ${H}`} aria-hidden>
			<defs>
				<pattern id="fl-nopass" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
					<line className="fl-tl-nopass" x1="0" y1="0" x2="0" y2="7" />
				</pattern>
			</defs>
			{/* rain, hanging from the top like a rain gauge chart */}
			{bars.map((b) => (
				<rect key={b.t} className="fl-tl-rain" x={X(b.t - HOUR)} y={0} width={hourW} height={Math.max(1, (b.mm / maxMm) * 28)} />
			))}
			{days.storm1 !== null && bars.length > 0 && (
				<text className="fl-tl-note" x={X(days.storm1 + 6 * HOUR)} y={11} textAnchor="start">
					rain, up to {Math.round(maxMm)} mm an hour (weather model)
				</text>
			)}

			<line className="fl-tl-grid" x1={X_PAD} x2={w - X_PAD} y1={Y(yMax)} y2={Y(yMax)} />
			<text className="fl-tl-note" x={w - X_PAD} y={Y(yMax) - 4} textAnchor="end">
				{ha(yMax)} ha
			</text>
			{active.refAlways && active.refHa > 0 && (
				<>
					<line className="fl-tl-always" x1={X(model.first)} x2={X(model.last)} y1={Y(active.refHa)} y2={Y(active.refHa)} />
					<text className="fl-tl-note" x={X(model.first) + 4} y={Y(active.refHa) + 12} textAnchor="start">
						always there, {ha(active.refHa)} ha
					</text>
				</>
			)}
			{quiet && (
				<>
					<rect x={X(model.last)} y={Y(yMax)} width={X(t1) - X(model.last)} height={Y0 - Y(yMax)} fill="url(#fl-nopass)" />
					<text className="fl-tl-note" x={(X(model.last) + X(t1)) / 2} y={Y0 - 16} textAnchor="middle">
						no {series.sensor} layer after {utcDay(model.last, false)} yet
					</text>
				</>
			)}
			{twoClass && <path className="fl-tl-veg" d={area((p) => p.open + p.veg)} />}
			<path className="fl-tl-open" d={area((p) => p.open)} />
			<path className="fl-tl-line" d={line((p) => p.open)} />
			{model.times.map((t, i) => (
				<circle key={t} className="fl-tl-pass" cx={X(t)} cy={Y(model.areaOfPass(i)[0])} r={3} />
			))}

			{/* the Copernicus EMS mapping days and the days a Sentinel-2 picture exists */}
			{days.ems0 !== null && days.ems1 !== null && <line className="fl-tl-ems" x1={X(days.ems0)} x2={X(days.ems1)} y1={36} y2={36} />}
			{data.optical.scenes
				.filter((s) => Date.parse(s.time_utc) >= t0)
				.map((s) => (
					<rect key={s.day} className="fl-tl-pic" data-cloud={cloud(s) > 80 || undefined} x={X(Date.parse(s.time_utc)) - 3.5} y={32.5} width={7} height={7} rx={1.5} />
				))}

			<line className="fl-tl-axis" x1={X_PAD} x2={w - X_PAD} y1={Y0} y2={Y0} />
			{others.map((t) => (
				<circle key={t} className="fl-tl-other" cx={X(t)} cy={Y0 + 7.5} r={1.8} />
			))}
			{nisarMarks.map((t) => {
				const x = X(t)
				return <path key={t} className="fl-tl-nisar" d={`M${x},${Y0 + 3}l4.2,4.6l-4.2,4.6l-4.2,-4.6z`} />
			})}
			{marks.map((m) => (
				<g key={m.t}>
					<line className="fl-tl-tick" x1={X(m.t)} x2={X(m.t)} y1={Y0} y2={Y0 + (m.label ? 5 : 3)} />
					{m.label && (
						<text className="fl-tl-day" x={X(m.t)} y={H - 3} textAnchor="middle">
							{utcDay(m.t, false)}
						</text>
					)}
				</g>
			))}
		</svg>
	)
})

export function WaterApp({ story }: { story: Story }) {
	const { data, error } = useData(story)
	const mapEl = useRef<HTMLDivElement>(null)
	const mapRef = useRef<MapLibreMap | null>(null)
	const water = useRef<WaterLayer | null>(null)
	const pic = useRef<PictureLayer | null>(null)
	const picBefore = useRef<PictureLayer | null>(null)
	const tlBox = useRef<HTMLDivElement>(null)
	const dock = useRef<HTMLElement>(null)
	const head = useRef<HTMLDivElement>(null)
	const swipe = useRef<HTMLDivElement>(null)
	const el = useRef<Record<string, HTMLElement | null>>({})
	const st = useRef({ T: 0, playing: false, dwell: 0, now: 0, shown: Number.NaN, beat: -1, zoomFade: -1, split: 0.5, outl: '', tone: '' })
	const speed = useRef(1)

	const [mapReady, setMapReady] = useState(false)
	const [ready, setReady] = useState(false)
	const [playing, setPlaying] = useState(false)
	const [seriesId, setSeriesId] = useState<string | null>(null)
	const [optical, setOptical] = useState<string>('auto')
	const [showWater, setShowWater] = useState(true)
	const [showOutlines, setShowOutlines] = useState(true)
	const [compare, setCompare] = useState(false)
	const [far, setFar] = useState(false)
	const [exact, setExact] = useState(false)
	const [credits, setCredits] = useState(false)
	const [cinema, setCinema] = useState(false)
	const [w, setW] = useState(0)
	const opt = useRef({ optical, showWater, showOutlines, compare })
	opt.current = { optical, showWater, showOutlines, compare }

	const days = useMemo<Days>(
		() => ({
			t0: Date.parse(story.window.from),
			t1: Date.parse(story.window.to),
			storm0: story.storm ? Date.parse(story.storm.from) : null,
			storm1: story.storm ? Date.parse(story.storm.to) : null,
			ems0: story.ems ? Date.parse(story.ems.from) : null,
			ems1: story.ems ? Date.parse(story.ems.to) : null,
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
		const model = floodModel(series, data.rain)
		const base = { series, layerSeries: series, model, nisar: series.sensor === 'NISAR', twoClass: series.frames.some((f) => f.veg_ha > 0) }
		// a storm is measured against the last pass before the rain
		if (days.storm0 !== null && model.times[0] < days.storm0) {
			const ref = model.before(days.storm0)
			return { ...base, ref, refFrom: model.times[ref] + 60e3, refHa: model.areaOfPass(ref)[0], refAlways: false }
		}
		// a season is measured against the water every pass has: one more frame after the passes
		if (story.kind === 'season' && series.always) {
			const frames = [...series.frames, { file: series.always.file, granules: [], open_ha: series.always.water_ha, veg_ha: 0, seen: 1 }]
			return { ...base, layerSeries: { ...series, frames }, ref: frames.length - 1, refFrom: -Infinity, refHa: series.always.water_ha, refAlways: true }
		}
		return { ...base, ref: -1, refFrom: Infinity, refHa: 0, refAlways: false }
	}, [data, choices, seriesId, days, story])
	const others = useMemo(() => {
		if (!data || !active) return []
		return data.meta.series.filter((s) => s.sensor !== active.series.sensor && s.sensor !== 'NISAR').flatMap((s) => inWindow(s, days).frames.map(frameTime))
	}, [data, active, days])

	// the story in a few lines, every number read from the baked files
	const beats = useMemo(() => {
		if (!data || !active) return []
		const { model, series, nisar, twoClass, ref } = active
		const last = series.frames.length - 1
		const what = twoClass ? 'open water' : 'water'
		const sees = nisar ? 'NISAR sees' : 'Sentinel-1 sees'
		if (story.kind === 'season') {
			const areas = series.frames.map((_, i) => model.areaOfPass(i)[0])
			const usual = [...areas].sort((a, b) => a - b)[Math.floor(areas.length / 2)]
			const high = areas.indexOf(Math.max(...areas))
			// the first pass from which the water stays well above its usual level
			let rise = areas.length
			for (let i = areas.length - 1; i >= 0 && areas[i] > usual * 1.15; i--) rise = i
			const early = (i: number) => model.times[i] - (model.times[i] - model.times[i - 1]) * 0.45
			const list = [{ from: model.first, text: `${utcDay(model.first, false)}. ${sees} ${ha(areas[0])} ha of ${what}. ${ha(active.refHa)} ha of it is there on every pass: the lagoon.` }]
			if (areas.length > 2) list.push({ from: early(1), text: `Pass after pass the map hardly moves: around ${ha(usual)} ha, little more than the lagoon.` })
			if (rise > 1 && rise < areas.length) list.push({ from: early(rise), text: `${utcDay(model.times[rise], false)}: the paddies start to fill, ${ha(areas[rise])} ha.` })
			if (high > rise) list.push({ from: early(high), text: `${utcDay(model.times[high], false)}: ${ha(areas[high])} ha, ${(areas[high] / usual).toFixed(1)} times the usual water. Rice fields are flooded on purpose: farm water, not storm water.` })
			return list
		}
		const afterI = Math.min(last, Math.max(0, ref) + 1)
		const before = model.areaOfPass(Math.max(0, ref))
		const after = model.areaOfPass(afterI)
		const final = model.areaOfPass(last)
		const rain = data.rain && days.storm0 !== null && days.storm1 !== null ? data.rain.hours.filter((h) => Date.parse(h.t) > days.storm0! && Date.parse(h.t) <= days.storm1!).reduce((a, h) => a + h.mm, 0) : 0
		const times = Math.round(after[0] / Math.max(1, before[0]))
		const usual = twoClass ? `${ha(before[0])} ha open, ${ha(before[1])} ha under plants` : `${ha(before[0])} ha`
		const list = [{ from: model.first, text: `Before the storm. ${sees} the usual water of the marsh: ${usual}.` }]
		if (days.storm0 !== null) list.push({ from: days.storm0, text: `${story.title}. The weather model puts ${ha(rain)} mm of rain here in two days. The optical satellite sees only cloud.` })
		if (days.ems0 !== null && data.outlines) {
			const emsHa = (data.outlines.ems.features[0] as { properties: { area_ha: number } }).properties.area_ha
			list.push({ from: days.ems0, text: `Copernicus EMS maps ${ha(emsHa)} ha of flood from other satellites. No ${series.sensor} pass has come by yet.` })
		}
		list.push({ from: model.times[afterI] - 3 * HOUR, text: `${utcDay(model.times[afterI], false)}, first ${series.sensor} pass after the storm: ${ha(after[0])} ha of ${what}, ${times} times as much as before.` })
		if (last > afterI && days.storm1 !== null) {
			const weeks = Math.round((model.last - days.storm1) / (7 * DAY))
			list.push({ from: model.times[afterI] + 30 * HOUR, text: 'Radar keeps passing, cloud or not. The water gives ground slowly.' })
			list.push({ from: model.last - 4 * DAY, text: `${weeks} weeks on, ${ha(final[0])} ha are still ${what}.` })
		}
		return list
	}, [data, active, story, days])

	const X = useCallback((t: number) => X_PAD + ((t - days.t0) / (days.t1 - days.t0)) * (w - 2 * X_PAD), [w, days])

	/** draw one moment: the map layers, the readout, the playhead */
	const apply = useCallback(
		(T: number) => {
			if (!data || !active) return
			const s = st.current
			const { model, series, ref, twoClass } = active
			const v = model.viewAt(T)
			const hasRef = ref >= 0 && T > active.refFrom
			water.current?.set({ a: v.a, b: v.b, gain: v.gain, loss: v.loss, observed: v.observed, ref: hasRef ? ref : -1 })
			water.current?.want(v.b + 1)

			// the newest real picture at this moment, unless a day is pinned
			const scenes = data.optical.scenes
			let key = opt.current.optical
			if (key === 'auto') key = (scenes.filter((x) => Date.parse(x.time_utc) <= T).pop() ?? scenes[0]).day
			const shownScene = scenes.find((x) => x.day === key)
			pic.current?.show(key)
			// under radar water the picture steps back a little, so the water reads
			const tone = opt.current.showWater ? '1' : '0'
			if (tone !== s.tone) {
				s.tone = tone
				pic.current?.setDimmed(opt.current.showWater)
			}

			const map = mapRef.current
			if (days.ems0 !== null && days.storm0 !== null) {
				const outl = `${opt.current.showOutlines && T >= days.ems0 ? 1 : 0}${opt.current.showOutlines && T >= days.storm0 + DAY ? 1 : 0}`
				if (outl !== s.outl && map?.getLayer('ems-line')) {
					s.outl = outl
					map.setPaintProperty('ems-line', 'line-opacity', outl[0] === '1' ? 1 : 0)
					map.setPaintProperty('ems-case', 'line-opacity', outl[0] === '1' ? 0.5 : 0)
					map.setPaintProperty('gva-line', 'line-opacity', outl[1] === '1' ? 0.95 : 0)
					map.setPaintProperty('gva-case', 'line-opacity', outl[1] === '1' ? 0.45 : 0)
					map.setPaintProperty('depth', 'circle-opacity', outl[1] === '1' ? 1 : 0)
					map.setPaintProperty('depth', 'circle-stroke-opacity', outl[1] === '1' ? 1 : 0)
				}
			}

			const e = el.current
			const [open, veg] = model.areaAt(T)
			const frame = v.pass !== null ? series.frames[v.pass] : null
			const put = (node: HTMLElement | null | undefined, text: string) => {
				if (node && node.textContent !== text) node.textContent = text
			}
			put(e.date, utcDay(T))
			put(e.clock, utcClock(T))
			put(e.open, ha(open))
			put(e.veg, ha(veg))
			if (e.chip) {
				e.chip.dataset.state = frame ? 'pass' : 'between'
				put(e.chip, frame ? `${PLATFORMS[frame.platform ?? ''] ?? series.sensor} radar pass` : 'Between passes, an estimate')
			}
			put(
				e.seen,
				frame && frame.seen < 0.98 ? `This pass saw ${Math.round(frame.seen * 100)} % of the site` : !frame && v.storm ? (v.loss > 0 ? 'Rain over: the shoreline settles towards the next pass' : 'The shoreline rises with the rain') : '',
			)
			const word = twoClass ? 'open water' : 'water'
			if (active.refAlways) put(e.delta, `${ha(Math.max(0, open - active.refHa))} ha more than the ${ha(active.refHa)} ha that are always there`)
			else if (hasRef) {
				const d = open - active.refHa
				put(e.delta, `${d >= 0 ? '+' : ''}${ha(d)} ha of ${word} since ${utcDay(model.times[ref], false)}`)
			} else put(e.delta, story.kind === 'storm' ? 'The usual water of the marsh' : '')
			if (shownScene) {
				const c = cloud(shownScene)
				const text = `Sentinel-2 picture of ${utcDay(Date.parse(shownScene.time_utc), false)}, ${c >= 99.5 ? '100' : c.toFixed(0)} % cloud`
				put(e.pic, text)
				put(e.picchip, text)
				if (e.picchip) e.picchip.dataset.cloudy = c > 80 ? 'true' : 'false'
			}
			let beat = 0
			for (let i = 0; i < beats.length; i++) if (T >= beats[i].from) beat = i
			if (beat !== s.beat && e.caption) {
				s.beat = beat
				e.caption.textContent = beats[beat]?.text ?? ''
				e.caption.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 420, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' })
			}
			// rain falls on the picture when the weather model says it rains, harder when it rains harder
			if (e.rain) e.rain.style.opacity = String(Math.min(0.85, model.rainAt(T) / 14))
			const x = X(T)
			if (head.current) head.current.style.transform = `translate3d(${x}px, 0, 0)`
			if (e.tag) {
				put(e.tag, utcDay(T, false))
				e.tag.style.transform = x < 44 ? 'translateX(-14px)' : x > w - 44 ? 'translateX(calc(-100% + 14px))' : 'translateX(-50%)'
			}
			s.shown = T
		},
		[data, active, beats, X, w, days, story],
	)

	// the map, the pictures and the outlines
	useEffect(() => {
		if (!data || !mapEl.current) return
		let map: MapLibreMap | null = null
		let gone = false
		;(async () => {
			const { Map, Marker, Popup, setWorkerUrl } = await import('maplibre-gl')
			setWorkerUrl('/maplibre/maplibre-gl-worker.mjs')
			if (gone || !mapEl.current) return
			const far0 = ['interpolate', ['linear'], ['zoom'], 7.8, 1, 9.6, 0] as never
			map = new Map({
				container: mapEl.current,
				style: {
					version: 8,
					sources: {
						base: { type: 'raster', tiles: [BASE_TILES], tileSize: 256, maxzoom: 14 },
						...(story.space ? { space: { type: 'raster', tiles: [story.space.tiles], tileSize: 256, maxzoom: 9 }, names: { type: 'raster', tiles: [NAMES_TILES], tileSize: 256, maxzoom: 12 } } : {}),
					},
					layers: [
						{ id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.78 } },
						...(story.space
							? ([
									{ id: 'space', type: 'raster', source: 'space', paint: { 'raster-opacity': far0, 'raster-fade-duration': 0 } },
									{ id: 'names', type: 'raster', source: 'names', paint: { 'raster-opacity': far0 } },
								] as never[])
							: []),
					],
				},
				center: story.camera.center,
				zoom: story.camera.zoom,
				minZoom: story.space ? 4.5 : 8.8,
				maxZoom: 16,
				dragRotate: false,
				pitchWithRotate: false,
				attributionControl: false,
			})
			map.touchZoomRotate.disableRotation()
			mapRef.current = map
			map.on('load', () => {
				if (gone || !map) return
				const pictures = data.optical.scenes.map((s) => ({ key: s.day, url: `${story.root}/${s.file}` }))
				const small = window.matchMedia('(max-width: 820px)').matches
				picBefore.current = new PictureLayer({ id: 'pic-before', bounds: data.optical.bounds, pictures, maxSize: small ? 2048 : 4096 })
				pic.current = new PictureLayer({ id: 'pic', bounds: data.optical.bounds, pictures, maxSize: small ? 2048 : 4096 })
				picBefore.current.setTone(1, 0.96)
				// a sky full of cloud steps back more than a clear picture
				for (const sc of data.optical.scenes) pic.current.setDim(sc.day, cloud(sc) > 80 ? 0.7 : 0.88, cloud(sc) > 80 ? 0.56 : 0.84)
				map.addLayer(pic.current.layer)
				map.addLayer(picBefore.current.layer)
				// the water layers go under this empty layer, the reference lines over it
				map.addLayer({ id: 'over-water', type: 'background', paint: { 'background-opacity': 0 } })

				if (data.outlines) {
					const fc = (features: unknown[]) => ({ type: 'geojson', data: { type: 'FeatureCollection', features } }) as never
					map.addSource('ems', fc(data.outlines.ems.features))
					map.addSource('gva', fc(data.outlines.generalitat.features))
					map.addSource('depth', fc(data.outlines.depth.features))
					const fade = { duration: 700, delay: 0 }
					map.addLayer({ id: 'gva-case', type: 'line', source: 'gva', paint: { 'line-color': '#1b1203', 'line-width': 3, 'line-opacity': 0, 'line-opacity-transition': fade } })
					map.addLayer({ id: 'gva-line', type: 'line', source: 'gva', paint: { 'line-color': '#ffd166', 'line-width': 1.3, 'line-opacity': 0, 'line-opacity-transition': fade } })
					map.addLayer({ id: 'ems-case', type: 'line', source: 'ems', paint: { 'line-color': '#2a0619', 'line-width': 3.4, 'line-opacity': 0, 'line-opacity-transition': fade } })
					map.addLayer({ id: 'ems-line', type: 'line', source: 'ems', paint: { 'line-color': '#ff7ac8', 'line-width': 1.5, 'line-opacity': 0, 'line-opacity-transition': fade } })
					map.addLayer({
						id: 'depth',
						type: 'circle',
						source: 'depth',
						minzoom: 11,
						paint: {
							'circle-radius': ['interpolate', ['linear'], ['get', 'depth_m'], 0.1, 3, 1.5, 7.5],
							'circle-color': ['interpolate', ['linear'], ['get', 'depth_m'], 0.1, '#ffe6a8', 0.8, '#ff9d3c', 1.5, '#e8452c'],
							'circle-stroke-color': '#1a0f08',
							'circle-stroke-width': 1,
							'circle-opacity': 0,
							'circle-stroke-opacity': 0,
							'circle-opacity-transition': fade,
							'circle-stroke-opacity-transition': fade,
						},
					})
					const tip = new Popup({ closeButton: false, offset: 10, className: 'fl-tip' })
					map.on('mousemove', 'depth', (ev) => {
						const f = ev.features?.[0]
						if (!f || !map) return
						map.getCanvas().style.cursor = 'pointer'
						tip.setLngLat(ev.lngLat).setText(`${Number(f.properties.depth_m).toFixed(1)} m of water measured here`).addTo(map)
					})
					map.on('mouseleave', 'depth', () => {
						if (map) map.getCanvas().style.cursor = ''
						tip.remove()
					})
				}
				for (const p of story.places) {
					const node = document.createElement('span')
					const label = document.createElement('span')
					label.className = 'fl-place'
					label.textContent = p.name
					node.appendChild(label)
					new Marker({ element: node, anchor: 'center' }).setLngLat(p.at).addTo(map)
				}
				if (story.space) {
					// from far out one ring says where the place is
					const ring = document.createElement('span')
					const mark = document.createElement('span')
					mark.className = 'fl-ring'
					mark.textContent = story.space.ring
					ring.appendChild(mark)
					new Marker({ element: ring, anchor: 'center' }).setLngLat(story.camera.center).addTo(map)
				}
				setMapReady(true)
			})
		})()
		return () => {
			gone = true
			map?.remove()
			mapRef.current = null
			water.current = null
			pic.current = null
			picBefore.current = null
			setMapReady(false)
			setReady(false)
		}
	}, [data, story])

	// keep the place in the part of the map the panels leave free
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady) return
		const fit = () => {
			const wide = window.innerWidth > 1180
			// on a phone the readout sits above the dock, so the free part of the map is the top
			const side = window.innerWidth <= 720 ? (document.querySelector<HTMLElement>('.fl-side')?.offsetHeight ?? 0) + 12 : 0
			map.setPadding({ top: 70, left: 0, right: wide ? 330 : 0, bottom: (dock.current?.offsetHeight ?? 240) + 20 + side })
			if (!st.current.playing && map.getZoom() > 9) map.jumpTo({ center: story.camera.center, zoom: window.innerWidth < 720 ? story.camera.zoom - 1.3 : story.camera.zoom })
		}
		fit()
		window.addEventListener('resize', fit)
		return () => window.removeEventListener('resize', fit)
	}, [mapReady, story])

	// the radar water of the chosen series: one layer, under the reference lines
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady || !data || !active) return
		const layer = new WaterLayer({ id: `water-${active.series.id}`, root: story.root, meta: data.meta, series: active.layerSeries })
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

	// one loop: move the playhead while playing, redraw when anything changed
	useEffect(() => {
		if (!active) return
		const { model } = active
		// data time per millisecond: the whole series in a fixed number of seconds
		const pace = (model.last - model.first) / (PLAY_SECONDS[story.kind] * 1000)
		st.current.T = Math.min(model.last, Math.max(model.first, st.current.T))
		let raf = 0
		const loop = (now: number) => {
			raf = requestAnimationFrame(loop)
			const s = st.current
			const dt = Math.min(100, now - (s.now || now))
			s.now = now
			if (s.playing) {
				if (s.dwell > 0) s.dwell -= dt
				else {
					const next = s.T + dt * pace * speed.current
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
			if (map && water.current) {
				// from far out the picture from space takes over: the site layers fade away
				const zf = story.space ? clamp01((map.getZoom() - 8.6) / 1.2) : 1
				if (Math.abs(zf - s.zoomFade) > 0.004) {
					s.zoomFade = zf
					water.current.setStyle({ opacity: opt.current.showWater ? zf : 0 })
					pic.current?.setAlpha(zf)
					picBefore.current?.setAlpha(zf)
					mapEl.current?.parentElement?.style.setProperty('--near', String(zf))
				}
			}
			if (s.T !== s.shown) apply(s.T)
		}
		raf = requestAnimationFrame(loop)
		return () => cancelAnimationFrame(raf)
	}, [active, apply, story])

	// toggles
	useEffect(() => {
		st.current.playing = playing
		const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		water.current?.setFlow(playing && !calm ? 1 : 0)
	}, [playing, ready])
	useEffect(() => {
		st.current.zoomFade = -1
		st.current.shown = Number.NaN
		st.current.outl = ''
		st.current.tone = ''
	}, [optical, showWater, showOutlines, ready, w])
	useEffect(() => {
		water.current?.setStyle({ soft: exact ? 0 : 0.85 })
	}, [exact, ready])
	useEffect(() => {
		const before = data?.optical.scenes[0]?.day ?? null
		const s = st.current.split
		if (compare) {
			picBefore.current?.show(before, 300)
			picBefore.current?.setClip(0, s)
			water.current?.setClip(s, 1)
		} else {
			picBefore.current?.show(null, 300)
			water.current?.setClip(0, 1)
		}
		if (swipe.current) swipe.current.style.transform = `translate3d(${s * (mapEl.current?.clientWidth ?? 0)}px, 0, 0)`
	}, [compare, data, ready])

	// the width of the time axis
	useEffect(() => {
		if (!tlBox.current) return
		const ro = new ResizeObserver(([entry]) => setW(Math.round(entry.contentRect.width)))
		ro.observe(tlBox.current)
		return () => ro.disconnect()
	}, [data])

	const seek = useCallback(
		(t: number) => {
			if (!active) return
			st.current.T = Math.min(active.model.last, Math.max(active.model.first, t))
			st.current.dwell = 0
		},
		[active],
	)

	const scrub = useCallback(
		(clientX: number) => {
			if (!tlBox.current || w <= 2 * X_PAD) return
			const r = tlBox.current.getBoundingClientRect()
			seek(days.t0 + ((clientX - r.left - X_PAD) / (w - 2 * X_PAD)) * (days.t1 - days.t0))
		},
		[seek, w, days],
	)

	const toggle = useCallback(() => {
		if (!active) return
		setPlaying((p) => {
			if (!p && st.current.T >= active.model.last - 1) st.current.T = active.model.first
			return !p
		})
	}, [active])

	const step = useCallback(
		(dir: 1 | -1) => {
			if (!active) return
			const { times } = active.model
			const i = active.model.before(st.current.T)
			setPlaying(false)
			st.current.T = dir > 0 ? times[Math.min(times.length - 1, i + 1)] : st.current.T > times[i] + 1 ? times[i] : times[Math.max(0, i - 1)]
		},
		[active],
	)

	useEffect(() => {
		const key = (e: KeyboardEvent) => {
			if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(e.target.tagName)) return
			if (e.code === 'Space') {
				e.preventDefault()
				toggle()
			} else if (e.code === 'ArrowRight') step(1)
			else if (e.code === 'ArrowLeft') step(-1)
		}
		window.addEventListener('keydown', key)
		return () => window.removeEventListener('keydown', key)
	}, [toggle, step])

	const fly = useCallback(() => {
		const map = mapRef.current
		if (!map || !story.space) return
		const space = story.space
		setFar((f) => {
			const to = f ? story.camera : space
			map.flyTo({ center: to.center, zoom: to.zoom, duration: 3200, curve: 1.3, essential: true })
			return !f
		})
	}, [story])

	/** The story told by itself, for the demo film: from space into the place, the passes played, then the check. */
	const tell = useCallback(async () => {
		const map = mapRef.current
		if (!map || !active || !data) return
		const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
		const { model } = active
		const done = () => {
			;(window as unknown as { __waterStoryDone?: boolean }).__waterStoryDone = true
		}
		setCinema(true)
		setCompare(false)
		setOptical('auto')
		setShowOutlines(true)
		setShowWater(true)
		setPlaying(false)
		if (story.space && days.storm0 !== null) {
			// 1. the storm day from space
			seek(days.storm0 + 12 * HOUR)
			map.jumpTo({ center: story.space.center, zoom: story.space.zoom })
			setFar(true)
			// let the picture from space arrive before anything moves
			await Promise.race([new Promise((r) => map.once('idle', r)), wait(4000)])
			await wait(500)
			map.easeTo({ zoom: story.space.zoom + 0.55, duration: 2800, easing: (t) => t })
			await wait(2800)
			// 2. down to the place, back to the pass before the storm
			seek(model.first)
			map.flyTo({ center: story.camera.center, zoom: story.camera.zoom, duration: 3400, curve: 1.25, essential: true })
			await wait(3500)
			setFar(false)
			await wait(1100)
		} else {
			seek(model.first)
			await wait(1400)
		}
		// 3. the passes, played
		speed.current = story.kind === 'storm' ? 2 : 1
		setPlaying(true)
		await new Promise<void>((ok) => {
			const id = window.setInterval(() => {
				if (st.current.T >= model.last) {
					window.clearInterval(id)
					ok()
				}
			}, 80)
		})
		speed.current = 1
		await wait(1700)
		if (story.kind !== 'storm' || days.storm1 === null) return done()
		// 4. the check against the clear picture after the storm, swiped
		const clear = data.optical.scenes.find((x) => cloud(x) < 5 && Date.parse(x.time_utc) > days.storm1!)
		if (clear) setOptical(clear.day)
		st.current.split = 0.78
		setCompare(true)
		const box = mapEl.current
		const from = performance.now()
		await new Promise<void>((ok) => {
			const tick = (now: number) => {
				const k = Math.min(1, (now - from) / 2600)
				const e = k * k * (3 - 2 * k)
				const s = 0.78 - 0.42 * e
				st.current.split = s
				picBefore.current?.setClip(0, s)
				water.current?.setClip(s, 1)
				if (swipe.current && box) swipe.current.style.transform = `translate3d(${s * box.clientWidth}px, 0, 0)`
				if (k < 1) requestAnimationFrame(tick)
				else ok()
			}
			requestAnimationFrame(tick)
		})
		await wait(1600)
		done()
	}, [active, data, seek, story, days])

	// a small handle on the page for the storyboard shots and the demo recording (scripts/shoot_flood.py)
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
			optical: (key: string) => setOptical(key),
			compare: (on: boolean, split = 0.5) => {
				st.current.split = split
				setCompare(on)
			},
			water: (on: boolean) => setShowWater(on),
			outlines: (on: boolean) => setShowOutlines(on),
			exact: (on: boolean) => setExact(on),
			cinema: (on: boolean) => setCinema(on),
			story: tell,
			camera: (center: [number, number], zoom: number, ms = 0) => {
				if (ms > 0) mapRef.current?.flyTo({ center, zoom, duration: ms, curve: 1.3, essential: true })
				else mapRef.current?.jumpTo({ center, zoom })
			},
			settled: () => !!water.current?.ready() && !!pic.current?.current() && !!mapRef.current?.loaded() && !mapRef.current?.isMoving(),
		}
		const host = window as unknown as { __flood?: typeof api }
		host.__flood = api
		return () => {
			delete host.__flood
		}
	}, [data, active, seek, tell])

	// once the page is ready it plays by itself: ?story plays the film, otherwise the passes run once
	const told = useRef(false)
	useEffect(() => {
		if (!ready || told.current) return
		told.current = true
		const q = new URLSearchParams(window.location.search)
		if (q.has('story')) {
			tell()
			return
		}
		// people who ask for less motion, and scripts that take stills (?still), get a still picture
		if (q.has('still') || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
		const id = window.setTimeout(() => setPlaying(true), 1100)
		return () => window.clearTimeout(id)
	}, [ready, tell])

	const dragSwipe = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
		const box = mapEl.current
		if (!box) return
		const move = (ev: PointerEvent) => {
			const r = box.getBoundingClientRect()
			const s = Math.min(0.96, Math.max(0.04, (ev.clientX - r.left) / r.width))
			st.current.split = s
			picBefore.current?.setClip(0, s)
			water.current?.setClip(s, 1)
			if (swipe.current) swipe.current.style.transform = `translate3d(${s * r.width}px, 0, 0)`
		}
		const up = () => {
			window.removeEventListener('pointermove', move)
			window.removeEventListener('pointerup', up)
		}
		window.addEventListener('pointermove', move)
		window.addEventListener('pointerup', up)
		e.preventDefault()
	}, [])

	const set = (name: string) => (node: HTMLElement | null) => {
		el.current[name] = node
	}
	const before = data?.optical.scenes[0]
	const twoClass = active?.twoClass ?? false
	const storm = story.kind === 'storm'

	return (
		<div className="fl" data-ready={ready || undefined} data-far={far || undefined} data-cinema={cinema || undefined}>
			<div ref={mapEl} className="fl-map" />
			{story.storm && <div ref={set('rain')} className="fl-rain" aria-hidden />}
			{compare && (
				<div ref={swipe} className="fl-swipe" onPointerDown={dragSwipe}>
					<span className="fl-swipe-tag" data-side="left">
						{before ? `${utcDay(Date.parse(before.time_utc))}${storm ? ', before' : ''}` : 'Before'}
					</span>
					<span className="fl-swipe-tag" data-side="right">
						Radar water
					</span>
					<i />
				</div>
			)}

			<header className="fl-head">
				<Link href="/" className="fl-back">
					Dancing with the SARs
				</Link>
				<h1 className="display fl-title">{story.title}</h1>
				<p className="fl-sub">{story.place}</p>
			</header>

			<p ref={set('picchip')} className="fl-picchip" />
			{story.space && <p className="fl-picchip fl-farchip">{story.space.label}</p>}

			<div className="fl-side">
				<section className="fl-read" aria-live="off">
					{choices.length > 1 && (
						<div className="fl-seg fl-sensor" role="radiogroup" aria-label="Radar">
							{choices.map((s) => (
								<button key={s.id} type="button" role="radio" aria-checked={active?.series.id === s.id} onClick={() => setSeriesId(s.id)}>
									{s.sensor} <small>{s.band}</small>
								</button>
							))}
						</div>
					)}
					<p className="fl-when mono">
						<span ref={set('date')}>&nbsp;</span>
						<span ref={set('clock')} className="fl-clock" />
					</p>
					<p ref={set('chip')} className="fl-chip" data-state="pass" />
					<p className="fl-big">
						<b ref={set('open')} className="mono">
							0
						</b>
						<span>
							ha of
							<br />
							{twoClass ? 'open water' : 'water'}
						</span>
					</p>
					<p className="fl-row" hidden={!twoClass}>
						<b ref={set('veg')} className="mono">
							0
						</b>{' '}
						ha of flooded vegetation
					</p>
					<p ref={set('delta')} className="fl-row fl-delta" />
					<p ref={set('seen')} className="fl-row fl-seen" />
				</section>

				<aside className="fl-legend">
					<p>
						<i data-k="open" /> {storm ? (twoClass ? 'Open water' : 'Water') : 'Water that is always there'}
					</p>
					{twoClass && (
						<p>
							<i data-k="veg" /> Flooded vegetation
						</p>
					)}
					<p>
						<i data-k="new" /> {storm ? 'New since the storm' : 'Water of the season'}
					</p>
					<p>
						<i data-k="est" /> Between passes: an estimate
					</p>
					{story.ems && (
						<>
							<p>
								<i data-k="ems" /> Copernicus EMS outline, {utcDay(days.ems0 ?? 0, false).split(' ')[0]} to {utcDay(days.ems1 ?? 0, false)}
							</p>
							<p>
								<i data-k="gva" /> Official river-flood footprint
							</p>
							<p>
								<i data-k="depth" /> Measured depth
							</p>
						</>
					)}
				</aside>
			</div>

			<footer ref={dock} className="fl-dock">
				<div className="fl-dock-top">
					<button type="button" className="fl-play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'} disabled={!ready}>
						{playing ? <Pause size={20} strokeWidth={2.4} /> : <Play size={20} strokeWidth={2.4} />}
					</button>
					<p ref={set('caption')} className="fl-caption" />
					<div className="fl-tools">
						<div className="fl-seg" role="radiogroup" aria-label="Satellite picture">
							<button type="button" role="radio" aria-checked={optical === 'auto'} onClick={() => setOptical('auto')}>
								Latest picture
							</button>
							{data?.optical.scenes.map((s) => (
								<button key={s.day} type="button" role="radio" aria-checked={optical === s.day} onClick={() => setOptical(s.day)} title={`Sentinel-2, ${cloud(s).toFixed(0)} % cloud`}>
									{utcDay(Date.parse(s.time_utc), false)}
								</button>
							))}
						</div>
						<button type="button" className="fl-tog" aria-pressed={showWater} onClick={() => setShowWater((v) => !v)}>
							Radar water
						</button>
						{story.ems && (
							<button type="button" className="fl-tog" aria-pressed={showOutlines} onClick={() => setShowOutlines((v) => !v)}>
								Outlines
							</button>
						)}
						<button type="button" className="fl-tog" aria-pressed={exact} onClick={() => setExact((v) => !v)} title="Draw the radar pixels exactly as delivered, with no rounding of their corners">
							Exact pixels
						</button>
						<button type="button" className="fl-tog" aria-pressed={compare} onClick={() => setCompare((v) => !v)}>
							<Columns2 size={15} /> Compare
						</button>
						{story.space && (
							<button type="button" className="fl-tog" aria-pressed={far} onClick={fly}>
								<Globe2 size={15} /> From space
							</button>
						)}
					</div>
				</div>

				<div
					ref={tlBox}
					className="fl-time"
					onPointerDown={(e) => {
						e.currentTarget.setPointerCapture(e.pointerId)
						setPlaying(false)
						scrub(e.clientX)
					}}
					onPointerMove={(e) => e.buttons === 1 && scrub(e.clientX)}
				>
					{data && active && w > 0 && <Timeline story={story} days={days} data={data} active={active} others={others} w={w} />}
					<div ref={head} className="fl-playhead">
						<b ref={set('tag')} className="mono" />
					</div>
				</div>

				<div className="fl-foot">
					<p ref={set('pic')} className="fl-picnote" />
					<p className="fl-keys">
						<i data-k="pass" /> {active?.series.sensor ?? 'radar'} pass <i data-k="nisar" /> NISAR pass <i data-k="pic" /> Sentinel-2 picture
						{story.ems && (
							<>
								{' '}
								<i data-k="emsday" /> EMS mapping days
							</>
						)}
					</p>
					<p className="fl-attrib">{story.credit}</p>
					<ThemeSwitch />
					<button type="button" className="fl-src" aria-expanded={credits} onClick={() => setCredits((v) => !v)}>
						Sources
					</button>
				</div>
				{credits && (
					<ul className="fl-credits">
						{story.credits.map((c) => (
							<li key={c.what}>
								<b>{c.what}</b> {c.who}
							</li>
						))}
					</ul>
				)}
			</footer>

			{error && <p className="fl-error">The layers did not load: {error}</p>}
		</div>
	)
}
