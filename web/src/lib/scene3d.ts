// Real 3D for the map pages: the ground from an elevation source, a sky over it, and the globe for the way in.
//
// With the terrain on, MapLibre lays its raster, fill and line layers over the relief, and our own two layers too
// (water-layer.ts and picture-layer.ts draw into the terrain tiles). Nothing else in a page has to change: switch it
// on after the style has loaded, tilt the camera, and switch it off again for the flat map.
import type { CustomLayerInterface, Map as MapLibreMap, SkySpecification } from 'maplibre-gl'
import { maxZoomOf, tilesOf } from './tiles'

/** A view of the map with the camera tilted: where it looks, how close, how low, and from which side. */
export type Camera3D = { center: [number, number]; zoom: number; pitch: number; bearing: number }

/**
 * The elevation tiles. Mapterhorn serves open elevation data as terrarium tiles: in Spain the 2 m lidar model of
 * the national survey (MDT02, CC BY 4.0), elsewhere Copernicus GLO-30. No key, sent with CORS headers. The tiles of
 * the stories are copied into the app (scripts/bake_tiles.py, lib/tiles.ts); others still come from Mapterhorn.
 * The credit is the one its tile description asks for, plus the two sources these pages actually show.
 */
export const TERRAIN = {
	id: 'terrain-dem',
	source: {
		type: 'raster-dem' as const,
		tiles: [tilesOf('dem')],
		encoding: 'terrarium' as const,
		tileSize: 512,
		// far out the relief cannot be seen, and some open-ocean tiles of the low zooms do not exist (404).
		// It stops at zoom 12 (15 m): the terrain mesh of these views is coarser than that, so finer tiles only cost
		minzoom: 6,
		maxzoom: maxZoomOf('dem'),
	},
	credit: 'Terrain: © Mapterhorn (mapterhorn.com/attribution). MDT02 2015-2021 CC-BY 4.0 scne.es; Copernicus GLO-30, DLR e.V. 2010-2014 and Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA',
	creditShort: 'Terrain: Mapterhorn, CNIG, Copernicus',
}

/** A second elevation source, kept as a spare: the Terrain Tiles on AWS (about 30 m in Europe, EU-DEM and SRTM). */
export const TERRAIN_SPARE = {
	source: {
		type: 'raster-dem' as const,
		tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
		encoding: 'terrarium' as const,
		tileSize: 256,
		maxzoom: 14,
	},
	credit: 'Terrain Tiles on AWS (Mapzen, Tilezen Joerd). Europe terrain data produced using Copernicus data and information funded by the European Union: EU-DEM layers. SRTM terrain data courtesy of the U.S. Geological Survey',
}

/** The view of each story with the camera tilted, for a 16:9 screen (chosen from screenshots of the test bench).
 *  The marsh sits in front of its mountains with the sea in the foreground; the burned slopes face the camera;
 *  the lagoon lies behind its rice fields with the city on the horizon. */
export const CAMERAS: Record<'pego_oliva' | 'espada' | 'albufera', Camera3D> = {
	pego_oliva: { center: [-0.072, 38.872], zoom: 12.5, pitch: 56, bearing: -110 },
	espada: { center: [-0.262, 39.885], zoom: 11.75, pitch: 60, bearing: -25 },
	albufera: { center: [-0.33, 39.3], zoom: 11.25, pitch: 50, bearing: -8 },
}

/** how much taller than life the relief is drawn: the marsh is flat, its mountains are a few hundred metres */
export const EXAGGERATION = 1.5

export function terrainOn(map: MapLibreMap) {
	return !!map.getTerrain()
}

/** Lay the map over the relief. Call it once the style has loaded; calling it again only changes the exaggeration. */
export function enableTerrain(map: MapLibreMap, opts: { exaggeration?: number; spare?: boolean } = {}) {
	if (!map.getSource(TERRAIN.id)) map.addSource(TERRAIN.id, opts.spare ? TERRAIN_SPARE.source : TERRAIN.source)
	map.setTerrain({ source: TERRAIN.id, exaggeration: opts.exaggeration ?? EXAGGERATION })
	// low views are the point of the relief; the default stops at 60 degrees
	map.setMaxPitch(75)
}

/** Back to the flat map. The camera keeps its tilt: set the pitch to 0 for a plan view. */
export function disableTerrain(map: MapLibreMap) {
	if (map.getTerrain()) map.setTerrain(null)
}

const FAR_ONLY = ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 8, 0] as never
/** haze on the far ground, but only once the map is close: seen from space it would wash out half the globe */
const hazeFrom = (near: number) => ['interpolate', ['linear'], ['zoom'], 6, 1, 9.5, near] as never

/** Skies. The haze near the horizon hides the far edge of the tiles; the glow of the atmosphere shows from space only. */
export const SKIES: Record<'day' | 'night' | 'storm', SkySpecification> = {
	day: { 'sky-color': '#8fc3ea', 'horizon-color': '#e6eff5', 'fog-color': '#dbe6ec', 'sky-horizon-blend': 0.7, 'horizon-fog-blend': 0.8, 'fog-ground-blend': hazeFrom(0.72), 'atmosphere-blend': FAR_ONLY },
	night: { 'sky-color': '#060d17', 'horizon-color': '#1b3145', 'fog-color': '#0f1c29', 'sky-horizon-blend': 0.7, 'horizon-fog-blend': 0.8, 'fog-ground-blend': hazeFrom(0.72), 'atmosphere-blend': FAR_ONLY },
	storm: { 'sky-color': '#2c343d', 'horizon-color': '#56616b', 'fog-color': '#434d56', 'sky-horizon-blend': 0.8, 'horizon-fog-blend': 0.9, 'fog-ground-blend': hazeFrom(0.55), 'atmosphere-blend': FAR_ONLY },
}

/** One of the skies above, or none. */
export function setSky(map: MapLibreMap, sky: keyof typeof SKIES | null) {
	map.setSky(sky ? SKIES[sky] : (undefined as never))
}

/** The Earth as a ball from far out. MapLibre turns it into the flat map by itself between zoom 11 and 12, so the
 *  page can stay on the globe for the whole way in. Keep the terrain on with it: our own layers are drawn by the
 *  terrain then, which works on the ball too; without terrain they only appear once the map is flat. */
export function setGlobe(map: MapLibreMap, on: boolean) {
	map.setProjection({ type: on ? 'globe' : 'mercator' })
}

/** Everything for the 3D view in one call, and everything off again. */
export function set3d(map: MapLibreMap, on: boolean, opts: { sky?: keyof typeof SKIES; globe?: boolean; exaggeration?: number } = {}) {
	if (on) {
		enableTerrain(map, { exaggeration: opts.exaggeration })
		setSky(map, opts.sky ?? 'day')
		setGlobe(map, opts.globe ?? true)
	} else {
		disableTerrain(map)
		setSky(map, null)
		setGlobe(map, false)
	}
}

/**
 * The whole Earth for the view from space. The base map of the pages (EOX cloudless 2017) has no picture south of
 * about 22 degrees north at these zooms and shows white there, so the ball needs a complete picture under it:
 * the Blue Marble of NASA, from the same service the storm pictures come from. No key, sent with CORS headers.
 */
export const FAR_BASE = {
	id: 'far-base',
	// NASA GIBS BlueMarble_ShadedRelief_Bathymetry, copied into the app for the way in (lib/tiles.ts)
	tiles: [tilesOf('far')],
	maxzoom: maxZoomOf('far'),
	credit: 'Blue Marble: NASA Earth Observatory, served by NASA GIBS',
}

/**
 * A layer that draws nothing, to hold a place in the order of the layers (ours go under it). Unlike an empty
 * background layer it is not drawn into the textures of the terrain either: with the terrain on, MapLibre would fill
 * every terrain tile with a background layer, invisible or not, each time it draws the tiles again.
 */
export function emptyLayer(id: string): CustomLayerInterface {
	return { id, type: 'custom', renderingMode: '2d', render: () => {} }
}

/** Put the whole Earth under the base map, and let the base map fade in over it on the way down (zoom 5.2 to 6.6).
 *  `baseLayerId` is the raster layer of the page's own base map. */
export function addFarBase(map: MapLibreMap, baseLayerId: string, fade: [number, number] = [5.2, 6.6]) {
	if (!map.getSource(FAR_BASE.id)) map.addSource(FAR_BASE.id, { type: 'raster', tiles: FAR_BASE.tiles, tileSize: 256, maxzoom: FAR_BASE.maxzoom })
	if (!map.getLayer(FAR_BASE.id)) {
		map.addLayer({ id: FAR_BASE.id, type: 'raster', source: FAR_BASE.id, maxzoom: fade[1] + 0.4, paint: { 'raster-saturation': -0.15, 'raster-brightness-max': 0.86, 'raster-fade-duration': 0 } }, baseLayerId)
	}
	map.setPaintProperty(baseLayerId, 'raster-opacity', ['interpolate', ['linear'], ['zoom'], fade[0], 0, fade[1], 1])
}

/** where the way in starts when the page does not say: the ball with Europe and North Africa in view */
export function farView(to: Camera3D): { center: [number, number]; zoom: number } {
	return { center: [to.center[0] + 6, to.center[1] + 4], zoom: 2.6 }
}

const smooth = (x: number) => x * x * x * (x * (x * 6 - 15) + 10)
const between = (a: number, b: number, x: number) => smooth(Math.min(1, Math.max(0, (x - a) / (b - a))))

/** The camera at one moment of the way in, 0 at the start and 1 on arrival. Zooming is even to the eye (the zoom
 *  number runs evenly), the place drifts to the middle of the screen, and the camera only tilts and turns in the
 *  last stretch, when the relief is close enough to be seen. */
export function wayIn(to: Camera3D, from: { center: [number, number]; zoom: number }, t: number) {
	const e = smooth(Math.min(1, Math.max(0, t)))
	const zoom = from.zoom + (to.zoom - from.zoom) * e
	// zooming towards a point keeps it at the same spot of the screen; the last factor brings it to the middle
	const k = 2 ** -(zoom - from.zoom) * (1 - between(0.15, 0.9, t))
	const center: [number, number] = [to.center[0] + (from.center[0] - to.center[0]) * k, to.center[1] + (from.center[1] - to.center[1]) * k]
	const tilt = between(0.55, 1, t)
	return { center, zoom, pitch: to.pitch * tilt, bearing: to.bearing * tilt }
}

/**
 * The way in: from the globe down to the place in one move, the camera tilting as it arrives.
 * Resolves when the camera has stopped. The path is our own (wayIn), so warmUp can load exactly its tiles.
 */
export function flyIn(map: MapLibreMap, to: Camera3D, opts: { from?: { center: [number, number]; zoom: number }; duration?: number } = {}) {
	const from = opts.from ?? farView(to)
	const duration = opts.duration ?? 7000
	map.stop()
	map.jumpTo(wayIn(to, from, 0))
	return new Promise<void>((done) => {
		const t0 = performance.now()
		const step = (now: number) => {
			const t = Math.min(1, (now - t0) / duration)
			map.jumpTo(wayIn(to, from, t))
			if (t < 1) requestAnimationFrame(step)
			else done()
		}
		requestAnimationFrame(step)
	})
}

/**
 * Visit the stops of the way in once, from the place back out, so the tiles of every zoom on the way are in memory
 * and the real flight shows sharp ground instead of tiles arriving. The page should cover the map meanwhile.
 * Each stop waits until the map is idle, or 2.5 s at most. Ends at the start of the way in.
 */
export async function warmUp(map: MapLibreMap, to: Camera3D, opts: { from?: { center: [number, number]; zoom: number }; stops?: number } = {}) {
	const from = opts.from ?? farView(to)
	const stops = opts.stops ?? 8
	const idle = () =>
		new Promise<void>((ok) => {
			const timer = setTimeout(ok, 2500)
			map.once('idle', () => {
				clearTimeout(timer)
				ok()
			})
		})
	for (let i = stops; i >= 0; i--) {
		map.jumpTo(wayIn(to, from, i / stops))
		await idle()
	}
}

/** A slow turn around the place, for a still scene that should keep some depth. Returns a function that stops it. */
export function orbit(map: MapLibreMap, degreesPerSecond = 1.2) {
	let raf = 0
	let last = performance.now()
	const step = (now: number) => {
		map.setBearing(map.getBearing() + ((now - last) / 1000) * degreesPerSecond)
		last = now
		raf = requestAnimationFrame(step)
	}
	raf = requestAnimationFrame(step)
	return () => cancelAnimationFrame(raf)
}
