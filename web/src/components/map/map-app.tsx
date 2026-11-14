'use client'

import 'maplibre-gl/dist/maplibre-gl.css'
import { ArrowLeft, ArrowUpRight, Columns2, Pause, Play, Square } from 'lucide-react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Mark } from '../brand'
import { ThemeToggle } from '../theme-toggle'
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
	places: Place[]
	initial: { pi: number; ti: number; a: number; b: number | null }
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dd = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`
const span = (p: PassView) => p.dates.map(dd).join(' > ')
const PRODUCT = {
	GCOV: 'Radar brightness · HH and HV · 20 m',
	GUNW: 'Ground motion pairs · 12 days apart · 80 m',
}
const TILES = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg'

/** An image that cross-fades when its source changes: the new one fades in over the old, then the old is dropped. */
function Fader({ src, alt, className, style }: { src: string; alt: string; className?: string; style?: React.CSSProperties }) {
	const [layers, setLayers] = useState([{ src, id: 0 }])
	useEffect(() => {
		setLayers((l) => (l[l.length - 1].src === src ? l : [...l.slice(-1), { src, id: l[l.length - 1].id + 1 }]))
		const t = window.setTimeout(() => setLayers((l) => l.slice(-1)), 520)
		return () => window.clearTimeout(t)
	}, [src])
	return (
		<div className={className} style={style}>
			{layers.map((l, i) => (
				<img key={l.id} src={l.src} alt={i === layers.length - 1 ? alt : ''} data-new={i === layers.length - 1 || undefined} />
			))}
		</div>
	)
}

/**
 * The map app. Landtrack's full-bleed map with floating glass panels and EarthEye's layers-on-the-left, figures-on-
 * the-right, with a cleaner rail: the four stories with their 3D icons, then place, track and layer. The radar is
 * the real NISAR preview, placed on its box by projecting the box corners on every move; the swipe compare clips the
 * second pass at the handle. Every pass links to its granule record, so each picture carries its proof.
 */
export function MapApp({ stories }: { stories: StoryCfg[] }) {
	const mapEl = useRef<HTMLDivElement>(null)
	const mapRef = useRef<MapLibreMap | null>(null)
	const ov = useRef<HTMLDivElement>(null)
	const after = useRef<HTMLDivElement>(null)
	const swipeEl = useRef<HTMLDivElement>(null)
	const swipeRef = useRef(0.5)
	const [ready, setReady] = useState(false)
	const [si, setSi] = useState(0)
	const [pi, setPi] = useState(stories[0].initial.pi)
	const [ti, setTi] = useState(stories[0].initial.ti)
	const [a, setA] = useState(stories[0].initial.a)
	const [b, setB] = useState<number | null>(stories[0].initial.b)
	const [compare, setCompare] = useState(stories[0].initial.b != null)
	const [slot, setSlot] = useState<'a' | 'b'>('a')
	const [playing, setPlaying] = useState(false)
	const [swipe, setSwipe] = useState(0.5)
	const [radarOn, setRadarOn] = useState(true)
	const [opacity, setOpacity] = useState(1)

	const story = stories[si]
	const place = story.places[Math.min(pi, story.places.length - 1)]
	const track = place.tracks[Math.min(ti, place.tracks.length - 1)]
	const n = track.passes.length
	const pa = track.passes[Math.min(a, n - 1)]
	const pb = b != null ? track.passes[Math.min(b, n - 1)] : null
	const showB = compare && pb != null

	const choose = useCallback(
		(i: number) => {
			const s = stories[i]
			setSi(i)
			setPi(s.initial.pi)
			setTi(s.initial.ti)
			setA(s.initial.a)
			setB(s.initial.b)
			setCompare(s.initial.b != null)
			setSlot('a')
			setPlaying(false)
			try {
				history.replaceState(null, '', `/map?story=${s.key}`)
			} catch {}
		},
		[stories],
	)

	// a story from the link (?story=fire) on arrival
	useEffect(() => {
		const k = new URLSearchParams(window.location.search).get('story')
		const i = stories.findIndex((s) => s.key === k)
		if (i > 0) choose(i)
	}, [stories, choose])

	// place the radar box on the map: project its corners, clip the second pass at the handle
	const layout = useCallback(() => {
		const map = mapRef.current
		const el = ov.current
		if (!map || !el) return
		const [w, s, e, nn] = place.box
		const tl = map.project([w, nn])
		const br = map.project([e, s])
		const ww = br.x - tl.x
		const hh = br.y - tl.y
		el.style.transform = `translate3d(${tl.x}px, ${tl.y}px, 0)`
		el.style.width = `${ww}px`
		el.style.height = `${hh}px`
		if (after.current) {
			const x = swipeRef.current * map.getContainer().clientWidth - tl.x
			after.current.style.clipPath = `inset(0 0 0 ${Math.min(ww, Math.max(0, x))}px)`
		}
		// the handle spans the radar box only, so its knob always sits on the picture
		if (swipeEl.current) {
			swipeEl.current.style.top = `${tl.y}px`
			swipeEl.current.style.height = `${hh}px`
		}
	}, [place.box])

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
					layers: [{ id: 's2', type: 'raster', source: 's2', paint: { 'raster-saturation': -0.35, 'raster-contrast': 0.05 } }],
				},
				bounds: [
					[w, s],
					[e, nn],
				],
				maxZoom: 12.5,
				minZoom: 3,
				dragRotate: false,
				pitchWithRotate: false,
				attributionControl: { compact: true },
			})
			map.touchZoomRotate.disableRotation()
			mapRef.current = map
			map.on('load', () => {
				setReady(true)
				// on a phone the credits stay behind their info button (one tap away) instead of covering the map
				if (window.innerWidth <= 900) map?.getContainer().querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show')
			})
		})()
		return () => {
			gone = true
			map?.remove()
			mapRef.current = null
		}
	}, [stories])

	// keep the radar on its box while the map moves
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

	// fly to the place, leaving room for the rail, the panel and the timeline
	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		const wide = window.innerWidth > 900
		const [w, s, e, nn] = place.box
		map.fitBounds(
			[
				[w, s],
				[e, nn],
			],
			{ padding: wide ? { top: 96, bottom: 120, left: 360, right: 380 } : { top: 140, bottom: 170, left: 24, right: 24 }, duration: 1300, maxZoom: 11.2 },
		)
	}, [ready, place.box, si, pi])

	useEffect(() => {
		swipeRef.current = swipe
		layout()
	}, [swipe, showB, layout])

	// play through the track, one pass at a time
	useEffect(() => {
		if (!playing) return
		const id = window.setInterval(() => setA((v) => (v + 1) % n), 1100)
		return () => window.clearInterval(id)
	}, [playing, n])

	// arrow keys step through passes
	useEffect(() => {
		const on = (e: KeyboardEvent) => {
			if (e.target instanceof HTMLInputElement) return
			if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
			const d = e.key === 'ArrowRight' ? 1 : -1
			setPlaying(false)
			if (compare && slot === 'b') setB((v) => Math.min(n - 1, Math.max(0, (v ?? 0) + d)))
			else setA((v) => Math.min(n - 1, Math.max(0, v + d)))
		}
		window.addEventListener('keydown', on)
		return () => window.removeEventListener('keydown', on)
	}, [compare, slot, n])

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

	const pick = (i: number) => {
		setPlaying(false)
		if (compare && slot === 'b') setB(i)
		else setA(i)
	}
	const toggleCompare = (on: boolean) => {
		setPlaying(false)
		setCompare(on)
		if (on && b == null) setB(Math.min(n - 1, a + Math.max(1, Math.floor(n / 2))))
		if (on) setSlot('b')
		else setSlot('a')
	}
	const shownPass = compare && slot === 'b' && pb ? pb : pa

	return (
		<div className="mp">
			<div ref={mapEl} className="mp-map" />
			<div className="mp-wash" aria-hidden />

			<div ref={ov} className="mp-ov" data-on={(radarOn && ready) || undefined} style={{ opacity }}>
				<Fader className="mp-layer" src={pa.img} alt={`NISAR ${place.name}, ${span(pa)}`} />
				{showB && (
					<div ref={after} className="mp-after">
						<Fader className="mp-layer" src={pb!.img} alt={`NISAR ${place.name}, ${span(pb!)}`} />
					</div>
				)}
			</div>

			{showB && radarOn && (
				<div ref={swipeEl} className="mp-swipe" style={{ left: `${swipe * 100}%` }} onPointerDown={drag} role="slider" aria-label="Compare" aria-valuenow={Math.round(swipe * 100)} aria-valuemin={0} aria-valuemax={100} tabIndex={0}>
					<span className="mp-swipe-a">{span(pa)}</span>
					<span className="mp-swipe-knob">
						<Columns2 size={16} strokeWidth={2} />
					</span>
					<span className="mp-swipe-b">{span(pb!)}</span>
				</div>
			)}

			<aside className="mp-rail">
				<Link href="/" className="mp-brand">
					<Mark size={20} />
					<span className="display">Dancing with the SARs</span>
				</Link>

				<p className="mp-label">Stories</p>
				<ul className="mp-stories">
					{stories.map((s, i) => {
						const count = s.places.reduce((m, p) => m + p.tracks.reduce((k, t) => k + t.passes.length, 0), 0)
						return (
							<li key={s.key}>
								<button type="button" onClick={() => choose(i)} data-on={i === si || undefined}>
									<img src={`/img/icons/${s.key}.webp`} alt="" width={44} height={44} />
									<span>
										<b>{s.tab}</b>
										<small>{s.places.map((p) => p.name).join(' · ')}</small>
									</span>
									<i className="mono">{count}</i>
								</button>
							</li>
						)
					})}
				</ul>

				{story.places.length > 1 && (
					<>
						<p className="mp-label">Place</p>
						<div className="mp-seg">
							{story.places.map((p, i) => (
								<button
									key={p.site}
									type="button"
									data-on={i === pi || undefined}
									onClick={() => {
										setPi(i)
										setTi(0)
										setA(story.places[i].tracks[0].passes.length - 1)
										setB(null)
										setCompare(false)
										setSlot('a')
									}}
								>
									{p.name}
								</button>
							))}
						</div>
					</>
				)}

				<p className="mp-label">Track</p>
				<div className="mp-seg">
					{place.tracks.map((t, i) => (
						<button
							key={t.id}
							type="button"
							data-on={i === ti || undefined}
							onClick={() => {
								setTi(i)
								setA(t.passes.length - 1)
								setB(null)
								setCompare(false)
								setSlot('a')
								setPlaying(false)
							}}
						>
							<span className="mono">{t.label}</span>
							<small>{t.passes.length}</small>
						</button>
					))}
				</div>

				<p className="mp-label">Layer</p>
				<label className="mp-switch">
					<span>
						<b>NISAR {place.product}</b>
						<small>{PRODUCT[place.product]}</small>
					</span>
					<input type="checkbox" checked={radarOn} onChange={(e) => setRadarOn(e.target.checked)} />
					<i aria-hidden />
				</label>
				<label className="mp-range">
					<small>Opacity</small>
					<input type="range" min={0.2} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} />
				</label>

				<div className="mp-rail-foot">
					<Link href="/" className="mp-back">
						<ArrowLeft size={15} strokeWidth={2} /> Landing
					</Link>
					<ThemeToggle />
				</div>
			</aside>

			<div className="mp-top">
				<span className="mp-crumb">
					<b>{place.name}</b>
					<i className="mono">{track.label}</i>
				</span>
				<div className="mp-view" role="group" aria-label="View">
					<button type="button" data-on={!compare || undefined} onClick={() => toggleCompare(false)}>
						<Square size={14} strokeWidth={2} /> Single
					</button>
					<button type="button" data-on={compare || undefined} onClick={() => toggleCompare(true)}>
						<Columns2 size={14} strokeWidth={2} /> Compare
					</button>
				</div>
			</div>

			<aside className="mp-panel">
				<img className="mp-icon" src={`/img/icons/${story.key}.webp`} alt="" width={76} height={76} />
				<p className="mp-eyebrow">
					{story.n} · {story.kind}
				</p>
				<h1 className="display">{story.title}</h1>
				<p className="mp-what">{story.what}</p>
				<dl>
					<div>
						<dt>Place</dt>
						<dd>{place.name}</dd>
					</div>
					<div>
						<dt>Product</dt>
						<dd>NISAR L2 {place.product}</dd>
					</div>
					<div>
						<dt>Track</dt>
						<dd className="mono">
							{track.label} · {n} {place.product === 'GUNW' ? 'pairs' : 'passes'}
						</dd>
					</div>
					<div>
						<dt>{showB ? 'Comparing' : 'Shown'}</dt>
						<dd className="mono">{showB ? `${span(pa)} | ${span(pb!)}` : span(pa)}</dd>
					</div>
				</dl>
				<p className="mp-note">{story.note}</p>
				<a className="mp-proof" href={`https://cmr.earthdata.nasa.gov/search/granules.json?readable_granule_name=${encodeURIComponent(shownPass.granule)}`} target="_blank" rel="noopener noreferrer">
					<span>
						Granule record, NASA CMR
						<small className="mono">{shownPass.crid === 'P05036' ? 'Validated' : 'Provisional'} · {shownPass.collection.replace('NISAR_L2_', '').replace(/_/g, ' ')}</small>
					</span>
					<ArrowUpRight size={16} strokeWidth={2} />
				</a>
			</aside>

			<div className="mp-time">
				<button type="button" className="mp-play" onClick={() => {
						if (compare) toggleCompare(false)
						setPlaying((v) => !v)
					}} aria-label={playing ? 'Pause' : 'Play every pass'}>
					{playing ? <Pause size={16} strokeWidth={2.2} /> : <Play size={16} strokeWidth={2.2} />}
				</button>
				{compare && (
					<div className="mp-slots">
						<button type="button" data-on={slot === 'a' || undefined} onClick={() => setSlot('a')}>
							<b>A</b> {dd(pa.dates[pa.dates.length - 1])}
						</button>
						<button type="button" data-on={slot === 'b' || undefined} onClick={() => setSlot('b')}>
							<b>B</b> {pb ? dd(pb.dates[pb.dates.length - 1]) : 'pick'}
						</button>
					</div>
				)}
				<div className="mp-ticks">
					{track.passes.map((p, i) => (
						<button
							key={p.img}
							type="button"
							style={{ left: `${ticks.at[i] * 100}%` }}
							data-a={i === a || undefined}
							data-b={(compare && i === b) || undefined}
							onClick={() => pick(i)}
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
				<span className="mp-count mono">
					{String((compare && slot === 'b' && b != null ? b : a) + 1).padStart(2, '0')} / {String(n).padStart(2, '0')}
				</span>
			</div>
		</div>
	)
}
