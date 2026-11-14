// The map tiles of the Valencia stories are part of the app (public/tiles, made by scripts/bake_tiles.py): the
// cloudless picture of EOX, the relief of Mapterhorn, the Blue Marble of NASA and the names of EOX, for the boxes and
// zooms the three stories show. So a story page needs no remote tile server, and its first view does not wait on four
// of them. The sources ask for their tiles here; `transformTile` sends a tile outside the boxes (someone flew far away)
// on to its own server. `?offline` on the page keeps every tile here, to check that the stories need nothing else.
import type { RequestParameters, ResourceType } from 'maplibre-gl'
import index from '@/data/tiles.json'

export type TileSource = 'base' | 'names' | 'far' | 'dem'
type Entry = { ext: string; remote: string; boxes: Record<string, number[][]> }
const SOURCES = index.sources as unknown as Record<TileSource, Entry>

/** the tile address of a source, as a MapLibre source takes it */
export const tilesOf = (source: TileSource) => `/tiles/${source}/{z}/{x}/{y}.${SOURCES[source].ext}`

/** the highest zoom of a source that is here: the source stops there and MapLibre scales its tiles up beyond */
export const maxZoomOf = (source: TileSource) => Math.max(...Object.keys(SOURCES[source].boxes).map(Number))

/** whether a tile of a source is here */
export function isBaked(source: TileSource, z: number, x: number, y: number) {
	const boxes = SOURCES[source].boxes[z]
	return !!boxes && boxes.some(([x0, y0, x1, y1]) => x >= x0 && x <= x1 && y >= y0 && y <= y1)
}

const LOCAL = /\/tiles\/(base|names|far|dem)\/(\d+)\/(\d+)\/(\d+)\.\w+$/

/** how many tiles came from here and how many went to their own server, for the checks */
export const tileCount = { here: 0, away: 0 }

let offline: boolean | null = null

/** MapLibre's transformRequest: a tile that is not here goes to its own server */
export function transformTile(url: string, type?: ResourceType): RequestParameters | undefined {
	if (type !== 'Tile') return undefined
	const m = LOCAL.exec(url)
	if (!m) return undefined
	const source = m[1] as TileSource
	const [z, x, y] = [Number(m[2]), Number(m[3]), Number(m[4])]
	if (isBaked(source, z, x, y)) {
		tileCount.here++
		return undefined
	}
	offline ??= new URLSearchParams(window.location.search).has('offline')
	if (offline) return undefined
	tileCount.away++
	return { url: SOURCES[source].remote.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y)) }
}
