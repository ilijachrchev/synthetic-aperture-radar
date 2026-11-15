'use client'

// The flat flood explorer: a street map, flat and sharp down to the houses, of the official flood zones (SNCZI), what
// really flooded (Copernicus EMS in 2024 and 2026, NISAR in 2026), and our model of where the water would go, with
// its rain slider and its honest notes. A click on any spot reads every layer there. A short replay walks through the
// DANA of 2026 at Pego-Oliva, our maps in order and no score.
//
// Everything that is a measurement comes from the baked files: public/layers/explore/ (scripts/bake_explore.py) and
// public/layers/<site>/prediction* (scripts/bake_prediction.py). The radar and model pictures are 15 to 20 m pixels:
// at street level they fade out and the sharp outlines and buildings stay.

import 'maplibre-gl/dist/maplibre-gl.css'
import { Layers, Pause, Play, X } from 'lucide-react'
import type { MapGeoJSONFeature, Map as MapLibreMap, MapMouseEvent, Marker as MapLibreMarker, PointLike } from 'maplibre-gl'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CREDITS, DEFAULT_LAYERS, ICV, LEGEND, type LayerKey, PLACES, PNOA, START, STREET_FADE, ZONES } from '@/content/explore'
import { DANA } from '@/content/stories'
import { utcDay } from '@/lib/flood-model'
import type { Bounds } from '@/lib/gl-quad'
import { LikelihoodLayer } from '@/lib/likelihood-layer'
import { PREDICTION_SITES, type Prediction, fileUrl, inBounds, inspectAt, loadPrediction, pixelAt, readPixel } from '@/lib/prediction'
import { emptyLayer } from '@/lib/scene3d'
import { ExploreSpot, type ExploreSpotInfo, type ExploreSpotResult } from './explore-spot'
import { RainSlider } from './rain-slider'
import './explore.css'

const maplibre =
	typeof window === 'undefined'
		? null
		: import('maplibre-gl').then((m) => {
				m.setWorkerUrl(`/maplibre/maplibre-gl-worker.mjs?v=${m.getVersion()}`)
				m.setMaxParallelImageRequests(16)
				m.prewarm()
				return m
			})

const ROOT = '/layers/explore'
type Picture = { file: string; bytes?: number }
type NisarSite = {
	stack: string
	before: string
	after: string
	bounds: Bounds
	size: [number, number]
	pictures: { before: Picture; after: Picture }
	open_water: { before_ha: number; after_ha: number; new_ha: number; on_both_ha: number; gone_ha: number }
	still?: { file: string; date: string; outline_ha: number; seen_ha: number; open_water_ha: number; open_water_share: number; source: string }
	data: { file: string; planes: string[] }
	sources: Record<string, string>
}
type ExploreIndex = { baked_utc: string; vectors: Record<string, { file: string; source: string }>; sites: Record<string, { name: string; nisar: NisarSite | null }> }
type Base = 'pnoa' | 'icv'

/** the vector layers of bake_explore.py: a source each, a hit layer each (always on, never seen: a click reads it
 *  whatever the legend shows) and the layers the legend switches */
const ZONE_SOURCES = ['zones_horta_sud', 'zones_pego_oliva']
const FLOODS = [
	{ key: 'floods_2024', year: 2024, code: 'EMSR773' },
	{ key: 'floods_2026', year: 2026, code: 'EMSR935' },
]
const zoneColor = ['match', ['get', 'zone'], 'frequent', ZONES[0].color, 'occasional', ZONES[1].color, 'rare', ZONES[2].color, '#ffffff'] as const
/** the legend's switches and the map layers they show */
const SHOWS: Record<LayerKey, string[]> = {
	zones: ZONE_SOURCES.map((s) => `${s}-line`),
	floods2024: ['floods_2024-fill', 'floods_2024-line'],
	buildings2024: ['buildings_2024'],
	floods2026: ['floods_2026-fill', 'floods_2026-line'],
	nisar: ['nisar-pego_oliva', 'nisar-albufera'],
	still: ['still-pego_oliva'],
	model: [],
	flow: [],
	depth: [],
}
/** the DANA replay: its steps, how long each holds while it plays, and the map layers of each */
const SCENES = 4
const SCENE_MS = 5600
const SCENE_LAYERS: string[][] = [['nisar0-pego_oliva'], [], ['nisar-pego_oliva', 'floods_2026-fill', 'floods_2026-line'], ['still-pego_oliva', 'floods_2026-line']]
const ALL_SHOWN = [...new Set([...Object.values(SHOWS).flat(), ...SCENE_LAYERS.flat()])]
const ha = (x: number) => Math.round(x).toLocaleString('en-US')
const day = (iso: string) => utcDay(Date.parse(iso.length === 10 ? `${iso}T12:00:00Z` : iso), false)
const smooth = (a: number, b: number, x: number) => {
	const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
	return t * t * (3 - 2 * t)
}

export function ExploreApp() {
	const mapEl = useRef<HTMLDivElement>(null)
	const mapRef = useRef<MapLibreMap | null>(null)
	const [idx, setIdx] = useState<ExploreIndex | null>(null)
	const [ready, setReady] = useState(false)
	const [layers, setLayers] = useState(DEFAULT_LAYERS)
	const [base, setBase] = useState<Base>('pnoa')
	const baseRef = useRef<Base>('pnoa')
	/** the legend on a phone, where it covers the map until it is asked for; on a wider screen it always shows */
	const [legendOpen, setLegendOpen] = useState(false)
	const [sources, setSources] = useState(false)
	const [error, setError] = useState<string | null>(null)

	// the model: prediction.json of both sites, a layer each, one rain for both
	const [preds, setPreds] = useState<Record<string, Prediction | null>>({})
	const models = useRef<Record<string, LikelihoodLayer>>({})
	const [rainIdx, setRainIdx] = useState(2)
	const rainPos = useRef(2)
	const [modelSite, setModelSite] = useState('pego_oliva')

	// the replay
	const [replaying, setReplaying] = useState(false)
	const [scene, setScene] = useState(0)
	const sceneRef = useRef(0)
	const [auto, setAuto] = useState(false)

	// a clicked spot
	const [spot, setSpot] = useState<{ result: ExploreSpotResult | null; loading: boolean } | null>(null)
	const spotMarker = useRef<MapLibreMarker | null>(null)
	const spotAt = useRef<{ lngLat: [number, number]; point: [number, number] } | null>(null)
	const spotSeq = useRef(0)

	const pego = preds.pego_oliva ?? null
	const rains = useMemo(() => (preds[modelSite] ?? pego)?.scenarios.filter((s) => s.rain_mm !== null) ?? [], [preds, modelSite, pego])
	const rain = rains[rainIdx]
	// the model map issued before the storm for the NISAR pass after it: the replay's second step
	const prestorm = useMemo(() => {
		const n = idx?.sites.pego_oliva?.nisar
		const storm = Date.parse(DANA.storm?.from ?? '')
		return pego && n ? (pego.replays.find((r) => r.target_time_utc.slice(0, 10) === n.after && Date.parse(r.issue_time_utc) < storm) ?? null) : null
	}, [pego, idx])

	// the index of the baked layers
	useEffect(() => {
		let gone = false
		fetch(`${ROOT}/explore.json`)
			.then((r) => {
				if (!r.ok) throw new Error(`explore.json: ${r.status}`)
				return r.json() as Promise<ExploreIndex>
			})
			.then((d) => !gone && setIdx(d))
			.catch((e: Error) => !gone && setError(e.message))
		return () => {
			gone = true
		}
	}, [])

	/** the prediction of both sites, read once something needs it (the model, the replay, a click) */
	const needPreds = useCallback(() => {
		for (const s of PREDICTION_SITES) {
			if (s.site in preds) continue
			loadPrediction(s.root).then((p) => setPreds((was) => ({ ...was, [s.site]: p })))
		}
	}, [preds])

	// ---------------------------------------------------------------- the map
	useEffect(() => {
		if (!idx || !mapEl.current) return
		let map: MapLibreMap | null = null
		let gone = false
		;(async () => {
			const { Map } = await (maplibre ?? import('maplibre-gl'))
			if (gone || !mapEl.current) return
			const q = new URLSearchParams(window.location.search)
			const place = PLACES.find((p) => p.key === q.get('place'))
			map = new Map({
				container: mapEl.current,
				style: {
					version: 8,
					sources: {
						pnoa: { type: 'raster', tiles: [PNOA.tiles], tileSize: 256, maxzoom: PNOA.maxzoom, attribution: PNOA.credit },
						icv: { type: 'raster', tiles: [ICV.tiles], tileSize: 256, maxzoom: ICV.maxzoom, attribution: ICV.credit },
					},
					layers: [
						{ id: 'pnoa', type: 'raster', source: 'pnoa', paint: { 'raster-saturation': -0.12 } },
						{ id: 'icv', type: 'raster', source: 'icv', layout: { visibility: 'none' }, paint: { 'raster-saturation': -0.12 } },
					],
				},
				center: place?.view.center ?? START.center,
				zoom: place?.view.zoom ?? START.zoom,
				minZoom: 6,
				maxZoom: 18.6,
				pitch: 0,
				maxPitch: 0,
				dragRotate: false,
				pitchWithRotate: false,
				attributionControl: { compact: true },
			})
			mapRef.current = map
			map.touchZoomRotate.disableRotation()
			// the official photographs first; should their server fail, the Valencian ones
			let failed = 0
			map.on('error', (e) => {
				if ((e as unknown as { sourceId?: string }).sourceId === 'pnoa' && ++failed >= 4 && baseRef.current === 'pnoa') {
					baseRef.current = 'icv'
					setBase('icv')
				}
			})
			map.once('style.load', () => {
				if (gone || !map) return
				const v = `?v=${encodeURIComponent(idx.baked_utc)}`
				const fade = ['interpolate', ['linear'], ['zoom'], STREET_FADE[0], 1, STREET_FADE[1], 0] as never
				// the radar pictures: NISAR open water before and after the DANA, and what was still flooded
				for (const [site, s] of Object.entries(idx.sites)) {
					const n = s.nisar
					if (!n) continue
					const [w, so, e, no] = n.bounds
					const corners: [[number, number], [number, number], [number, number], [number, number]] = [
						[w, no],
						[e, no],
						[e, so],
						[w, so],
					]
					const pictures: [string, string][] = [
						[`nisar-${site}`, n.pictures.after.file],
						[`nisar0-${site}`, n.pictures.before.file],
					]
					if (n.still) pictures.push([`still-${site}`, n.still.file])
					for (const [id, file] of pictures) {
						map.addSource(id, { type: 'image', url: `${ROOT}/${file}${v}`, coordinates: corners })
						map.addLayer({ id, type: 'raster', source: id, layout: { visibility: 'none' }, paint: { 'raster-opacity': fade, 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } })
					}
				}
				// the model's layers go here, under every outline
				map.addLayer(emptyLayer('over-rasters'))
				const add = (key: string) => {
					const vec = idx.vectors[key]
					if (vec) map!.addSource(key, { type: 'geojson', data: `${ROOT}/${vec.file}`, attribution: '' } as never)
					return !!vec
				}
				for (const f of FLOODS) {
					if (!add(f.key)) continue
					map.addLayer({ id: `${f.key}-fill`, type: 'fill', source: f.key, paint: { 'fill-color': '#ff7ac8', 'fill-opacity': ['match', ['get', 'observed'], 'flood_trace', 0.14, 0.24] as never } })
					map.addLayer({ id: `${f.key}-line`, type: 'line', source: f.key, paint: { 'line-color': '#ffa3da', 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.8, 16, 2] as never, 'line-opacity': 0.9 } })
				}
				if (add('municipalities')) {
					map.addLayer({ id: 'municipalities-line', type: 'line', source: 'municipalities', minzoom: 9, paint: { 'line-color': '#ffffff', 'line-width': 1, 'line-opacity': 0.45, 'line-dasharray': [3, 2] } })
				}
				for (const z of ZONE_SOURCES) {
					if (!add(z)) continue
					map.addLayer({
						id: `${z}-line`,
						type: 'line',
						source: z,
						paint: { 'line-color': zoneColor as never, 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1, 16, 2.6] as never, 'line-opacity': 0.95 },
					})
				}
				if (add('buildings_2024')) {
					map.addLayer({
						id: 'buildings_2024',
						type: 'circle',
						source: 'buildings_2024',
						paint: {
							'circle-color': ['match', ['get', 'damage'], 'Destroyed', '#ff2d55', 'Damaged', '#ff6b3d', '#ffb340'] as never,
							'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1.6, 14, 3.4, 17, 7] as never,
							'circle-stroke-color': '#ffffff',
							'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 0, 14, 0.8, 17, 1.4] as never,
						},
					})
				}
				// what a click reads, whatever the legend shows: shapes drawn with nothing to see
				for (const key of [...ZONE_SOURCES, 'municipalities', ...FLOODS.map((f) => f.key)]) {
					if (map.getSource(key)) map.addLayer({ id: `${key}-hit`, type: 'fill', source: key, paint: { 'fill-opacity': 0 } })
				}
				if (map.getSource('buildings_2024')) map.addLayer({ id: 'buildings_2024-hit', type: 'circle', source: 'buildings_2024', paint: { 'circle-opacity': 0, 'circle-radius': 7 } })
				setReady(true)
			})
		})()
		return () => {
			gone = true
			map?.remove()
			mapRef.current = null
			models.current = {}
			setReady(false)
		}
	}, [idx])

	// the photograph: the official one or the Valencian one
	useEffect(() => {
		baseRef.current = base
		const map = mapRef.current
		if (!map || !ready) return
		map.setLayoutProperty('pnoa', 'visibility', base === 'pnoa' ? 'visible' : 'none')
		map.setLayoutProperty('icv', 'visibility', base === 'icv' ? 'visible' : 'none')
	}, [base, ready])

	// which layers show: the legend's, or the step of the replay
	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		const on = new Set(replaying ? SCENE_LAYERS[scene] : (Object.keys(layers) as LayerKey[]).filter((k) => layers[k]).flatMap((k) => SHOWS[k]))
		for (const id of ALL_SHOWN) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on.has(id) ? 'visible' : 'none')
		if (map.getLayer('municipalities-line')) map.setLayoutProperty('municipalities-line', 'visibility', replaying ? 'none' : 'visible')
	}, [layers, replaying, scene, ready])

	// ---------------------------------------------------------------- the model layers
	useEffect(() => {
		if (layers.model || replaying) needPreds()
	}, [layers.model, replaying, needPreds])

	// a layer per site, once its prediction is here; its frames load only when it is asked to show
	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		for (const s of PREDICTION_SITES) {
			const p = preds[s.site]
			if (!p || models.current[s.site] || !map.getLayer('over-rasters')) continue
			const frames = [...p.scenarios, ...p.replays].map((m) => ({ key: m.id, url: fileUrl(s.root, p, m.file) }))
			const layer = new LikelihoodLayer({ id: `model-${s.site}`, frames, bounds: p.grid.bounds, size: [p.grid.width, p.grid.height] })
			map.addLayer(layer.layer, 'over-rasters')
			models.current[s.site] = layer
			layer.setAlpha(1 - smooth(STREET_FADE[0], STREET_FADE[1], map.getZoom()))
		}
	}, [preds, ready])

	/** the rain slider's handle, as a position over the stops: every model layer mixes the two maps around it */
	const showRain = useCallback(
		(pos: number) => {
			rainPos.current = pos
			for (const s of PREDICTION_SITES) {
				const p = preds[s.site]
				const layer = models.current[s.site]
				const list = p?.scenarios.filter((x) => x.rain_mm !== null) ?? []
				if (!layer || !list.length) continue
				const a = Math.max(0, Math.min(list.length - 1, Math.floor(pos)))
				const b = Math.min(list.length - 1, a + 1)
				layer.set(list[a].id, list[b].id, pos - a, list[a].thresholds.new_water)
			}
		},
		[preds],
	)

	// the model shows with the legend's switch, or in the second step of the replay (Pego-Oliva only)
	useEffect(() => {
		for (const s of PREDICTION_SITES) {
			const layer = models.current[s.site]
			if (!layer) continue
			if (replaying) {
				const on = scene === 1 && s.site === 'pego_oliva' && !!prestorm
				if (on && prestorm) layer.set(prestorm.id, prestorm.id, 0, prestorm.thresholds.new_water)
				layer.fadeTo(on ? 1 : 0, 600)
			} else {
				if (layers.model) {
					showRain(rainPos.current)
					const p = preds[s.site]
					layer.preload(p?.scenarios.map((x) => x.id) ?? [])
				}
				layer.fadeTo(layers.model ? 1 : 0, 600)
			}
		}
	}, [layers.model, replaying, scene, prestorm, preds, showRain])

	// at street level the 15 to 20 m pictures give way to the sharp outlines; the readout follows the site in view
	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		const zoom = () => {
			const k = 1 - smooth(STREET_FADE[0], STREET_FADE[1], map.getZoom())
			for (const layer of Object.values(models.current)) layer.setAlpha(k)
		}
		const moved = () => {
			const c = map.getCenter()
			const inside = PREDICTION_SITES.find((s) => preds[s.site] && inBounds(preds[s.site]!.grid.bounds, [c.lng, c.lat]))
			if (inside) setModelSite(inside.site)
		}
		zoom()
		map.on('zoom', zoom)
		map.on('moveend', moved)
		return () => {
			map.off('zoom', zoom)
			map.off('moveend', moved)
		}
	}, [ready, preds])

	// ---------------------------------------------------------------- a click on the map
	const inspect = useCallback(
		async (lngLat: [number, number], point: [number, number]) => {
			const map = mapRef.current
			if (!map || !idx) return
			const seq = ++spotSeq.current
			spotAt.current = { lngLat, point }
			setSpot((s) => ({ result: s?.result ?? null, loading: true }))
			if (!spotMarker.current) {
				const { Marker } = await (maplibre ?? import('maplibre-gl'))
				const node = document.createElement('span')
				node.className = 'ex-spot'
				spotMarker.current = new Marker({ element: node, anchor: 'center' })
			}
			if (seq !== spotSeq.current) return
			spotMarker.current.setLngLat(lngLat).addTo(map)
			needPreds()
			try {
				// the shapes under the spot, from the layers nobody sees
				const hits = (layers: string[], at: PointLike | [PointLike, PointLike]): MapGeoJSONFeature[] => {
					const ok = layers.filter((l) => map.getLayer(l))
					return ok.length ? map.queryRenderedFeatures(at, { layers: ok }) : []
				}
				const muni = hits(['municipalities-hit'], point)[0]?.properties?.name as string | undefined
				const classes = new Set(hits(ZONE_SOURCES.map((z) => `${z}-hit`), point).map((f) => f.properties?.zone as string))
				const zone = muni ? ((['frequent', 'occasional', 'rare'] as const).find((z) => classes.has(z)) ?? 'none') : null
				const floods = FLOODS.flatMap((f) =>
					[...new Set(hits([`${f.key}-hit`], point).map((x) => x.properties?.observed as string))].map((observed) => ({ year: f.year, code: f.code, observed })),
				)
				const box: [PointLike, PointLike] = [
					[point[0] - 5, point[1] - 5],
					[point[0] + 5, point[1] + 5],
				]
				const building = (hits(['buildings_2024-hit'], box)[0]?.properties?.damage as string | undefined) ?? null

				// the files of the model and of NISAR
				const mapId = replaying && sceneRef.current === 1 ? (prestorm?.id ?? null) : (rains[Math.round(rainPos.current)]?.id ?? 'scenario_100mm')
				const model = await inspectAt(lngLat, mapId)
				const site = model.kind === 'spot' ? model.spot.site : null
				let nisar: ExploreSpotInfo['nisar'] = null
				let nisarLayer = ''
				for (const s of Object.values(idx.sites)) {
					const n = s.nisar
					const px = n ? pixelAt({ width: n.size[0], height: n.size[1], bounds: n.bounds }, lngLat) : null
					if (!n || !px) continue
					const [code, still] = await readPixel(`${ROOT}/${n.data.file}?v=${encodeURIComponent(idx.baked_utc)}`, px.row, px.col)
					nisar = { code, before: n.before, after: n.after, still: still === 1 }
					nisarLayer = n.sources.layer
					break
				}
				if (seq !== spotSeq.current) return
				if (!muni && model.kind !== 'spot' && !nisar && !floods.length && !building) {
					setSpot({ result: { kind: 'outside', lngLat }, loading: false })
					return
				}
				const p = site ? await loadPrediction(PREDICTION_SITES.find((x) => x.site === site)!.root) : null
				const m = model.kind === 'spot' ? model.spot : null
				const sources = [
					...(zone !== null ? ['Zones: SNCZI (MITECO), data/zones/zones_*.geojson (PR #36)'] : []),
					...(floods.length || building ? ['Floods: Copernicus EMS EMSR773 (2024) and EMSR935 (2026), data/zones (PR #36)'] : []),
					...(nisar ? [`NISAR: ${nisarLayer} (PR #35)`] : []),
					...(m?.model ? [`Model: ${String(m.model.map.sources.water_likelihood)} (model ${p?.source.model_sha256_16 ?? ''})`] : []),
					...(p?.inspect.soil ? [`Soil: ${p.inspect.soil.product}, ${p.inspect.soil.source}`] : []),
					...(p?.inspect.landcover ? [`Land: ${p.inspect.landcover.product}, ${p.inspect.landcover.source}`] : []),
				]
				const info: ExploreSpotInfo = {
					lngLat,
					municipality: muni ?? (m ? m.name : null),
					zone,
					floods,
					building,
					nisar: nisar && nisar.code !== 255 ? nisar : nisar?.still ? nisar : null,
					model: m?.model
						? { ...m.model, evidenceText: m.model.evidence !== 0 && m.model.evidence !== 255 ? (p?.evidence?.[String(m.model.evidence)] ?? null) : null }
						: null,
					soil: m?.soil ?? null,
					land: m?.land?.name ?? null,
					site,
					sources,
				}
				setSpot({ result: { kind: 'spot', info }, loading: false })
			} catch (e) {
				if (seq === spotSeq.current) setSpot({ result: { kind: 'error', message: (e as Error).message }, loading: false })
			}
		},
		[idx, needPreds, replaying, prestorm, rains],
	)
	const closeSpot = useCallback(() => {
		spotSeq.current++
		spotAt.current = null
		setSpot(null)
		spotMarker.current?.remove()
	}, [])
	useEffect(() => {
		const map = mapRef.current
		if (!map || !ready) return
		const click = (e: MapMouseEvent) => inspect([e.lngLat.lng, e.lngLat.lat], [e.point.x, e.point.y])
		map.on('click', click)
		return () => {
			map.off('click', click)
		}
	}, [ready, inspect])
	// the panel follows the rain and the replay: the same spot is read again
	useEffect(() => {
		const at = spotAt.current
		const map = mapRef.current
		if (!at || !map) return
		const p = map.project(at.lngLat)
		inspect(at.lngLat, [p.x, p.y])
	}, [rainIdx, scene, replaying, inspect])

	const go = useCallback(
		(key: string) => {
			const place = PLACES.find((p) => p.key === key)
			if (place) mapRef.current?.flyTo({ ...place.view, duration: 2400, essential: true })
		},
		[],
	)

	// ---------------------------------------------------------------- the replay
	const goScene = useCallback((i: number) => {
		sceneRef.current = i
		setScene(i)
	}, [])
	const startReplay = useCallback(() => {
		closeSpot()
		goScene(0)
		setReplaying(true)
		setAuto(true)
		go('pego')
	}, [closeSpot, goScene, go])
	const stopReplay = useCallback(() => {
		setAuto(false)
		setReplaying(false)
	}, [])
	useEffect(() => {
		if (!replaying || !auto) return
		const id = window.setTimeout(() => {
			const next = Math.min(SCENES - 1, sceneRef.current + 1)
			goScene(next)
			if (next >= SCENES - 1) setAuto(false)
		}, SCENE_MS + (sceneRef.current === 0 ? 1600 : 0))
		return () => window.clearTimeout(id)
	}, [replaying, auto, scene, goScene])
	const playReplay = useCallback(() => {
		if (!auto && sceneRef.current >= SCENES - 1) goScene(0)
		setAuto((a) => !a)
	}, [auto, goScene])

	useEffect(() => {
		const key = (e: KeyboardEvent) => {
			if (e.code === 'Escape') {
				if (spotAt.current) closeSpot()
				else if (replaying) stopReplay()
				return
			}
			if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(e.target.tagName)) return
			const dir = e.code === 'ArrowRight' ? 1 : e.code === 'ArrowLeft' ? -1 : 0
			if (replaying) {
				if (e.code === 'Space') {
					e.preventDefault()
					playReplay()
				} else if (dir) {
					setAuto(false)
					goScene(Math.max(0, Math.min(SCENES - 1, sceneRef.current + dir)))
				}
			} else if (layers.model && dir) setRainIdx((i) => Math.max(0, Math.min(rains.length - 1, i + dir)))
		}
		window.addEventListener('keydown', key)
		return () => window.removeEventListener('keydown', key)
	}, [replaying, layers.model, rains, playReplay, goScene, closeSpot, stopReplay])

	// a small handle for scripted checks
	useEffect(() => {
		const api = {
			map: () => mapRef.current,
			layer: (k: LayerKey, on: boolean) => setLayers((was) => ({ ...was, [k]: on })),
			rain: (i: number) => setRainIdx(i),
			replay: (on: boolean) => (on ? startReplay() : stopReplay()),
			scene: (i: number) => {
				setAuto(false)
				goScene(i)
			},
			inspect: (lng: number, lat: number) => {
				const m = mapRef.current
				if (!m) return
				const p = m.project([lng, lat])
				inspect([lng, lat], [p.x, p.y])
			},
			go,
			base: (b: Base) => setBase(b),
			modelReady: () => Object.values(models.current).some((l) => l.ready()),
			ready: () => ready && !!mapRef.current?.loaded(),
		}
		const host = window as unknown as { __explore?: typeof api }
		host.__explore = api
		return () => {
			delete host.__explore
		}
	}, [ready, inspect, go, startReplay, stopReplay, goScene])

	// ---------------------------------------------------------------- what the bottom panel says
	const nisarPego = idx?.sites.pego_oliva?.nisar ?? null
	const dry = rains.find((s) => s.rain_mm === 0)
	const rainStops = useMemo(
		() =>
			rains.map((r) => {
				const add = dry ? r.area_ha.likely_new_water - dry.area_ha.likely_new_water : null
				const sub = !dry ? undefined : r === dry ? `${ha(r.area_ha.likely_new_water)} ha` : `${add! >= 0 ? '+' : ''}${ha(add!)} ha`
				return { label: `${r.rain_mm} mm`, sub, warn: !!r.caption.warning }
			}),
		[rains, dry],
	)
	type Read = { num: string; unit: string; tag: string; pass?: boolean; small: string; caption: string; note?: { text: string; keys: boolean } }
	const read: Read | null = useMemo(() => {
		if (replaying && nisarPego) {
			const n = nisarPego
			const list: Read[] = [
				{ num: ha(n.open_water.before_ha), unit: 'ha of open water', tag: 'Radar pass', pass: true, small: `NISAR, track ${n.stack.replace(/_/g, ' ')}`, caption: `${day(n.before)}, before the storm: the open water NISAR saw at Pego-Oliva` },
				prestorm
					? {
							num: ha(prestorm.area_ha.likely_new_water),
							unit: 'ha of likely new water',
							tag: 'Model',
							small: `Issued ${day(prestorm.issue_time_utc)}, before the rain`,
							caption: `Our model, from the ${prestorm.issued_from_sensor ?? 'radar'} map of ${day(prestorm.issue_time_utc)}: where water would be on ${day(prestorm.target_time_utc)}`,
							note: { text: prestorm.caption.note, keys: true },
						}
					: { num: '', unit: '', tag: 'Model', small: '', caption: 'The model map is still loading' },
				{ num: ha(n.open_water.after_ha), unit: 'ha of open water', tag: 'Radar pass', pass: true, small: `+${ha(n.open_water.new_ha)} ha new since ${day(n.before)}`, caption: `${day(n.after)}, the next NISAR pass, and the Copernicus EMS flood map of 20 to 21 Oct` },
				n.still
					? {
							num: ha(n.still.open_water_ha),
							unit: 'ha still under water',
							tag: 'Radar pass',
							pass: true,
							small: `${Math.round(n.still.open_water_share * 100)} % of the EU map's flooded land NISAR saw`,
							caption: `Still under water on ${day(n.still.date)}: flooded land of the EU map that NISAR saw as open water`,
						}
					: { num: '', unit: '', tag: '', small: '', caption: '' },
			]
			return list[scene]
		}
		if (layers.model && rain) {
			const more = dry ? rain.area_ha.likely_new_water - dry.area_ha.likely_new_water : 0
			return {
				num: ha(rain.area_ha.likely_new_water),
				unit: 'ha of likely new water',
				tag: `Model, ${PREDICTION_SITES.find((s) => s.site === modelSite)?.name ?? ''}`,
				small: !dry || rain === dry ? `${day(rain.target_time_utc)}, with no rain at all` : `${day(rain.target_time_utc)}: ${more >= 0 ? '+' : ''}${ha(more)} ha more than with no rain`,
				caption: rain.caption.line,
				note: { text: rain.caption.note, keys: true },
			}
		}
		return null
	}, [replaying, nisarPego, prestorm, scene, layers.model, rain, dry, modelSite])

	const toggle = (k: LayerKey) => setLayers((was) => ({ ...was, [k]: !was[k] }))

	return (
		<div className="ex" data-ready={ready || undefined}>
			<div ref={mapEl} className="ex-map" />

			<header className="ex-top">
				<Link href="/" className="ex-brand">
					Dancing with the SARs
				</Link>
				<h1 className="display ex-title">Flood explorer</h1>
				<p className="ex-sub">Official flood zones, what really flooded, and where our model says the water would go.</p>
				<nav className="ex-places" aria-label="Places">
					{PLACES.map((p) => (
						<button key={p.key} type="button" onClick={() => go(p.key)}>
							<b>{p.name}</b>
							<small>{p.when}</small>
						</button>
					))}
				</nav>
			</header>

			<button type="button" className="ex-legend-btn" aria-expanded={legendOpen} onClick={() => setLegendOpen((o) => !o)}>
				<Layers size={16} strokeWidth={2.2} /> Layers
			</button>
			<aside className="ex-legend" aria-label="Layers" data-open={legendOpen || undefined}>
				{LEGEND.map((g) => (
					<section key={g.title}>
						<h2>{g.title}</h2>
						{g.layers.map((l) => (
							<div key={l.key}>
								<button type="button" className="ex-row" role="switch" aria-checked={!!layers[l.key] && !l.soon} disabled={l.soon || replaying} onClick={() => toggle(l.key)}>
									<span className="ex-sw" data-kind={l.swatch} />
									<span>
										<b>{l.label}</b>
										{l.detail && <small>{l.detail}</small>}
									</span>
									{l.soon ? <span className="ex-soon">soon</span> : <i />}
								</button>
								{l.key === 'zones' && layers.zones && (
									<ul className="ex-zonekey">
										{ZONES.map((z) => (
											<li key={z.key}>
												<i style={{ background: z.color }} /> {z.label}, {z.name}: {z.detail}
											</li>
										))}
									</ul>
								)}
							</div>
						))}
					</section>
				))}
				<div className="ex-base">
					<span>Photo</span>
					<div className="ex-seg">
						<button type="button" aria-pressed={base === 'pnoa'} onClick={() => setBase('pnoa')}>
							IGN PNOA
						</button>
						<button type="button" aria-pressed={base === 'icv'} onClick={() => setBase('icv')}>
							ICV 2024
						</button>
					</div>
				</div>
				<button type="button" className="sp-src" aria-expanded={sources} onClick={() => setSources((s) => !s)}>
					Sources
				</button>
				{sources && (
					<ul className="ex-sources">
						<li>
							<b>Photo</b> {base === 'pnoa' ? PNOA.credit : ICV.credit}
						</li>
						{CREDITS.map((c) => (
							<li key={c.what}>
								<b>{c.what}</b> {c.who}
							</li>
						))}
					</ul>
				)}
			</aside>

			<ExploreSpot result={spot?.result ?? null} loading={!!spot?.loading} onClose={closeSpot} onGo={go} />

			<footer className="ex-bottom">
				{read && (
					<>
						{read.num && (
							<div className="ex-read">
								<b className="display">{read.num}</b>
								<span>
									<i className="ex-tag" data-pass={read.pass || undefined}>
										{read.tag}
									</i>
									{read.unit}
									<small>{read.small}</small>
								</span>
							</div>
						)}
						<p key={read.caption} className="ex-caption">
							{read.caption}
						</p>
						{read.note && (
							<div className="ex-note">
								{read.note.keys && (
									<>
										<span className="ex-key">
											<i className="ex-ramp" /> less to more likely
										</span>
										<span className="ex-key">
											<i className="ex-dash" /> likely new water
										</span>
									</>
								)}
								<span className="ex-why">{read.note.text}</span>
								{!replaying && rain?.caption.warning && <span className="ex-warn">{rain.caption.warning}</span>}
								{!replaying && rain?.caption.detail && <span className="ex-detail">{rain.caption.detail}</span>}
							</div>
						)}
					</>
				)}
				{replaying ? (
					<div className="ex-strip">
						<button type="button" className="ex-play" onClick={playReplay} aria-label={auto ? 'Pause' : 'Play'}>
							{auto ? <Pause size={18} strokeWidth={2.4} /> : <Play size={18} strokeWidth={2.4} />}
						</button>
						<ol className="rp-steps" style={{ ['--scene-ms' as string]: `${SCENE_MS}ms` }}>
							{[`${nisarPego ? day(nisarPego.before) : ''}: NISAR`, 'Our model', `${nisarPego ? day(nisarPego.after) : ''}: NISAR`, 'Still flooded'].map((label, i) => (
								<li key={label}>
									<button
										type="button"
										aria-current={i === scene ? 'step' : undefined}
										data-done={i < scene || undefined}
										data-auto={(auto && i === scene) || undefined}
										onClick={() => {
											setAuto(false)
											goScene(i)
										}}
									>
										<i />
										<span>{label}</span>
									</button>
								</li>
							))}
						</ol>
						<button type="button" className="ex-close" onClick={stopReplay} aria-label="End the replay">
							<X size={16} strokeWidth={2.4} />
						</button>
					</div>
				) : layers.model && rains.length > 0 ? (
					<div className="ex-strip">
						<RainSlider stops={rainStops} index={rainIdx} onInput={showRain} onStop={setRainIdx} label={`Rain in ${Math.round(rain?.lead_days ?? 0)} days`} />
					</div>
				) : null}
				{!replaying && (
					<div className="ex-actions">
						<button type="button" className="ex-pill" aria-pressed={layers.model} onClick={() => toggle('model')}>
							What if it rains
						</button>
						{nisarPego && (
							<button type="button" className="ex-pill" onClick={startReplay}>
								<Play size={14} strokeWidth={2.6} /> DANA replay
							</button>
						)}
					</div>
				)}
			</footer>
			{error && <p className="sp-text">The layers did not load: {error}</p>}
		</div>
	)
}

