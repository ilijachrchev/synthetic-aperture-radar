'use client'

// The guided flood map (/explore): one flat map, one card, five steps, one main action each. Back and Next are quiet;
// "All layers" opens the free explorer. Every number on the card is read from a baked file at run time, with the
// field it comes from (see content/guided.ts for the files).
//
//   2  The official map said safe   tap a blue street (streets that flooded in 2024, official zones as outlines)
//   3  Our simulation saw it        one switch: the official map or our simulation, over the same blue streets
//   4  NISAR sees more water        drag the line between Sentinel-1 and NISAR of the same evening
//   5  Did we get it right?         drag the line between our prediction and what happened (EMSR935)
//   6  What if it rains             the rain slider on the model's likely flooded area, one outline

import 'maplibre-gl/dist/maplibre-gl.css'
import { ArrowLeft, ArrowRight, Layers, RotateCcw, X } from 'lucide-react'
import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ICV, PNOA } from '@/content/explore'
import { COLORS, REVEAL_FADE_MS, REVEAL_MS, STEPS, type StepKey } from '@/content/guided'
import { RainSlider } from '../explore/rain-slider'
import { MapSwipe } from './map-swipe'
import './guided.css'

const maplibre =
	typeof window === 'undefined'
		? null
		: import('maplibre-gl').then((m) => {
				m.setWorkerUrl(`/maplibre/maplibre-gl-worker.mjs?v=${m.getVersion()}`)
				m.setMaxParallelImageRequests(16)
				m.prewarm()
				return m
			})

const ROOT = '/layers/guided'
type Num = { value: number; source: string }
type StreetsIndex = {
	baked_utc: string
	files: Record<string, { file: string; bytes: number }>
	towns: string[]
	names: string[]
	zones: Record<string, string>
	reveal: { bins: number; rule: string }
	numbers: Record<string, Num>
	marks: { radius_m: number; points: [number, number, number][]; source: string }
	sources: Record<string, string>
}
type Pic = { file: string; bytes?: number }
type SwipeItem = { date: string; nisar: Pic & { time_utc: string }; s1: Pic & { time_utc: string }; numbers: Record<string, { value: number; what: string; source: unknown[] }> }
type ViewsDoc = { baked_utc: string; bounds: [number, number, number, number]; views: { swipe?: { items: SwipeItem[] } } }
type ExploreDoc = { sites: { pego_oliva?: { nisar: { still?: { date: string; open_water_share: number; source: string } } | null } } }
type ExamDoc = {
	baked_utc: string
	bounds: [number, number, number, number]
	prediction: Pic
	happened: Pic
	hectares: { hit: number; false_alarm: number; missed: number }
	source: Record<string, string>
	rain: { file: string; stops: { rain_mm: number; ha: number; lead_days: number; warning: string | null; source: string }[]; source: Record<string, string> } | null
}
type ScoreDoc = {
	score: string
	help: string
	model_rain_fell: number
	model_forecast: number
	simple_rules: [number, number]
	next_exam: string
	by: string
	source: string
}

type Pick = { name: string; town: string; zone: string; zoneCode: number; water: number | null; lngLat: [number, number] }

/** the 16 groups of the reveal, each its own layer, so a group fades in with one paint value */
const BINS = 16
const binLayer = (i: number) => `g-flood-${i}`
const BIN_LAYERS = Array.from({ length: BINS }, (_, i) => binLayer(i))
/** which map layers each step shows */
const STEP_LAYERS: Record<StepKey, string[]> = {
	missed: ['g-zones-line', ...BIN_LAYERS],
	simulation: ['g-flood-all'],
	nisar: [],
	exam: [],
	rain: ['g-rain-fill', 'g-rain-line'],
}
const ALL_LAYERS = [...new Set([...Object.values(STEP_LAYERS).flat(), 'g-zones-line', 'g-zones-fill', 'g-sim-line', 'g-sim-fill', 'g-pick'])]
const lineWidth = (k = 1) => ['interpolate', ['exponential', 1.6], ['zoom'], 11, 0.9 * k, 13, 1.8 * k, 15, 3.4 * k, 17, 6.5 * k, 18.6, 10 * k] as never

const pct = (v: number) => `${Math.round(v)}%`
const ha = (v: number) => Math.round(v).toLocaleString('en-US')
const f2 = (v: number) => v.toFixed(2)
const timeOf = (iso: string) => iso.slice(11, 16)
const minutesApart = (a: string, b: string) => Math.round(Math.abs(Date.parse(a) - Date.parse(b)) / 60000)

/** metres between two points, close together (equirectangular) */
function metres(a: [number, number], b: [number, number]) {
	const k = Math.cos(((a[1] + b[1]) / 2) * (Math.PI / 180))
	return Math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540)
}
/** the point of a line nearest to p */
function snap(p: [number, number], line: number[][]): [number, number] {
	let best: [number, number] = [line[0][0], line[0][1]]
	let dBest = Infinity
	const k = Math.cos(p[1] * (Math.PI / 180))
	for (let i = 0; i < line.length - 1; i++) {
		const ax = line[i][0] * k
		const ay = line[i][1]
		const bx = line[i + 1][0] * k
		const by = line[i + 1][1]
		const px = p[0] * k
		const py = p[1]
		const dx = bx - ax
		const dy = by - ay
		const t = dx || dy ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))) : 0
		const q: [number, number] = [(ax + t * dx) / k, ay + t * dy]
		const d = metres(p, q)
		if (d < dBest) {
			dBest = d
			best = q
		}
	}
	return best
}

/** the step the address asks for (?step=2 to 6, the numbers of the pitch: the landing is step 1) */
function firstStep() {
	if (typeof window === 'undefined') return 0
	const n = Number(new URLSearchParams(window.location.search).get('step'))
	return n >= 2 && n <= STEPS.length + 1 ? n - 2 : 0
}

async function getJson<T>(url: string): Promise<T> {
	const r = await fetch(url)
	if (!r.ok) throw new Error(`${url}: ${r.status}`)
	return (await r.json()) as T
}

export function GuidedApp({ onAllLayers }: { onAllLayers: () => void }) {
	const mapEl = useRef<HTMLDivElement>(null)
	const cardRef = useRef<HTMLElement>(null)
	const [map, setMap] = useState<MapLibreMap | null>(null)
	const [ready, setReady] = useState(false)
	const [step, setStep] = useState(firstStep)
	const [error, setError] = useState<string | null>(null)
	const [sources, setSources] = useState(false)

	const [streets, setStreets] = useState<StreetsIndex | null>(null)
	const [views, setViews] = useState<ViewsDoc | null>(null)
	const [explore, setExplore] = useState<ExploreDoc | null>(null)
	const [exam, setExam] = useState<ExamDoc | null>(null)
	const [score, setScore] = useState<ScoreDoc | null>(null)

	const [pick, setPick] = useState<Pick | null>(null)
	const [method, setMethod] = useState<'zones' | 'sim'>('zones')
	const [rainIdx, setRainIdx] = useState(2)

	const key = STEPS[step].key
	const s = STEPS[step]

	// ---------------------------------------------------------------- the step in the address, so a step can be shared
	useEffect(() => {
		const url = new URL(window.location.href)
		url.searchParams.set('step', String(step + 2))
		url.searchParams.delete('all')
		window.history.replaceState(null, '', url)
	}, [step])

	// ---------------------------------------------------------------- the files, each when its step first needs it
	useEffect(() => {
		const fail = (e: Error) => setError(e.message)
		if ((key === 'missed' || key === 'simulation') && !streets) getJson<StreetsIndex>(`${ROOT}/streets.json`).then(setStreets).catch(fail)
		if (key === 'nisar' && !views) getJson<ViewsDoc>('/layers/pego_oliva/views.json').then(setViews).catch(fail)
		if (key === 'nisar' && !explore) getJson<ExploreDoc>('/layers/explore/explore.json').then(setExplore).catch(fail)
		if ((key === 'exam' || key === 'rain') && !exam) getJson<ExamDoc>(`${ROOT}/exam.json`).then(setExam).catch(fail)
		if ((key === 'exam' || key === 'rain') && !score) getJson<ScoreDoc>(`${ROOT}/test_score.json`).then(setScore).catch(fail)
	}, [key, streets, views, explore, exam, score])

	// ---------------------------------------------------------------- the map
	useEffect(() => {
		if (!mapEl.current) return
		let m: MapLibreMap | null = null
		let gone = false
		;(async () => {
			const { Map } = await (maplibre ?? import('maplibre-gl'))
			if (gone || !mapEl.current) return
			m = new Map({
				container: mapEl.current,
				style: {
					version: 8,
					sources: {
						pnoa: { type: 'raster', tiles: [PNOA.tiles], tileSize: 256, maxzoom: PNOA.maxzoom, attribution: PNOA.credit },
						icv: { type: 'raster', tiles: [ICV.tiles], tileSize: 256, maxzoom: ICV.maxzoom, attribution: ICV.credit },
					},
					layers: [
						{ id: 'pnoa', type: 'raster', source: 'pnoa', paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.82 } },
						{ id: 'icv', type: 'raster', source: 'icv', layout: { visibility: 'none' }, paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.82 } },
					],
				},
				bounds: STEPS[0].view,
				fitBoundsOptions: { padding: 40 },
				minZoom: 8,
				maxZoom: 18.6,
				pitch: 0,
				maxPitch: 0,
				dragRotate: false,
				pitchWithRotate: false,
				attributionControl: { compact: true },
			})
			m.touchZoomRotate.disableRotation()
			// the official photographs first; should their server fail, the Valencian ones
			let failed = 0
			m.on('error', (e) => {
				if ((e as unknown as { sourceId?: string }).sourceId === 'pnoa' && ++failed === 4 && m) {
					m.setLayoutProperty('pnoa', 'visibility', 'none')
					m.setLayoutProperty('icv', 'visibility', 'visible')
				}
			})
			m.once('style.load', () => {
				if (gone || !m) return
				// on a phone the photo credit folds into its (i) button, so it does not cover the map (MapLibre opens it
				// once its sources have loaded: fold it then too)
				const fold = () => {
					if (window.innerWidth < 900) mapEl.current?.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show')
				}
				fold()
				m.once('idle', fold)
				setMap(m)
				setReady(true)
			})
		})()
		return () => {
			gone = true
			m?.remove()
			setMap(null)
			setReady(false)
		}
	}, [])

	/** room the card takes on screen: the map frames each step in what is left */
	const padding = useCallback(() => {
		const el = cardRef.current
		const w = window.innerWidth
		const h = window.innerHeight
		if (!el) return 40
		const r = el.getBoundingClientRect()
		if (w >= 900) return { top: 70, bottom: 40, left: Math.min(w * 0.6, r.right + 24), right: 40 }
		return { top: 64, bottom: Math.min(h * 0.62, h - r.top + 16), left: 16, right: 16 }
	}, [])

	// each step frames its own ground
	useEffect(() => {
		if (!map || !ready) return
		map.fitBounds(STEPS[step].view, { padding: padding(), duration: step === 0 ? 0 : 1600, essential: true })
	}, [map, ready, step, padding])

	// ---------------------------------------------------------------- the street layers (steps 2 and 3)
	useEffect(() => {
		if (!map || !ready || !streets || map.getSource('g-streets')) return
		const v = `?v=${encodeURIComponent(streets.baked_utc)}`
		map.addSource('g-zones', { type: 'geojson', data: `${ROOT}/${streets.files.zones.file}${v}` })
		map.addSource('g-sim', { type: 'geojson', data: `${ROOT}/${streets.files.simulated.file}${v}` })
		map.addSource('g-streets', { type: 'geojson', data: `${ROOT}/${streets.files.streets.file}${v}` })
		map.addSource('g-pick', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
		const hidden = { visibility: 'none' as const }
		map.addLayer({ id: 'g-zones-fill', type: 'fill', source: 'g-zones', layout: hidden, paint: { 'fill-color': COLORS.zone, 'fill-opacity': 0.16 } })
		map.addLayer({ id: 'g-sim-fill', type: 'fill', source: 'g-sim', layout: hidden, paint: { 'fill-color': COLORS.sim, 'fill-opacity': 0.34 } })
		map.addLayer({ id: 'g-zones-line', type: 'line', source: 'g-zones', layout: hidden, paint: { 'line-color': COLORS.zone, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1, 16, 2.4] as never, 'line-opacity': 0.95 } })
		map.addLayer({ id: 'g-sim-line', type: 'line', source: 'g-sim', layout: hidden, paint: { 'line-color': COLORS.sim, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1, 16, 2.4] as never, 'line-opacity': 0.95 } })
		const street = { 'line-color': COLORS.flooded, 'line-width': lineWidth(), 'line-opacity': 0 }
		for (let i = 0; i < BINS; i++) {
			map.addLayer({ id: binLayer(i), type: 'line', source: 'g-streets', filter: ['==', ['get', 'r'], i], layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' }, paint: street as never })
		}
		map.addLayer({ id: 'g-flood-all', type: 'line', source: 'g-streets', layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' }, paint: { ...street, 'line-opacity': 1 } as never })
		map.addLayer({ id: 'g-pick', type: 'line', source: 'g-pick', layout: { ...hidden, 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': lineWidth(2.2), 'line-opacity': 0.95 } }, binLayer(0))
		// what a tap reads: the flooded streets, wide and unseen
		map.addLayer({ id: 'g-hit', type: 'line', source: 'g-streets', paint: { 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 10, 16, 22] as never, 'line-opacity': 0 } })
	}, [map, ready, streets])

	// the rain outlines (step 6)
	useEffect(() => {
		if (!map || !ready || !exam?.rain || map.getSource('g-rain')) return
		map.addSource('g-rain', { type: 'geojson', data: `${ROOT}/${exam.rain.file}?v=${encodeURIComponent(exam.baked_utc)}` })
		map.addLayer({ id: 'g-rain-fill', type: 'fill', source: 'g-rain', layout: { visibility: 'none' }, paint: { 'fill-color': COLORS.rain, 'fill-opacity': 0.16 } })
		map.addLayer({ id: 'g-rain-line', type: 'line', source: 'g-rain', layout: { visibility: 'none', 'line-join': 'round' }, paint: { 'line-color': COLORS.rain, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1.2, 16, 3] as never } })
	}, [map, ready, exam])

	// which layers show
	useEffect(() => {
		if (!map || !ready) return
		const on = new Set(STEP_LAYERS[key])
		if (key === 'simulation') for (const id of method === 'zones' ? ['g-zones-line', 'g-zones-fill'] : ['g-sim-fill']) on.add(id)
		if (key === 'missed' && pick) on.add('g-pick')
		for (const id of ALL_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on.has(id) ? 'visible' : 'none')
		if (map.getLayer('g-hit')) map.setLayoutProperty('g-hit', 'visibility', key === 'missed' ? 'visible' : 'none')
	}, [map, ready, key, method, pick, streets, exam])

	// step 2 opens with the flooded streets appearing outward from the ravines, about 4 s, then still
	const playReveal = useCallback(() => {
		let stop = false
		if (!map || !map.getLayer(binLayer(0))) return () => {}
		const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		const gap = (REVEAL_MS - REVEAL_FADE_MS) / (BINS - 1)
		const t0 = performance.now()
		const frame = (now: number) => {
			if (stop) return
			const t = reduce ? Infinity : now - t0
			let done = true
			for (let i = 0; i < BINS; i++) {
				const k = Math.min(1, Math.max(0, (t - i * gap) / REVEAL_FADE_MS))
				if (k < 1) done = false
				map.setPaintProperty(binLayer(i), 'line-opacity', k * k * (3 - 2 * k))
			}
			if (!done) requestAnimationFrame(frame)
		}
		requestAnimationFrame(frame)
		return () => {
			stop = true
		}
	}, [map])
	useEffect(() => {
		if (key !== 'missed' || !map || !map.getLayer(binLayer(0))) return
		// wait for the camera and the lines, so the first group is drawn when it starts
		let gone = false
		let cancel = () => {}
		const go = () => {
			if (!gone) cancel = playReveal()
		}
		if (map.isSourceLoaded('g-streets') && !map.isMoving()) go()
		else map.once('idle', go)
		return () => {
			gone = true
			map.off('idle', go)
			cancel()
		}
	}, [key, map, playReveal, streets])

	// ---------------------------------------------------------------- tap a street (step 2)
	const tap = useCallback(
		(e: MapMouseEvent) => {
			if (!map || !streets || key !== 'missed' || !map.getLayer('g-hit')) return
			const p = e.point
			const hits = map.queryRenderedFeatures(
				[
					[p.x - 6, p.y - 6],
					[p.x + 6, p.y + 6],
				],
				{ layers: ['g-hit'] },
			)
			const at: [number, number] = [e.lngLat.lng, e.lngLat.lat]
			let best: { f: (typeof hits)[number]; q: [number, number]; d: number } | null = null
			for (const f of hits) {
				if (f.geometry.type !== 'LineString') continue
				const q = snap(at, f.geometry.coordinates)
				const d = metres(at, q)
				if (!best || d < best.d) best = { f, q, d }
			}
			if (!best) {
				setPick(null)
				return
			}
			const props = best.f.properties as { z: number; t: number; n: number }
			let water: number | null = null
			let dw = Infinity
			for (const [lon, lat, depth] of streets.marks.points) {
				if (Math.abs(lat - best.q[1]) > 0.0005) continue
				const d = metres(best.q, [lon, lat])
				if (d <= streets.marks.radius_m && d < dw) {
					dw = d
					water = depth
				}
			}
			setPick({ name: streets.names[props.n] ?? 'Street', town: streets.towns[props.t] ?? '', zone: streets.zones[String(props.z)] ?? '', zoneCode: props.z, water, lngLat: best.q })
			const src = map.getSource('g-pick') as GeoJSONSource | undefined
			src?.setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: best.f.geometry }] })
		},
		[map, streets, key],
	)
	useEffect(() => {
		if (!map || !ready) return
		map.on('click', tap)
		return () => {
			map.off('click', tap)
		}
	}, [map, ready, tap])
	// the pointer says where a tap does something
	useEffect(() => {
		if (!map || !ready) return
		const over = () => (map.getCanvas().style.cursor = 'pointer')
		const out = () => (map.getCanvas().style.cursor = '')
		map.on('mouseenter', 'g-hit', over)
		map.on('mouseleave', 'g-hit', out)
		return () => {
			map.off('mouseenter', 'g-hit', over)
			map.off('mouseleave', 'g-hit', out)
		}
	}, [map, ready])

	// ---------------------------------------------------------------- step 6: the rain outline
	const rainStops = exam?.rain?.stops ?? []
	const rain = rainStops[Math.min(rainIdx, Math.max(0, rainStops.length - 1))]
	useEffect(() => {
		if (!map || !map.getLayer('g-rain-line') || !rain) return
		const f = ['==', ['get', 'rain_mm'], rain.rain_mm] as never
		map.setFilter('g-rain-line', f)
		map.setFilter('g-rain-fill', f)
	}, [map, rain, exam])

	// ---------------------------------------------------------------- moving between steps
	const go = useCallback((i: number) => {
		setPick(null)
		setStep(Math.max(0, Math.min(STEPS.length - 1, i)))
	}, [])
	useEffect(() => {
		const onKey = (e: KeyboardEvent) => {
			if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return
			if (e.target instanceof HTMLElement && e.target.getAttribute('role') === 'slider') return
			if (e.key === 'Escape') setPick(null)
			if (e.key === 'ArrowRight' || e.key === 'PageDown') go(step + 1)
			if (e.key === 'ArrowLeft' || e.key === 'PageUp') go(step - 1)
		}
		window.addEventListener('keydown', onKey)
		return () => window.removeEventListener('keydown', onKey)
	}, [step, go])

	// a small handle for scripted checks
	useEffect(() => {
		const api = { map: () => map, step: (i: number) => go(i - 2), method: setMethod, rain: setRainIdx, reveal: () => void playReveal(), ready: () => ready && !!map?.loaded() }
		const host = window as unknown as { __guided?: typeof api }
		host.__guided = api
		return () => {
			delete host.__guided
		}
	}, [map, ready, go, playReveal])

	// ---------------------------------------------------------------- what the card says
	const swipe28 = useMemo(() => views?.views.swipe?.items.find((i) => i.date === '2026-10-28') ?? null, [views])
	const still = explore?.sites.pego_oliva?.nisar?.still ?? null
	const n = streets?.numbers

	let body: React.ReactNode = null
	if (key === 'missed') {
		body = (
			<>
				{n && (
					<div className="gd-num">
						<b className="display">{pct(n.outside_pct.value)}</b>
						<span>of the streets that flooded were outside every official flood zone</span>
					</div>
				)}
				{n && (
					<p className="gd-small">
						{ha(n.outside_km.value)} of {ha(n.flooded_km.value)} km of flooded street.
					</p>
				)}
				<ul className="gd-key">
					<li>
						<i className="gd-sw" data-k="flooded" /> Street that flooded: Copernicus EMS map or a measured water mark
					</li>
					<li>
						<i className="gd-sw" data-k="zone" /> Official flood zone (SNCZI)
					</li>
				</ul>
				{pick ? (
					<div className="gd-pick" aria-live="polite">
						<div className="gd-pick-head">
							<b>{pick.name}</b>
							<button type="button" className="gd-x" aria-label="Close" onClick={() => setPick(null)}>
								<X size={15} strokeWidth={2.4} />
							</button>
						</div>
						<small>{pick.town}</small>
						<p data-zone={pick.zoneCode === 0 || undefined}>{pick.zoneCode === 0 ? 'No flood zone' : `In the ${pick.zone}`}</p>
						<p>{pick.water !== null ? `Water ${pick.water.toFixed(1)} m, measured` : 'No measurement here'}</p>
					</div>
				) : (
					<p className="gd-hint">
						<i /> {s.hint}
					</p>
				)}
				<p className="gd-note">Shown outward from the ravines, not in time order.</p>
			</>
		)
	} else if (key === 'simulation') {
		body = (
			<>
				<div className="gd-seg" role="radiogroup" aria-label="Which map">
					<button type="button" role="radio" aria-checked={method === 'zones'} data-k="zone" onClick={() => setMethod('zones')}>
						Official map
					</button>
					<button type="button" role="radio" aria-checked={method === 'sim'} data-k="sim" onClick={() => setMethod('sim')}>
						Our simulation
					</button>
				</div>
				{n && (
					<div className="gd-pair">
						<p data-on={method === 'sim' || undefined}>
							<b className="display">{pct(n.sim_hit_pct.value)}</b>
							<span>of the flooded streets found by our simulation</span>
						</p>
						<p data-on={method === 'zones' || undefined}>
							<b className="display">{pct(n.zones_hit_pct.value)}</b>
							<span>by the official map</span>
						</p>
					</div>
				)}
				{n && (
					<p className="gd-small">
						{pct(n.sim_precision_pct.value)} of the streets our simulation flagged really flooded; the official map {pct(n.zones_precision_pct.value)}.
					</p>
				)}
				<ul className="gd-key">
					<li>
						<i className="gd-sw" data-k="flooded" /> Street that flooded
					</li>
					<li>
						<i className="gd-sw" data-k={method === 'zones' ? 'zone' : 'sim'} data-fill /> {method === 'zones' ? 'Official flood zone (SNCZI)' : 'Our simulation: water deeper than 0.3 m'}
					</li>
				</ul>
				<p className="gd-note">Run with the rain that fell on 29 Oct 2024.</p>
			</>
		)
	} else if (key === 'nisar') {
		body = (
			<>
				{swipe28 && (
					<div className="gd-pair">
						<p data-on>
							<b className="display">{pct(swipe28.numbers.nisar_finds.value * 100)}</b>
							<span>of the open water a same-day photo shows, found by NISAR</span>
						</p>
						<p>
							<b className="display">{pct(swipe28.numbers.s1_finds.value * 100)}</b>
							<span>by Sentinel-1</span>
						</p>
					</div>
				)}
				{still && <p className="gd-small">9 days after the flood, {pct(still.open_water_share * 100)} of the flooded farmland was still under water.</p>}
				<ul className="gd-key">
					<li>
						<i className="gd-sw" data-k="water" data-fill /> Water on each radar map
					</li>
					<li>
						<i className="gd-sw" data-k="nodata" data-fill /> Ground the map does not cover
					</li>
				</ul>
				{swipe28 && (
					<p className="gd-hint">
						<i /> {s.hint}: the same evening, {minutesApart(swipe28.nisar.time_utc, swipe28.s1.time_utc)} minutes apart
					</p>
				)}
			</>
		)
	} else if (key === 'exam') {
		body = (
			<>
				{score && (
					<div className="gd-pair">
						<p data-on>
							<b className="display">{f2(score.model_rain_fell)}</b>
							<span>our model, with the rain that fell</span>
						</p>
						<p>
							<b className="display">{f2(score.model_forecast)}</b>
							<span>with the forecast</span>
						</p>
					</div>
				)}
				{score && (
					<p className="gd-small">
						Three simple rules: {f2(score.simple_rules[0])} to {f2(score.simple_rules[1])}. {score.score}: {score.help}.
					</p>
				)}
				<ul className="gd-key">
					<li>
						<i className="gd-sw" data-k="hit" data-fill /> Predicted, and it flooded{exam ? ` (${ha(exam.hectares.hit)} ha)` : ''}
					</li>
					<li>
						<i className="gd-sw" data-k="false" data-fill /> Predicted, stayed dry{exam ? ` (${ha(exam.hectares.false_alarm)} ha)` : ''}
					</li>
					<li>
						<i className="gd-sw" data-k="missed" data-fill /> Flooded, we missed it{exam ? ` (${ha(exam.hectares.missed)} ha)` : ''}
					</li>
				</ul>
				{score && <p className="gd-note">{score.next_exam}</p>}
			</>
		)
	} else if (key === 'rain') {
		body = (
			<>
				{rain && (
					<div className="gd-num">
						<b className="display">{ha(rain.ha)}</b>
						<span>hectares likely flooded with {rain.rain_mm} mm of rain in {Math.round(rain.lead_days)} days</span>
					</div>
				)}
				{rainStops.length > 0 && (
					<div className="gd-rain">
						<RainSlider stops={rainStops.map((r) => ({ label: `${r.rain_mm} mm`, warn: !!r.warning }))} index={rainIdx} onInput={() => {}} onStop={setRainIdx} label="Rain" />
					</div>
				)}
				<ul className="gd-key">
					<li>
						<i className="gd-sw" data-k="rain" data-fill /> Likely flooded, our model: a relative likelihood, not depth
					</li>
				</ul>
				{rain?.warning && <p className="gd-small">{rain.warning}.</p>}
				{rain?.rain_mm === 0 && <p className="gd-small">With no rain the model still marks this much: water the marsh holds in this season.</p>}
				<p className="gd-note">Version 1. Its tested score is on the step before.</p>
				<div className="gd-end">
					<button type="button" className="gd-btn" onClick={() => go(0)}>
						<RotateCcw size={15} strokeWidth={2.4} /> Start again
					</button>
					<button type="button" className="gd-btn" data-quiet onClick={onAllLayers}>
						<Layers size={15} strokeWidth={2.4} /> All layers
					</button>
				</div>
			</>
		)
	}

	const src: string[] = []
	if (key === 'missed' || key === 'simulation') {
		if (streets) src.push(`Streets: ${streets.sources.streets}.`, `Flood: ${streets.sources.flood}.`, `Water marks: ${streets.sources.marks}.`, `Zones: ${streets.sources.zones}.`)
		if (key === 'simulation' && streets) src.push(`Simulation: ${streets.sources.simulated}, with no infiltration, so an upper bound.`)
		if (streets) src.push(`Numbers: ${streets.sources.scores}.`)
	}
	if (key === 'nisar') {
		src.push('NISAR: NASA-ISRO L2 GCOV, track 066 D, water by the team CV model (v1 at 0.3).', 'Sentinel-1: OPERA DSWx-S1 (open water and flooded vegetation).', 'Same-day photo: OPERA DSWx-HLS (Landsat 9, Sentinel-2) within a day.')
		src.push('Numbers: public/layers/pego_oliva/views.json (bake_views.py); still flooded: data/metrics/nisar_labels_summary.json against Copernicus EMS EMSR935.')
	}
	if (key === 'exam') {
		if (score) src.push(`Test: ${score.by}. ${score.source}.`)
		if (exam) src.push(`Map: ${exam.source.model}; flood: ${exam.source.flood}.`)
	}
	if (key === 'rain' && exam?.rain) src.push(`Model: ${exam.rain.source.model}.`, `Rain scenarios: ${exam.rain.source.rain}.`)

	const swipeOn = map && (key === 'nisar' || key === 'exam')

	return (
		<div className="gd" data-step={key} data-ready={ready || undefined}>
			<div ref={mapEl} className="gd-map" />

			{swipeOn && key === 'nisar' && views && swipe28 && (
				<MapSwipe
					key="nisar"
					map={map}
					bounds={views.bounds}
					beside=".gd-card"
					left={{ src: `/layers/pego_oliva/${swipe28.s1.file}?v=${encodeURIComponent(views.baked_utc)}`, label: 'Sentinel-1', sub: `${timeOf(swipe28.s1.time_utc)} UTC` }}
					right={{ src: `/layers/pego_oliva/${swipe28.nisar.file}?v=${encodeURIComponent(views.baked_utc)}`, label: 'NISAR', sub: `${timeOf(swipe28.nisar.time_utc)} UTC` }}
				/>
			)}
			{swipeOn && key === 'exam' && exam && (
				<MapSwipe
					key="exam"
					map={map}
					bounds={exam.bounds}
					beside=".gd-card"
					left={{ src: `${ROOT}/${exam.prediction.file}?v=${encodeURIComponent(exam.baked_utc)}`, label: 'Our prediction' }}
					right={{ src: `${ROOT}/${exam.happened.file}?v=${encodeURIComponent(exam.baked_utc)}`, label: 'What happened' }}
				/>
			)}

			<header className="gd-top">
				<Link href="/" className="gd-brand">
					Dancing with the SARs
				</Link>
				<button type="button" className="gd-all" onClick={onAllLayers}>
					<Layers size={15} strokeWidth={2.4} /> All layers
				</button>
			</header>

			<section ref={cardRef} className="gd-card" aria-live="polite">
				<ol className="gd-dots" aria-label="Steps">
					{STEPS.map((x, i) => (
						<li key={x.key}>
							<button type="button" aria-current={i === step ? 'step' : undefined} aria-label={x.title} onClick={() => go(i)} />
						</li>
					))}
				</ol>
				<p className="gd-when">
					{s.when} · {s.where}
				</p>
				<h1 className="display gd-title">{s.title}</h1>
				<div className="gd-body" key={key}>
					{body}
				</div>
				<nav className="gd-nav">
					<button type="button" onClick={() => go(step - 1)} disabled={step === 0}>
						<ArrowLeft size={15} strokeWidth={2.4} /> Back
					</button>
					<button type="button" className="gd-src" aria-expanded={sources} onClick={() => setSources((v) => !v)}>
						Sources
					</button>
					<button type="button" onClick={() => go(step + 1)} disabled={step === STEPS.length - 1}>
						Next <ArrowRight size={15} strokeWidth={2.4} />
					</button>
				</nav>
				{sources && (
					<ul className="gd-sources">
						{src.map((x) => (
							<li key={x}>{x}</li>
						))}
					</ul>
				)}
				{error && <p className="gd-error">Some layers did not load: {error}</p>}
			</section>
		</div>
	)
}
