'use client'

import 'maplibre-gl/dist/maplibre-gl.css'
import { ArrowLeft, ArrowUpRight, ChevronLeft, ChevronRight, Columns2, Globe2, Image as ImageIcon, Pause, Play, Waves } from 'lucide-react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Mark } from '../brand'
import { ChangeLayer } from '../change-layer'
import { PaletteSwitch } from '../palette-switch'
import './map-app.css'

type PassView = { img: string; dates: string[]; crid: string | null; granule: string; collection: string }
type Track = { id: string; label: string; passes: PassView[] }
type Place = { site: string; name: string; box: [number, number, number, number]; product: 'GCOV' | 'GUNW'; tracks: Track[] }
export type StoryCfg = {
	key: string
	n: string
	tab: string
	title: string
	what: string
	where: string
	kind: string
	note: string
	change: { kind: 'water' | 'fire' | 'sink' | 'quake'; legend: string; event?: string; epicentre?: [number, number] }
	places: Place[]
	initial: { pi: number; ti: number; a: number; b: number | null }
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dd = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`
const span = (p: PassView) => p.dates.map(dd).join(' > ')
const TILES = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg'
const center = (b: Place['box']): [number, number] => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]

/** An image that cross-fades when its source changes. */
function Fader({ src, alt }: { src: string; alt: string }) {
	const [layers, setLayers] = useState([{ src, id: 0 }])
	useEffect(() => {
		setLayers((l) => (l[l.length - 1].src === src ? l : [...l.slice(-1), { src, id: l[l.length - 1].id + 1 }]))
		const t = window.setTimeout(() => setLayers((l) => l.slice(-1)), 520)
		return () => window.clearTimeout(t)
	}, [src])
	return (
		<div className="mp-layer">
			{layers.map((l, i) => (
				<img key={l.id} src={l.src} alt={i === layers.length - 1 ? alt : ''} data-new={i === layers.length - 1 || undefined} />
			))}
		</div>
	)
}

/**
 * The map as an easy dashboard. What is where: every place is a marker on the map, the four stories sit on the left.
 * What to do: one dock at the bottom holds every command (step back, play the season, step on, compare) above the
 * pass timeline. What it is: one small card on the right, with the pass's record in NASA's catalogue as its proof.
 */
export function MapApp({ stories }: { stories: StoryCfg[] }) {
	const mapEl = useRef<HTMLDivElement>(null)
	const mapRef = useRef<MapLibreMap | null>(null)
	const ov = useRef<HTMLDivElement>(null)
	const after = useRef<HTMLDivElement>(null)
	const swipeEl = useRef<HTMLDivElement>(null)
	const pins = useRef<(HTMLButtonElement | null)[]>([])
	const swipeRef = useRef(0.5)
	const [ready, setReady] = useState(false)
	const [overview, setOverview] = useState(false)
	const [si, setSi] = useState(0)
	const [pi, setPi] = useState(stories[0].initial.pi)
	const [a, setA] = useState(0)
	const [b, setB] = useState<number | null>(stories[0].initial.b)
	const [compare, setCompare] = useState(false)
	const [side, setSide] = useState<'a' | 'b'>('b')
	const [playing, setPlaying] = useState(false)
	const [swipe, setSwipe] = useState(0.5)
	const [view, setView] = useState<'change' | 'radar'>('change')

	const story = stories[si]
	const place = story.places[Math.min(pi, story.places.length - 1)]
	const ti = pi === story.initial.pi ? story.initial.ti : 0
	const track = place.tracks[Math.min(ti, place.tracks.length - 1)]
	const n = track.passes.length
	const pa = track.passes[Math.min(a, n - 1)]
	const pb = b != null ? track.passes[Math.min(b, n - 1)] : null
	const showB = compare && pb != null && !overview
	const frames = useMemo(() => track.passes.map((p) => p.img), [track])
	const refCount = story.change.event ? Math.max(1, track.passes.filter((p) => p.dates[0] < story.change.event!).length) : 1
	const ev = story.change.event
	const revealAt = ev ? track.passes.findIndex((p) => p.dates[0] < ev && p.dates[p.dates.length - 1] >= ev) : -1
	const epi = useMemo<[number, number]>(() => {
		const c = story.change.epicentre
		if (!c) return [0.5, 0.5]
		const [w, s, e, nn] = place.box
		return [(c[0] - w) / (e - w), (nn - c[1]) / (nn - s)]
	}, [story.change.epicentre, place.box])

	// every place of every story, for the markers
	const allPlaces = useMemo(() => stories.flatMap((s, i) => s.places.map((p, j) => ({ story: i, place: j, name: p.name, key: s.key, c: center(p.box) }))), [stories])

	const choose = useCallback(
		(i: number, placeIdx?: number) => {
			const s = stories[i]
			const pIdx = placeIdx ?? s.initial.pi
			const same = pIdx === s.initial.pi
			setOverview(false)
			setSi(i)
			setPi(pIdx)
			// the change view starts at the first pass so play runs the whole season
			setA(0)
			setB(same ? s.initial.b : null)
			setCompare(false)
			setView('change')
			setSide('b')
			setPlaying(false)
			try {
				history.replaceState(null, '', `/map?story=${s.key}`)
			} catch {}
		},
		[stories],
	)

	useEffect(() => {
		const k = new URLSearchParams(window.location.search).get('story')
		const i = stories.findIndex((s) => s.key === k)
		if (i > 0) choose(i)
	}, [stories, choose])

	// place the radar on its box and the markers on their places
	const layout = useCallback(() => {
		const map = mapRef.current
		if (!map) return
		const box = map.getContainer()
		// read everything first so a frame lays out once: the map's offset and the panels a marker must not sit under
		const o = box.getBoundingClientRect()
		const panels = box.parentElement ? [...box.parentElement.querySelectorAll<HTMLElement>(':scope > .mp-rail, :scope > .mp-card, :scope > .mp-dock')].map((el) => el.getBoundingClientRect()) : []
		const [w, s, e, nn] = place.box
		const tl = map.project([w, nn])
		const br = map.project([e, s])
		const ww = br.x - tl.x
		const hh = br.y - tl.y
		if (ov.current) {
			ov.current.style.transform = `translate3d(${tl.x}px, ${tl.y}px, 0)`
			ov.current.style.width = `${ww}px`
			ov.current.style.height = `${hh}px`
		}
		if (after.current) {
			const x = swipeRef.current * o.width - tl.x
			after.current.style.clipPath = `inset(0 0 0 ${Math.min(ww, Math.max(0, x))}px)`
		}
		if (swipeEl.current) {
			swipeEl.current.style.top = `${tl.y}px`
			swipeEl.current.style.height = `${hh}px`
		}
		allPlaces.forEach((p, k) => {
			const el = pins.current[k]
			if (!el) return
			const pt = map.project(p.c)
			el.style.transform = `translate3d(${pt.x}px, ${pt.y}px, 0)`
			// a marker is an icon above its point and a name below it; one that would sit under a panel steps away
			const x = pt.x + o.left
			const y = pt.y + o.top
			el.toggleAttribute('data-under', panels.some((r) => x + 50 > r.left && x - 50 < r.right && y + 26 > r.top && y - 46 < r.bottom))
		})
	}, [place.box, allPlaces])

	useEffect(() => {
		let map: MapLibreMap | null = null
		let gone = false
		;(async () => {
			const { Map, setWorkerUrl } = await import('maplibre-gl')
			setWorkerUrl('/maplibre/maplibre-gl-worker.mjs')
			if (gone || !mapEl.current) return
			const [w, s, e, nn] = stories[0].places[stories[0].initial.pi].box
			map = new Map({
				container: mapEl.current,
				style: {
					version: 8,
					sources: {
						s2: {
							type: 'raster',
							tiles: [TILES],
							tileSize: 256,
							maxzoom: 15,
							attribution: '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless</a> by EOX, modified Copernicus Sentinel data 2020 · Radar: NASA-ISRO NISAR via NASA ASF DAAC',
						},
					},
					layers: [{ id: 's2', type: 'raster', source: 's2', paint: { 'raster-saturation': -0.4, 'raster-contrast': 0.05 } }],
				},
				bounds: [
					[w, s],
					[e, nn],
				],
				maxZoom: 12.5,
				minZoom: 1.5,
				dragRotate: false,
				pitchWithRotate: false,
				attributionControl: { compact: true },
			})
			map.touchZoomRotate.disableRotation()
			mapRef.current = map
			map.on('load', () => {
				setReady(true)
				map?.getContainer().querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show')
			})
		})()
		return () => {
			gone = true
			map?.remove()
			mapRef.current = null
		}
	}, [stories])

	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		let raf = 0
		const on = () => {
			if (!raf)
				raf = requestAnimationFrame(() => {
					raf = 0
					layout()
				})
		}
		map.on('move', on)
		map.on('resize', on)
		layout()
		return () => {
			map.off('move', on)
			map.off('resize', on)
			cancelAnimationFrame(raf)
		}
	}, [ready, layout])

	// fly to the place, or out to every place
	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		const wide = window.innerWidth > 900
		const pad = wide ? { top: 90, bottom: 190, left: 340, right: 360 } : { top: 130, bottom: 230, left: 24, right: 24 }
		if (overview) {
			const xs = allPlaces.map((p) => p.c[0])
			const ys = allPlaces.map((p) => p.c[1])
			map.fitBounds(
				[
					[Math.min(...xs) - 4, Math.min(...ys) - 4],
					[Math.max(...xs) + 4, Math.max(...ys) + 4],
				],
				{ padding: pad, duration: 1600 },
			)
			return
		}
		const [w, s, e, nn] = place.box
		map.fitBounds(
			[
				[w, s],
				[e, nn],
			],
			{ padding: pad, duration: 1400, maxZoom: 11.2 },
		)
	}, [ready, place.box, si, pi, overview, allPlaces])

	useEffect(() => {
		swipeRef.current = swipe
		layout()
	}, [swipe, showB, layout])

	// the radar view steps on a timer; the change view plays itself and reports each pass it reaches
	useEffect(() => {
		if (!playing || view === 'change') return
		const id = window.setInterval(() => setA((v) => (v + 1) % n), 1100)
		return () => window.clearInterval(id)
	}, [playing, n, view])

	const step = useCallback(
		(d: number) => {
			setPlaying(false)
			if (compare && side === 'b') setB((v) => Math.min(n - 1, Math.max(0, (v ?? 0) + d)))
			else setA((v) => Math.min(n - 1, Math.max(0, v + d)))
		},
		[compare, side, n],
	)
	useEffect(() => {
		const on = (e: KeyboardEvent) => {
			if (e.key === 'ArrowLeft') step(-1)
			else if (e.key === 'ArrowRight') step(1)
			else if (e.key === ' ' && !(e.target instanceof HTMLButtonElement)) {
				e.preventDefault()
				setCompare(false)
				setPlaying((v) => !v)
			}
		}
		window.addEventListener('keydown', on)
		return () => window.removeEventListener('keydown', on)
	}, [step])

	const toggleCompare = () => {
		setPlaying(false)
		setView('radar')
		if (!compare && pi === story.initial.pi && story.initial.b != null) {
			setA(story.initial.a)
			setB(story.initial.b)
		} else if (!compare && b == null) setB(Math.min(n - 1, a + Math.max(1, Math.floor(n / 2))))
		setSide('b')
		setCompare(!compare)
	}
	const drag = (e: React.PointerEvent) => {
		const host = mapEl.current
		if (!host) return
		const r = host.getBoundingClientRect()
		const move = (ev: PointerEvent) => setSwipe(Math.min(0.97, Math.max(0.03, (ev.clientX - r.left) / r.width)))
		const up = () => {
			window.removeEventListener('pointermove', move)
			window.removeEventListener('pointerup', up)
		}
		window.addEventListener('pointermove', move)
		window.addEventListener('pointerup', up)
		move(e.nativeEvent)
	}

	const ticks = useMemo(() => {
		const t = track.passes.map((p) => Date.parse(p.dates[p.dates.length - 1]))
		const lo = Math.min(...t) - 6 * 864e5
		const hi = Math.max(...t) + 6 * 864e5
		const at = (v: number) => (v - lo) / (hi - lo)
		const months: { label: string; at: number }[] = []
		const d = new Date(lo)
		d.setUTCDate(1)
		d.setUTCMonth(d.getUTCMonth() + 1)
		while (d.getTime() < hi) {
			months.push({ label: MONTHS[d.getUTCMonth()], at: at(d.getTime()) })
			d.setUTCMonth(d.getUTCMonth() + 1)
		}
		return { at: t.map(at), months }
	}, [track])

	const cur = compare && side === 'b' && pb ? pb : pa
	const idx = compare && side === 'b' && b != null ? b : a

	return (
		<div className="mp" data-overview={overview || undefined}>
			<div ref={mapEl} className="mp-map" />
			<div className="mp-wash" aria-hidden />

			<div ref={ov} className="mp-ov" data-on={(ready && !overview) || undefined} data-view={showB ? 'radar' : view}>
				<Fader src={pa.img} alt={`NISAR ${place.name}, ${span(pa)}`} />
				{view === 'change' && !showB && (
					<ChangeLayer className="mp-change" kind={story.change.kind} frames={frames} index={a} playing={playing} onIndex={setA} refCount={refCount} epicentre={epi} revealAt={story.change.kind === 'quake' ? revealAt : -1} />
				)}
				{showB && (
					<div ref={after} className="mp-after">
						<Fader src={pb!.img} alt={`NISAR ${place.name}, ${span(pb!)}`} />
					</div>
				)}
			</div>

			{showB && (
				<div ref={swipeEl} className="mp-swipe" style={{ left: `${swipe * 100}%` }} onPointerDown={drag} role="slider" aria-label="Compare the two passes" aria-valuenow={Math.round(swipe * 100)} aria-valuemin={0} aria-valuemax={100} tabIndex={0}>
					<span className="mp-swipe-tag mp-swipe-a">{span(pa)}</span>
					<span className="mp-swipe-knob">
						<Columns2 size={16} strokeWidth={2.2} />
					</span>
					<span className="mp-swipe-tag mp-swipe-b">{span(pb!)}</span>
				</div>
			)}

			{allPlaces.map((p, k) => (
				<button
					key={`${p.key}-${p.place}`}
					ref={(n) => void (pins.current[k] = n)}
					type="button"
					className="mp-pin"
					data-on={(!overview && p.story === si && p.place === pi) || undefined}
					onClick={() => choose(p.story, p.place)}
				>
					<img src={`/img/icons/${p.key}.webp`} alt="" width={40} height={40} />
					<span>{p.name}</span>
				</button>
			))}

			<aside className="mp-rail">
				<Link href="/" className="mp-brand" aria-label="Back to the landing">
					<Mark size={20} />
					<span className="display">Dancing with the SARs</span>
				</Link>
				<button type="button" className="mp-all" data-on={overview || undefined} onClick={() => setOverview(true)}>
					<Globe2 size={18} strokeWidth={1.9} />
					All places
				</button>
				<ul className="mp-stories">
					{stories.map((s, i) => (
						<li key={s.key}>
							<button type="button" onClick={() => choose(i)} data-on={(!overview && i === si) || undefined}>
								<img src={`/img/icons/${s.key}.webp`} alt="" width={52} height={52} />
								<span>
									<b>{s.tab}</b>
									<small>{s.where}</small>
								</span>
							</button>
						</li>
					))}
				</ul>
				<div className="mp-rail-foot">
					<Link href="/" className="mp-back">
						<ArrowLeft size={15} strokeWidth={2} /> Landing
					</Link>
					<PaletteSwitch />
				</div>
			</aside>

			{!overview && (
				<aside className="mp-card">
					<p className="mp-kind">{story.kind}</p>
					<h1 className="display">{story.title}</h1>
					<p className="mp-what">{story.what}</p>
					{view === 'change' && !showB && (
						<p className="mp-legend">
							<span className={`mp-swatch mp-swatch-${story.change.kind}`} aria-hidden />
							<span>
								{story.change.legend}
								<small>Animated from the radar previews: a quick estimate, not the project&apos;s models.</small>
							</span>
						</p>
					)}
					{story.places.length > 1 && (
						<div className="mp-places">
							{story.places.map((p, i) => (
								<button key={p.site} type="button" data-on={i === pi || undefined} onClick={() => choose(si, i)}>
									{p.name}
								</button>
							))}
						</div>
					)}
					<a className="mp-proof" href={`https://cmr.earthdata.nasa.gov/search/granules.json?readable_granule_name=${encodeURIComponent(cur.granule)}`} target="_blank" rel="noopener noreferrer">
						<span>
							Data record, NASA CMR
							<small className="mono">
								{place.product} · track {track.label} · {cur.crid === 'P05036' ? 'validated' : 'provisional'}
							</small>
						</span>
						<ArrowUpRight size={16} strokeWidth={2} />
					</a>
				</aside>
			)}

			{overview ? (
				<div className="mp-dock mp-dock-hint">
					<Globe2 size={18} strokeWidth={1.9} /> Pick a place on the map, or a story on the left.
				</div>
			) : (
				<div className="mp-dock">
					<div className="mp-cmds">
						<button type="button" className="mp-icon" onClick={() => step(-1)} aria-label="Previous pass">
							<ChevronLeft size={20} strokeWidth={2.2} />
						</button>
						<button
							type="button"
							className="mp-play"
							onClick={() => {
								setCompare(false)
								setPlaying((v) => !v)
							}}
						>
							{playing ? <Pause size={17} strokeWidth={2.4} /> : <Play size={17} strokeWidth={2.4} />}
							{playing ? 'Pause' : 'Play season'}
						</button>
						<button type="button" className="mp-icon" onClick={() => step(1)} aria-label="Next pass">
							<ChevronRight size={20} strokeWidth={2.2} />
						</button>
						<div className="mp-date">
							{compare && pb ? (
								<span className="mp-sides">
									<button type="button" data-on={side === 'a' || undefined} onClick={() => setSide('a')}>
										<small>Before</small>
										{span(pa)}
									</button>
									<button type="button" data-on={side === 'b' || undefined} onClick={() => setSide('b')}>
										<small>After</small>
										{span(pb)}
									</button>
								</span>
							) : (
								<>
									<b>{span(pa)} 2026</b>
									<small className="mono">
										pass {String(idx + 1).padStart(2, '0')} of {String(n).padStart(2, '0')}
									</small>
								</>
							)}
						</div>
						<div className="mp-view" role="group" aria-label="View">
							<button
								type="button"
								data-on={(view === 'change' && !compare) || undefined}
								onClick={() => {
									setCompare(false)
									setView('change')
								}}
							>
								<Waves size={16} strokeWidth={2.1} /> Change
							</button>
							<button type="button" data-on={(view === 'radar' && !compare) || undefined} onClick={() => setView('radar')}>
								<ImageIcon size={16} strokeWidth={2.1} /> Radar
							</button>
						</div>
						<button type="button" className="mp-compare" data-on={compare || undefined} onClick={toggleCompare}>
							<Columns2 size={17} strokeWidth={2.1} />
							Compare
						</button>
					</div>
					<div className="mp-ticks">
						{track.passes.map((p, i) => (
							<button
								key={p.img}
								type="button"
								style={{ left: `${ticks.at[i] * 100}%` }}
								data-a={i === a || undefined}
								data-b={(compare && i === b) || undefined}
								onClick={() => {
									setPlaying(false)
									if (compare && side === 'b') setB(i)
									else setA(i)
								}}
								aria-label={`Show ${span(p)}`}
								title={span(p)}
							>
								<span />
							</button>
						))}
						{ticks.months.map((m) => (
							<em key={m.label} style={{ left: `${m.at * 100}%` }}>
								{m.label}
							</em>
						))}
					</div>
				</div>
			)}
		</div>
	)
}
