'use client'

import 'maplibre-gl/dist/maplibre-gl.css'
import { Columns2, Globe2, Pause, Play } from 'lucide-react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import Link from 'next/link'
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CREDITS, FLOOD } from '@/content/flood'
import { type FloodModel, PLATFORMS, type RainFile, floodModel, utcClock, utcDay } from '@/lib/flood-model'
import type { Bounds } from '@/lib/gl-quad'
import { PictureLayer } from '@/lib/picture-layer'
import { WaterLayer, type WaterMeta, type WaterSeries } from '@/lib/water-layer'
import { PaletteSwitch } from '../palette-switch'
import './flood.css'

type Scene = { day: string; file: string; time_utc: string; platform: string; scenes: { id: string; tile: string; cloud_pct: number }[] }
type Optical = { bounds: Bounds; credit: string; scenes: Scene[] }
type Outline = { title: string; when?: string; credit: string; features: unknown[] }
type Outlines = { ems: Outline; generalitat: Outline; depth: Outline }
type Data = { meta: WaterMeta; rain: RainFile; optical: Optical; outlines: Outlines }
/** one radar series cut to the days of the story, with its clock */
type Active = { series: WaterSeries; model: FloodModel; nisar: boolean; twoClass: boolean; ref: number }

const HOUR = 3600e3
const DAY = 24 * HOUR
const BASE_TILES = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2017_3857/default/g/{z}/{y}/{x}.jpg'
/** days of the series played per second, and the short hold on every pass */
const DAYS_PER_SECOND = 1.15
const DWELL_MS = 320
const T0 = Date.parse(FLOOD.window.from)
const T1 = Date.parse(FLOOD.window.to)
const STORM0 = Date.parse(FLOOD.storm.from)
const STORM1 = Date.parse(FLOOD.storm.to)
const EMS0 = Date.parse(FLOOD.ems.from)
const EMS1 = Date.parse(FLOOD.ems.to)
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const ha = (x: number) => Math.round(x).toLocaleString('en-US')
const frameTime = (f: { time_utc?: string; date?: string }) => Date.parse(f.time_utc ?? `${f.date}T12:00:00Z`)

/** the cloud share of a picture: the worst tile that covers the site */
const cloud = (s: Scene) => Math.max(...s.scenes.map((x) => x.cloud_pct))

function useData() {
	const [data, setData] = useState<Data | null>(null)
	const [error, setError] = useState<string | null>(null)
	useEffect(() => {
		let gone = false
		const get = (name: string) =>
			fetch(`${FLOOD.root}/${name}`).then((r) => {
				if (!r.ok) throw new Error(`${name}: ${r.status}`)
				return r.json()
			})
		Promise.all([get('meta.json'), get('rain.json'), get('optical.json'), get('outlines.json')])
			.then(([meta, rain, optical, outlines]: [WaterMeta, RainFile, Optical, Outlines]) => !gone && setData({ meta, rain, optical, outlines }))
			.catch((e: Error) => !gone && setError(e.message))
		return () => {
			gone = true
		}
	}, [])
	return { data, error }
}

/** a series with only the passes inside the days of the story */
function inWindow(series: WaterSeries): WaterSeries {
	const times = series.frames.map(frameTime)
	const i0 = times.findIndex((t) => t >= T0)
	let i1 = times.length - 1
	while (i1 >= 0 && times[i1] > T1) i1--
	if (i0 < 0 || i1 < i0) return { ...series, frames: [], between: [] }
	return { ...series, frames: series.frames.slice(i0, i1 + 1), between: series.between.slice(i0, i1) }
}

const X_PAD = 16

/** The time axis of the page: rain on top, the water the picture shows as an area, every pass as a mark. */
const Timeline = memo(function Timeline({ data, active, others, w }: { data: Data; active: Active; others: number[]; w: number }) {
	const { model, twoClass, nisar, series } = active
	const H = 116
	const X = (t: number) => X_PAD + ((t - T0) / (T1 - T0)) * (w - 2 * X_PAD)
	const hourW = Math.max(1, X(T0 + HOUR) - X(T0))

	const maxMm = Math.max(1, ...model.rainMm)
	const bars = model.rainT.map((t, i) => ({ t, mm: model.rainMm[i] })).filter((b) => b.mm > 0.05 && b.t > T0 && b.t <= T1)

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
	const yMax = Math.max(200, Math.ceil(top / 200) * 200)
	const Y0 = 88
	const Y = (v: number) => Y0 - (v / yMax) * 42
	const line = (f: (p: (typeof pts)[number]) => number) => pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(f(p)).toFixed(1)}`).join('')
	const area = (f: (p: (typeof pts)[number]) => number) => `${line(f)}L${X(model.last).toFixed(1)},${Y0}L${X(model.first).toFixed(1)},${Y0}Z`

	const days: number[] = []
	for (let d = Math.ceil(T0 / DAY) * DAY; d <= T1; d += DAY) days.push(d)
	const every = w > 1100 ? 2 : w > 700 ? 3 : 6
	const nisarMarks = [...(nisar ? model.times : []), ...FLOOD.otherNisar.map((n) => Date.parse(n.t))]
	const quiet = model.last + 6 * HOUR < T1

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
			<text className="fl-tl-note" x={X(STORM1 + 6 * HOUR)} y={11} textAnchor="start">
				rain, up to {Math.round(maxMm)} mm an hour (weather model)
			</text>

			<line className="fl-tl-grid" x1={X_PAD} x2={w - X_PAD} y1={Y(yMax)} y2={Y(yMax)} />
			<text className="fl-tl-note" x={w - X_PAD} y={Y(yMax) - 4} textAnchor="end">
				{ha(yMax)} ha
			</text>
			{quiet && (
				<>
					<rect x={X(model.last)} y={Y(yMax)} width={X(T1) - X(model.last)} height={Y0 - Y(yMax)} fill="url(#fl-nopass)" />
					<text className="fl-tl-note" x={(X(model.last) + X(T1)) / 2} y={Y0 - 16} textAnchor="middle">
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
			<line className="fl-tl-ems" x1={X(EMS0)} x2={X(EMS1)} y1={36} y2={36} />
			{data.optical.scenes
				.filter((s) => Date.parse(s.time_utc) >= T0)
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
			{days.map((d, i) => (
				<g key={d}>
					<line className="fl-tl-tick" x1={X(d)} x2={X(d)} y1={Y0} y2={Y0 + (i % every === 0 ? 5 : 3)} />
					{i % every === 0 && (
						<text className="fl-tl-day" x={X(d)} y={H - 3} textAnchor="middle">
							{utcDay(d, false)}
						</text>
					)}
				</g>
			))}
		</svg>
	)
})

export function FloodApp() {
	const { data, error } = useData()
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
	const [w, setW] = useState(0)
	const opt = useRef({ optical, showWater, showOutlines, compare })
	opt.current = { optical, showWater, showOutlines, compare }

	// the radar series the baked files hold for these days
	const choices = useMemo(() => (data ? FLOOD.series.map((id) => data.meta.series.find((s) => s.id === id)).filter((s): s is WaterSeries => !!s && inWindow(s).frames.length > 1) : []), [data])
	const active = useMemo<Active | null>(() => {
		if (!data || !choices.length) return null
		const series = inWindow(choices.find((s) => s.id === seriesId) ?? choices[0])
		const model = floodModel(series, data.rain)
		// the reference is the last pass before the rain
		const ref = model.times[0] < STORM0 ? model.before(STORM0) : -1
		return { series, model, nisar: series.sensor === 'NISAR', twoClass: series.frames.some((f) => f.veg_ha > 0), ref }
	}, [data, choices, seriesId])
	const others = useMemo(() => {
		if (!data || !active) return []
		return data.meta.series.filter((s) => s.sensor !== active.series.sensor && s.sensor !== 'NISAR').flatMap((s) => inWindow(s).frames.map(frameTime))
	}, [data, active])

	// the story in a few lines, every number read from the baked files
	const beats = useMemo(() => {
		if (!data || !active) return []
		const { model, series, nisar, twoClass, ref } = active
		const last = series.frames.length - 1
		const afterI = Math.min(last, Math.max(0, ref) + 1)
		const before = model.areaOfPass(Math.max(0, ref))
		const after = model.areaOfPass(afterI)
		const final = model.areaOfPass(last)
		const storm = data.rain.hours.filter((h) => Date.parse(h.t) > STORM0 && Date.parse(h.t) <= STORM1).reduce((a, h) => a + h.mm, 0)
		const emsHa = (data.outlines.ems.features[0] as { properties: { area_ha: number } }).properties.area_ha
		const what = twoClass ? 'open water' : 'water'
		const times = Math.round(after[0] / Math.max(1, before[0]))
		const usual = twoClass ? `${ha(before[0])} ha open, ${ha(before[1])} ha under plants` : `${ha(before[0])} ha`
		const list = [
			{ from: model.first, text: `Before the storm. ${nisar ? 'NISAR sees' : 'Sentinel-1 sees'} the usual water of the marsh: ${usual}.` },
			{ from: STORM0, text: `DANA Adam. The weather model puts ${ha(storm)} mm of rain here in two days. The optical satellite sees only cloud.` },
			{ from: EMS0, text: `Copernicus EMS maps ${ha(emsHa)} ha of flood from other satellites. No ${series.sensor} pass has come by yet.` },
			{ from: model.times[afterI] - 3 * HOUR, text: `${utcDay(model.times[afterI], false)}, first ${series.sensor} pass after the storm: ${ha(after[0])} ha of ${what}, ${times} times more than before.` },
		]
		if (last > afterI) {
			const weeks = Math.round((model.last - STORM1) / (7 * DAY))
			list.push({ from: model.times[afterI] + 30 * HOUR, text: 'Radar keeps passing, cloud or not. The water gives ground slowly.' })
			list.push({ from: model.last - 4 * DAY, text: `${weeks} weeks on, ${ha(final[0])} ha are still ${what}.` })
		}
		return list
	}, [data, active])

	const X = useCallback((t: number) => X_PAD + ((t - T0) / (T1 - T0)) * (w - 2 * X_PAD), [w])

	/** draw one moment: the map layers, the readout, the playhead */
	const apply = useCallback(
		(T: number) => {
			if (!data || !active) return
			const s = st.current
			const { model, series, ref, twoClass } = active
			const v = model.viewAt(T)
			const hasRef = ref >= 0 && T > model.times[ref] + 60e3
			water.current?.set({ a: v.a, b: v.b, gain: v.gain, loss: v.loss, observed: v.observed, ref: hasRef ? ref : -1 })
			water.current?.want(v.b + 1)

			// the newest real picture at this moment, unless a day is pinned
			const scenes = data.optical.scenes
			let key = opt.current.optical
			if (key === 'auto') key = (scenes.filter((x) => Date.parse(x.time_utc) <= T).pop() ?? scenes[0]).day
			const shownScene = scenes.find((x) => x.day === key)
			pic.current?.show(key)
			// under radar water the picture steps back a little; a sky full of cloud steps back more, so the water reads
			const cloudy = shownScene ? cloud(shownScene) > 80 : false
			const tone = `${opt.current.showWater ? 1 : 0}${cloudy ? 1 : 0}`
			if (tone !== s.tone) {
				s.tone = tone
				if (!opt.current.showWater) pic.current?.setTone(1, 1)
				else pic.current?.setTone(cloudy ? 0.7 : 0.88, cloudy ? 0.56 : 0.84)
			}

			const map = mapRef.current
			const outl = `${opt.current.showOutlines && T >= EMS0 ? 1 : 0}${opt.current.showOutlines && T >= STORM0 + DAY ? 1 : 0}`
			if (outl !== s.outl && map?.getLayer('ems-line')) {
				s.outl = outl
				map.setPaintProperty('ems-line', 'line-opacity', outl[0] === '1' ? 1 : 0)
				map.setPaintProperty('ems-case', 'line-opacity', outl[0] === '1' ? 0.5 : 0)
				map.setPaintProperty('gva-line', 'line-opacity', outl[1] === '1' ? 0.95 : 0)
				map.setPaintProperty('gva-case', 'line-opacity', outl[1] === '1' ? 0.45 : 0)
				map.setPaintProperty('depth', 'circle-opacity', outl[1] === '1' ? 1 : 0)
				map.setPaintProperty('depth', 'circle-stroke-opacity', outl[1] === '1' ? 1 : 0)
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
			if (hasRef) {
				const d = open - model.areaOfPass(ref)[0]
				put(e.delta, `${d >= 0 ? '+' : ''}${ha(d)} ha of ${twoClass ? 'open water' : 'water'} since ${utcDay(model.times[ref], false)}`)
			} else put(e.delta, 'The usual water of the marsh')
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
			const x = X(T)
			if (head.current) head.current.style.transform = `translate3d(${x}px, 0, 0)`
			if (e.tag) {
				put(e.tag, utcDay(T, false))
				e.tag.style.transform = x < 44 ? 'translateX(-14px)' : x > w - 44 ? 'translateX(calc(-100% + 14px))' : 'translateX(-50%)'
			}
			s.shown = T
		},
		[data, active, beats, X, w],
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
			map = new Map({
				container: mapEl.current,
				style: {
					version: 8,
					sources: {
						base: { type: 'raster', tiles: [BASE_TILES], tileSize: 256, maxzoom: 14 },
						space: { type: 'raster', tiles: [FLOOD.space.tiles], tileSize: 256, maxzoom: 9 },
					},
					layers: [
						{ id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.78 } },
						{ id: 'space', type: 'raster', source: 'space', paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 7.8, 1, 9.6, 0], 'raster-fade-duration': 0 } },
					],
				},
				center: FLOOD.camera.center,
				zoom: FLOOD.camera.zoom,
				minZoom: 4.5,
				maxZoom: 16,
				dragRotate: false,
				pitchWithRotate: false,
				attributionControl: false,
			})
			map.touchZoomRotate.disableRotation()
			mapRef.current = map
			map.on('load', () => {
				if (gone || !map) return
				const pictures = data.optical.scenes.map((s) => ({ key: s.day, url: `${FLOOD.root}/${s.file}` }))
				const small = window.matchMedia('(max-width: 820px)').matches
				picBefore.current = new PictureLayer({ id: 'pic-before', bounds: data.optical.bounds, pictures, maxSize: small ? 2048 : 4096 })
				pic.current = new PictureLayer({ id: 'pic', bounds: data.optical.bounds, pictures, maxSize: small ? 2048 : 4096 })
				picBefore.current.setTone(1, 0.96)
				map.addLayer(pic.current.layer)
				map.addLayer(picBefore.current.layer)

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
				for (const p of FLOOD.places) {
					const node = document.createElement('span')
					const label = document.createElement('span')
					label.className = 'fl-place'
					label.textContent = p.name
					node.appendChild(label)
					new Marker({ element: node, anchor: 'center' }).setLngLat(p.at).addTo(map)
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
	}, [data])

	// keep the place in the part of the map the panels leave free
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady) return
		const fit = () => {
			const wide = window.innerWidth > 1180
			map.setPadding({ top: 70, left: 0, right: wide ? 330 : 0, bottom: (dock.current?.offsetHeight ?? 240) + 20 })
			if (!st.current.playing && map.getZoom() > 9) map.jumpTo({ center: FLOOD.camera.center, zoom: window.innerWidth < 720 ? FLOOD.camera.zoom - 1.3 : FLOOD.camera.zoom })
		}
		fit()
		window.addEventListener('resize', fit)
		return () => window.removeEventListener('resize', fit)
	}, [mapReady])

	// the radar water of the chosen series: one layer, under the outlines
	useEffect(() => {
		const map = mapRef.current
		if (!map || !mapReady || !data || !active) return
		const layer = new WaterLayer({ id: `water-${active.series.id}`, root: FLOOD.root, meta: data.meta, series: active.series })
		layer.onFrame = () => layer.ready() && setReady(true)
		water.current = layer
		map.addLayer(layer.layer, 'gva-case')
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
	}, [mapReady, data, active])

	// one loop: move the playhead while playing, redraw when anything changed
	useEffect(() => {
		if (!active) return
		const { model } = active
		const speed = (DAYS_PER_SECOND * DAY) / 1000
		let raf = 0
		const loop = (now: number) => {
			raf = requestAnimationFrame(loop)
			const s = st.current
			const dt = Math.min(100, now - (s.now || now))
			s.now = now
			if (s.playing) {
				if (s.dwell > 0) s.dwell -= dt
				else {
					const next = s.T + dt * speed
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
				// from far out the storm picture takes over: the site layers fade away
				const zf = clamp01((map.getZoom() - 8.6) / 1.2)
				if (Math.abs(zf - s.zoomFade) > 0.004) {
					s.zoomFade = zf
					water.current.setStyle({ opacity: opt.current.showWater ? zf : 0 })
					pic.current?.setAlpha(zf)
					picBefore.current?.setAlpha(zf)
					map.getContainer().style.setProperty('--near', String(zf))
				}
			}
			if (s.T !== s.shown) apply(s.T)
		}
		raf = requestAnimationFrame(loop)
		return () => cancelAnimationFrame(raf)
	}, [active, apply])

	// toggles
	useEffect(() => {
		st.current.playing = playing
		water.current?.setFlow(playing ? 1 : 0)
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
			seek(T0 + ((clientX - r.left - X_PAD) / (w - 2 * X_PAD)) * (T1 - T0))
		},
		[seek, w],
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
		if (!map) return
		setFar((f) => {
			const to = f ? FLOOD.camera : FLOOD.region
			map.flyTo({ center: to.center, zoom: to.zoom, duration: 3200, curve: 1.3, essential: true })
			return !f
		})
	}, [])

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
	}, [data, active, seek])

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
	const twoClass = active?.twoClass ?? true

	return (
		<div className="fl" data-ready={ready || undefined} data-far={far || undefined}>
			<div ref={mapEl} className="fl-map" />
			{compare && (
				<div ref={swipe} className="fl-swipe" onPointerDown={dragSwipe}>
					<span className="fl-swipe-tag" data-side="left">
						{before ? `${utcDay(Date.parse(before.time_utc))}, before` : 'Before'}
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
				<h1 className="display fl-title">{FLOOD.title}</h1>
				<p className="fl-sub">{FLOOD.place}</p>
			</header>

			<p ref={set('picchip')} className="fl-picchip" />

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
					<i data-k="open" /> {twoClass ? 'Open water' : 'Water'}
				</p>
				{twoClass && (
					<p>
						<i data-k="veg" /> Flooded vegetation
					</p>
				)}
				<p>
					<i data-k="new" /> New since the storm
				</p>
				<p>
					<i data-k="est" /> Between passes: an estimate
				</p>
				<p>
					<i data-k="ems" /> Copernicus EMS outline, 20 to 21 Oct
				</p>
				<p>
					<i data-k="gva" /> Official river-flood footprint
				</p>
				<p>
					<i data-k="depth" /> Measured depth
				</p>
			</aside>
			</div>

			<footer ref={dock} className="fl-dock">
				<div className="fl-dock-top">
					<button type="button" className="fl-play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play the flood'} disabled={!ready}>
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
						<button type="button" className="fl-tog" aria-pressed={showOutlines} onClick={() => setShowOutlines((v) => !v)}>
							Outlines
						</button>
						<button type="button" className="fl-tog" aria-pressed={exact} onClick={() => setExact((v) => !v)} title="Draw the radar pixels exactly as delivered, with no rounding of their corners">
							Exact pixels
						</button>
						<button type="button" className="fl-tog" aria-pressed={compare} onClick={() => setCompare((v) => !v)}>
							<Columns2 size={15} /> Compare
						</button>
						<button type="button" className="fl-tog" aria-pressed={far} onClick={fly}>
							<Globe2 size={15} /> From space
						</button>
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
					{data && active && w > 0 && <Timeline data={data} active={active} others={others} w={w} />}
					<div ref={head} className="fl-playhead">
						<b ref={set('tag')} className="mono" />
					</div>
				</div>

				<div className="fl-foot">
					<p ref={set('pic')} className="fl-picnote" />
					<p className="fl-keys">
						<i data-k="pass" /> {active?.series.sensor ?? 'radar'} pass <i data-k="nisar" /> NISAR pass <i data-k="pic" /> Sentinel-2 picture <i data-k="emsday" /> EMS mapping days
					</p>
					<p className="fl-attrib">NISAR: NASA-ISRO · Sentinel-1, Sentinel-2: Copernicus · OPERA DSWx-S1: NASA JPL · EMSR935: Copernicus EMS · Generalitat Valenciana · Open-Meteo · NASA GIBS · EOX</p>
					<PaletteSwitch />
					<button type="button" className="fl-src" aria-expanded={credits} onClick={() => setCredits((v) => !v)}>
						Sources
					</button>
				</div>
				{credits && (
					<ul className="fl-credits">
						{CREDITS.map((c) => (
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
