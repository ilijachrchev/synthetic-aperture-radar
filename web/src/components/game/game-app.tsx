'use client'

// The flood game on the map. Three steps: the brief (the marsh before the storm, the rain that was forecast), the
// picks (the player marks cells on a grid over the marsh), the reveal (the pass after the storm, the score, and for
// every cell the reason it flooded or stayed dry). The map is the page; the words sit in one panel.
//
// What is drawn is what the radar measured: the pass before, then the pass after, nothing in between. The cells
// were measured once by scripts/bake_game.py, so the page only compares numbers.

import 'maplibre-gl/dist/maplibre-gl.css'
import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { GAME } from '@/content/game'
import type { RainFile } from '@/lib/flood-model'
import { TERRAIN } from '@/lib/scene3d'
import { maxZoomOf, tilesOf, transformTile } from '@/lib/tiles'
import { WaterLayer, type WaterMeta } from '@/lib/water-layer'
import './game.css'

const maplibre =
	typeof window === 'undefined'
		? null
		: import('maplibre-gl').then((m) => {
				m.setWorkerUrl(`/maplibre/maplibre-gl-worker.mjs?v=${m.getVersion()}`)
				m.setMaxParallelImageRequests(32)
				m.prewarm()
				return m
			})

/** one cell of the playfield, as game.json records it (scripts/bake_game.py) */
type Cell = {
	i: number
	r: number
	c: number
	/** west, south, east, north */
	box: [number, number, number, number]
	land: number
	before: number
	new: number
	gone: number
	hidden: number
	ems: number
	elev: number | null
	elev_min: number | null
	new_ha: number
	flood: boolean
}
type Game = {
	cell_m: number
	flood_share: number
	grid: { rows: number; cols: number; box: [number, number, number, number] }
	before: { frame: number; time_utc: string; water_ha: number }
	after: { frame: number; time_utc: string; water_ha: number }
	s1_after: { frame: number; time_utc: string; water_ha: number }
	totals: { cells: number; flooded: number; new_ha: number; hidden_ha: number; ems_ha: number | null; new_in_ems: number | null }
	cells: Cell[]
}
type Data = { meta: WaterMeta; game: Game; rain: RainFile | null }
type Phase = 'brief' | 'pick' | 'reveal'
/** how a cell is drawn: marked by the player, then after the reveal a hit, a miss, or a flooded cell nobody marked */
type Mark = 'none' | 'pick' | 'hit' | 'miss' | 'late'

const day =(iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const pct = (v: number) => `${Math.round(v * 100)}%`

function useData() {
	const [data, setData] = useState<Data | null>(null)
	const [error, setError] = useState<string | null>(null)
	useEffect(() => {
		let gone = false
		const get = async <T,>(file: string, optional = false): Promise<T | null> => {
			const r = await fetch(`${GAME.root}/${file}`)
			if (!r.ok) {
				if (optional) return null
				throw new Error(`${file}: ${r.status}`)
			}
			return (await r.json()) as T
		}
		Promise.all([get<WaterMeta>('meta.json'), get<Game>('game.json'), get<RainFile>('rain.json', true)])
			.then(([meta, game, rain]) => {
				if (!gone && meta && game) setData({ meta, game, rain })
			})
			.catch((e: Error) => !gone && setError(e.message))
		return () => {
			gone = true
		}
	}, [])
	return { data, error }
}

/** the rain of the storm itself, from the hourly file of the flood story */
function stormRain(rain: RainFile | null) {
	if (!rain) return null
	const t0 = Date.parse(GAME.storm.from)
	const t1 = Date.parse(GAME.storm.to)
	let mm = 0
	for (const h of rain.hours) {
		const t = Date.parse(h.t)
		if (t >= t0 && t < t1) mm += h.mm
	}
	return Math.round(mm)
}

/** why a cell flooded or stayed dry, in the words of the measurements */
function why(cell: Cell, game: Game): string[] {
	const lines: string[] = []
	const m = cell.elev ?? 0
	if (cell.flood) {
		lines.push(`Flooded: ${cell.new_ha} ha of new water on ${day(game.after.time_utc)}.`)
		if (cell.before >= 0.2) lines.push(`It held water before the storm already (${pct(cell.before)} of the cell): the marsh grew out from here.`)
		else if (m <= 2) lines.push(`The ground lies ${m.toFixed(1)} m above the sea, where the marsh drains: the water had nowhere lower to go.`)
		else lines.push(`The ground lies ${m.toFixed(1)} m above the sea, the lowest point at ${(cell.elev_min ?? m).toFixed(1)} m.`)
		if (cell.hidden >= 0.25)
			lines.push(
				`Sentinel-1 passed the same evening and drew ${pct(cell.hidden)} of this new water as land. NISAR's longer L-band waves reach further into reeds and wet crops than Sentinel-1's C band, one reason the two radars disagree here.`,
			)
		if (cell.ems < 0.3) lines.push(`The Copernicus emergency map of 20 to 21 Oct had no water here. A week later NISAR found some.`)
	} else {
		lines.push(`Not flooded: ${pct(cell.new)} of the land was new water on ${day(game.after.time_utc)}, under the ${pct(game.flood_share)} a cell needs.`)
		if (cell.before >= 0.5) lines.push(`It was water before the storm already: nothing new for the radar to find.`)
		else if (m > 12) lines.push(`It lies ${Math.round(m)} m above the sea: rain runs off it, down to the marsh.`)
		else if (cell.ems >= 0.3) lines.push(`The Copernicus emergency map of 20 to 21 Oct had water here (${pct(cell.ems)} of the cell). By the pass of ${day(game.after.time_utc)}, a week later, the radar found it dry again.`)
		else if (m <= 3) lines.push(`Low ground (${m.toFixed(1)} m), yet dry on the radar: drains, pumps and banks decide where the water settles, not height alone.`)
		else lines.push(`The ground lies ${m.toFixed(1)} m above the sea, a little above the marsh: this time the water stayed below it.`)
		if (cell.gone >= 0.1) lines.push(`${pct(cell.gone)} of it was water before the storm and dry after: fields drained for the harvest, or water the radar could not tell from wet soil.`)
	}
	return lines
}

/** the rule a careful person could follow without a radar: the lowest cells that are not water already */
function lowestRule(cells: Cell[], n: number) {
	return cells
		.filter((c) => c.before < 0.5 && c.elev !== null)
		.sort((a, b) => (a.elev ?? 0) - (b.elev ?? 0))
		.slice(0, n)
}

export function GameApp() {
	const { data, error } = useData()
	const mapEl = useRef<HTMLDivElement>(null)
	const mapRef = useRef<MapLibreMap | null>(null)
	const nisar = useRef<WaterLayer | null>(null)
	const s1 = useRef<WaterLayer | null>(null)
	const [ready, setReady] = useState(false)
	const [phase, setPhase] = useState<Phase>('brief')
	const [picked, setPicked] = useState<Set<number>>(() => new Set())
	const [focus, setFocus] = useState<number | null>(null)
	const [relief, setRelief] = useState(true)
	const [compare, setCompare] = useState(false)
	const [split, setSplit] = useState(0.5)
	const phaseRef = useRef(phase)
	useEffect(() => {
		phaseRef.current = phase
	}, [phase])

	const game = data?.game ?? null
	const flooded = useMemo(() => game?.cells.filter((c) => c.flood) ?? [], [game])
	const score = useMemo(() => {
		if (!game) return null
		const hits = [...picked].filter((i) => game.cells[i]?.flood).length
		const rule = lowestRule(game.cells, GAME.picks)
		return {
			hits,
			ruleHits: rule.filter((c) => c.flood).length,
			chance: (GAME.picks * flooded.length) / game.cells.length,
		}
	}, [game, picked, flooded])
	const storm = useMemo(() => stormRain(data?.rain ?? null), [data])

	// the map, once the data is here
	useEffect(() => {
		if (!data || !mapEl.current || !maplibre) return
		let gone = false
		let map: MapLibreMap | null = null
		const { meta, game } = data
		maplibre.then(({ Map }) => {
			if (gone || !mapEl.current) return
			const small = window.matchMedia('(max-width: 720px)').matches
			// a phone opens on the middle of the playfield, so a cell is wide enough for a thumb; the rest is a pan away
			const [w, s, e, n] = game.grid.box
			const inset = small ? 0.22 : 0
			const bounds: [number, number, number, number] = [w + (e - w) * inset, s + (n - s) * inset, e - (e - w) * inset, n - (n - s) * inset]
			map = new Map({
				container: mapEl.current,
				transformRequest: transformTile,
				style: {
					version: 8,
					sources: {
						base: { type: 'raster', tiles: [tilesOf('base')], tileSize: 256, maxzoom: maxZoomOf('base') },
						names: { type: 'raster', tiles: [tilesOf('names')], tileSize: 256, maxzoom: maxZoomOf('names') },
						dem: TERRAIN.source,
					},
					layers: [
						{ id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.82 } },
						// the relief: the one clue to low ground the player gets, drawn as light and shade
						{ id: 'hill', type: 'hillshade', source: 'dem', paint: { 'hillshade-exaggeration': 0.45, 'hillshade-shadow-color': '#1a2733', 'hillshade-highlight-color': '#ffffff' } },
						{ id: 'names', type: 'raster', source: 'names', maxzoom: 11.5, paint: { 'raster-opacity': 0.75 } },
					],
				},
				bounds,
				fitBoundsOptions: { padding: small ? { top: 70, bottom: Math.round(window.innerHeight * 0.42), left: 8, right: 8 } : { top: 80, bottom: 40, left: 40, right: 420 } },
				minZoom: 8,
				maxZoom: 15,
				pitch: 0,
				bearing: 0,
				attributionControl: false,
				dragRotate: false,
			})
			mapRef.current = map
			map.touchZoomRotate.disableRotation()
			map.once('style.load', () => {
				if (gone || !map) return
				const series = meta.series.find((s) => s.id === GAME.series)
				const s1Series = meta.series.find((s) => s.id === 's1')
				if (!series) return
				const water = new WaterLayer({ id: 'water-nisar', root: GAME.root, meta, series })
				nisar.current = water
				map.addLayer(water.layer)
				water.set({ a: game.before.frame, b: game.before.frame, gain: 0, loss: 0, observed: 1, ref: -1 })
				if (s1Series) {
					const other = new WaterLayer({ id: 'water-s1', root: GAME.root, meta, series: s1Series, style: { opacity: 0 } })
					s1.current = other
					map.addLayer(other.layer)
					other.set({ a: game.s1_after.frame, b: game.s1_after.frame, gain: 0, loss: 0, observed: 1, ref: -1 })
				}
				// the playfield: one square per cell, coloured by what the player did with it
				map.addSource('cells', {
					type: 'geojson',
					data: {
						type: 'FeatureCollection',
						features: game.cells.map((c) => ({
							type: 'Feature',
							id: c.i,
							properties: { i: c.i },
							geometry: { type: 'Polygon', coordinates: [[[c.box[0], c.box[1]], [c.box[2], c.box[1]], [c.box[2], c.box[3]], [c.box[0], c.box[3]], [c.box[0], c.box[1]]]] },
						})),
					},
				} as never)
				const mark = ['coalesce', ['feature-state', 'mark'], 'none']
				map.addLayer({
					id: 'cells-fill',
					type: 'fill',
					source: 'cells',
					paint: {
						'fill-color': ['match', mark, 'pick', '#ffd166', 'hit', '#7cf29a', 'miss', '#ff6b6b', 'late', '#8de6ff', 'rgba(0,0,0,0)'],
						'fill-opacity': ['match', mark, 'pick', 0.42, 'hit', 0.4, 'miss', 0.38, 'late', 0.18, 0],
					},
					layout: { visibility: 'none' },
				} as never)
				map.addLayer({
					id: 'cells-line',
					type: 'line',
					source: 'cells',
					paint: {
						'line-color': ['match', mark, 'pick', '#ffd166', 'hit', '#7cf29a', 'miss', '#ff6b6b', 'late', '#8de6ff', 'rgba(255,255,255,0.35)'],
						'line-width': ['match', mark, 'none', 0.6, 1.8],
					},
					layout: { visibility: 'none' },
				} as never)
				map.addLayer({
					id: 'cells-focus',
					type: 'line',
					source: 'cells',
					paint: { 'line-color': '#ffffff', 'line-width': 3 },
					filter: ['==', ['id'], -1],
					layout: { visibility: 'none' },
				} as never)
				map.on('mouseenter', 'cells-fill', () => {
					if (map && phaseRef.current !== 'brief') map.getCanvas().style.cursor = 'pointer'
				})
				map.on('mouseleave', 'cells-fill', () => {
					if (map) map.getCanvas().style.cursor = ''
				})
				map.on('click', 'cells-fill', (e: MapMouseEvent & { features?: { id?: number | string }[] }) => {
					const id = e.features?.[0]?.id
					if (typeof id !== 'number') return
					if (phaseRef.current === 'pick') {
						setPicked((was) => {
							const next = new Set(was)
							if (next.has(id)) next.delete(id)
							else if (next.size < GAME.picks) next.add(id)
							else return was
							return next
						})
					} else if (phaseRef.current === 'reveal') setFocus((f) => (f === id ? null : id))
				})
				water.preloadAll()
				setReady(true)
			})
		})
		return () => {
			gone = true
			nisar.current = null
			s1.current = null
			mapRef.current = null
			map?.remove()
		}
	}, [data])

	// what the map shows in each step
	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready || !game) return
		const vis = phase === 'brief' ? 'none' : 'visible'
		for (const id of ['cells-fill', 'cells-line', 'cells-focus']) map.setLayoutProperty(id, 'visibility', vis)
		const frame = phase === 'reveal' ? game.after.frame : game.before.frame
		nisar.current?.set({ a: frame, b: frame, gain: 0, loss: 0, observed: 1, ref: phase === 'reveal' ? game.before.frame : -1 })
		if (phase === 'reveal') nisar.current?.flash()
		for (const c of game.cells) {
			let mark: Mark = 'none'
			const p = picked.has(c.i)
			if (phase === 'pick') mark = p ? 'pick' : 'none'
			else if (phase === 'reveal') mark = p ? (c.flood ? 'hit' : 'miss') : c.flood ? 'late' : 'none'
			map.setFeatureState({ source: 'cells', id: c.i }, { mark })
		}
		map.triggerRepaint()
	}, [phase, picked, ready, game])

	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		map.setFilter('cells-focus', ['==', ['id'], focus ?? -1] as never)
	}, [focus, ready])

	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		map.setLayoutProperty('hill', 'visibility', relief ? 'visible' : 'none')
	}, [relief, ready])

	// the comparison: Sentinel-1 of the same evening on the left of the line, NISAR on the right
	useEffect(() => {
		const on = compare && phase === 'reveal'
		s1.current?.setStyle({ opacity: on ? 1 : 0 })
		s1.current?.setClip(0, on ? split : 0)
		nisar.current?.setClip(on ? split : 0, 1)
		mapRef.current?.triggerRepaint()
	}, [compare, split, phase])

	const start = useCallback(() => setPhase('pick'), [])
	const reveal = useCallback(() => {
		setFocus(null)
		setPhase('reveal')
	}, [])
	const again = useCallback(() => {
		setPicked(new Set())
		setFocus(null)
		setCompare(false)
		setPhase('pick')
	}, [])

	const focused = focus !== null && game ? game.cells[focus] : null

	return (
		<div className="gm" data-ready={ready || undefined} data-phase={phase}>
			<div ref={mapEl} className="gm-map" />
			{compare && phase === 'reveal' && (
				<div className="gm-swipe" style={{ left: `${split * 100}%` }}>
					<span className="gm-swipe-tag gm-swipe-l">Sentinel-1, C band</span>
					<span className="gm-swipe-tag gm-swipe-r">NISAR, L band</span>
				</div>
			)}
			{compare && phase === 'reveal' && (
				<input className="gm-split" type="range" min={0.05} max={0.95} step={0.005} value={split} onChange={(e) => setSplit(Number(e.target.value))} aria-label="Where the comparison splits" />
			)}

			<header className="gm-top">
				<Link href="/flood" className="gm-back">
					Stories
				</Link>
				<div className="gm-title">
					<span className="display">{GAME.title}</span>
					<span className="gm-place mono">{GAME.place}</span>
				</div>
			</header>

			{error && <div className="gm-error">The game could not load its data: {error}</div>}

			<aside className="gm-panel">
				{phase === 'brief' && game && (
					<>
						<p className="gm-step mono">Step 1 of 3 · {day(game.before.time_utc)}, 18:53 UTC</p>
						<p className="gm-big">
							<b className="mono">{Math.round(game.before.water_ha)}</b> ha of water
						</p>
						{GAME.brief.map((line) => (
							<p key={line}>{line}</p>
						))}
						<button type="button" className="gm-btn gm-primary" onClick={start} disabled={!ready}>
							Mark {GAME.picks} cells
						</button>
					</>
				)}
				{phase === 'pick' && game && (
					<>
						<p className="gm-step mono">Step 2 of 3 · your picks</p>
						<p className="gm-big">
							<b className="mono">{picked.size}</b> of {GAME.picks} marked
						</p>
						<p>
							Each cell is {game.cell_m} m across. Tap a cell to mark it, tap again to clear it. The shade of the hills shows where the ground is low.
						</p>
						<label className="gm-toggle">
							<input type="checkbox" checked={relief} onChange={(e) => setRelief(e.target.checked)} /> Relief
						</label>
						<div className="gm-row">
							<button type="button" className="gm-btn gm-primary" onClick={reveal} disabled={picked.size === 0}>
								Show the next pass
							</button>
							<button type="button" className="gm-btn" onClick={() => setPicked(new Set())} disabled={picked.size === 0}>
								Clear
							</button>
						</div>
					</>
				)}
				{phase === 'reveal' && game && score && (
					<>
						<p className="gm-step mono">Step 3 of 3 · {day(game.after.time_utc)}, 18:53 UTC</p>
						<p className="gm-big">
							<b className="mono">{score.hits}</b> of {picked.size} right
						</p>
						<p>
							{storm !== null ? `${storm} mm fell on 18 and 19 Oct, against the ${GAME.alert.mm3d} mm forecast. ` : ''}
							The radar found <b>{Math.round(game.totals.new_ha)} ha</b> of new water in {flooded.length} cells. Marking the {GAME.picks} lowest cells would have found{' '}
							<b>{score.ruleHits}</b>; marking at random, about {score.chance.toFixed(1)}.
						</p>
						<ul className="gm-key">
							<li>
								<i style={{ background: '#7cf29a' }} /> right
							</li>
							<li>
								<i style={{ background: '#ff6b6b' }} /> stayed dry
							</li>
							<li>
								<i style={{ background: '#8de6ff' }} /> flooded, not marked
							</li>
						</ul>
						<p className="gm-hint">Tap any cell to read why.</p>
						{focused && (
							<div className="gm-why" data-flood={focused.flood || undefined}>
								<p className="mono gm-why-head">
									Cell {String.fromCharCode(65 + focused.r)}
									{focused.c + 1} · {picked.has(focused.i) ? 'you marked it' : 'not marked'}
								</p>
								{why(focused, game).map((line) => (
									<p key={line}>{line}</p>
								))}
							</div>
						)}
						<label className="gm-toggle">
							<input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} /> Compare with Sentinel-1 of the same evening
						</label>
						{compare && (
							<p className="gm-hint">
								Drag the line. Two radars, one evening: Sentinel-1 drew {Math.round(game.s1_after.water_ha)} ha of water and flooded plants, NISAR {Math.round(game.after.water_ha)} ha. They disagree in places: {Math.round(game.totals.hidden_ha)} ha of NISAR&apos;s new water is land on the Sentinel-1 map, and Sentinel-1 draws water where NISAR sees none.
							</p>
						)}
						<div className="gm-row">
							<button type="button" className="gm-btn gm-primary" onClick={again}>
								Play again
							</button>
							<Link href="/flood" className="gm-btn">
								Watch the whole flood
							</Link>
						</div>
					</>
				)}
				{!game && !error && <p className="gm-hint">Loading the radar passes</p>}
			</aside>
			<p className="gm-credit">{GAME.credit}</p>
		</div>
	)
}
