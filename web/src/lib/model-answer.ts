// The model's answer to the flood game (src/components/game, content/game.ts), for its reveal screen to show next
// to the player's, if the game's author wants it. Nothing here changes the game.
//
// The game shows the marsh on the NISAR pass of 16 Oct and asks for the cells that will be under new water on the
// pass of 28 Oct. The model map that answers the same question is the replay issued before the storm
// (replay_2026-10-28_prestorm in prediction.json): issued from the Sentinel-1 map of 17 Oct, for the NISAR pass of
// 28 Oct, given the rain that fell in between. So it is a reconstruction, not a forecast: it knew the rain, the
// player only had the forecast. Say so wherever it is shown.
//
// This gives the model's cells and its values only. It does not score the model against the radar: a score of
// the model on the DANA belongs to the team's DANA test and comes from its own result file.
import type { Bounds } from './gl-quad'
import { type Prediction, type PredictionMap, fileUrl, loadPrediction, readBlock, windowOf } from './prediction'

/** the part of a game cell (game.json of scripts/bake_game.py) this needs */
export type GameCellBox = { i: number; box: Bounds }

export type ModelCell = {
	i: number
	/** mean relative likelihood of water, 0 to 100, over the cell's ground that was dry on the issue map */
	mean: number | null
	/** share of that ground at or above the model's line of likely new water (thresholds.new_water) */
	likely: number
	/** pixels of the cell that count: the model's own prediction (evidence 0) on ground dry on the issue map */
	pixels: number
}

export type ModelAnswer = {
	map: PredictionMap
	/** the cells the model ranks highest, most likely first */
	picks: number[]
	/** every cell, in the order of the game's cells */
	cells: ModelCell[]
	/** what to say next to it, made from prediction.json */
	caption: string
	note: string
}

export const GAME_MAP = 'replay_2026-10-28_prestorm'

/**
 * Rank the game's cells by the model map: mean likelihood of new water over the ground the model predicts and that
 * was dry when the map was issued. `picks` is how many cells the model marks (the game lets the player mark 10).
 */
export async function modelAnswer(cells: GameCellBox[], opts: { root?: string; mapId?: string; picks?: number } = {}): Promise<ModelAnswer | null> {
	const root = opts.root ?? '/layers/pego_oliva'
	const p: Prediction | null = await loadPrediction(root)
	const map = p ? [...p.replays, ...p.scenarios].find((m) => m.id === (opts.mapId ?? GAME_MAP)) : undefined
	if (!p || !map || !cells.length) return null
	const url = fileUrl(root, p, map.data)
	const plane = (name: string) => map.data_planes.indexOf(name)
	const [iEv, iW, iDry, iNew] = [plane('evidence'), plane('water_likelihood_pct'), plane('dry_before'), plane('new_water_likelihood_pct')]

	// one window over the whole playfield, then each cell is a part of it
	const wins = cells.map((c) => windowOf(p.grid, c.box))
	const row0 = Math.min(...wins.map((w) => w.row0))
	const col0 = Math.min(...wins.map((w) => w.col0))
	const h = Math.max(...wins.map((w) => w.row0 + w.h)) - row0
	const w = Math.max(...wins.map((x) => x.col0 + x.w)) - col0
	const [ev, water, dry] = await Promise.all([readBlock(url, iEv, row0, col0, h, w), readBlock(url, iW, row0, col0, h, w), readBlock(url, iDry >= 0 ? iDry : iNew, row0, col0, h, w)])
	const line = map.thresholds.new_water * 100

	const out: ModelCell[] = cells.map((c, k) => {
		const win = wins[k]
		let sum = 0
		let n = 0
		let over = 0
		for (let r = win.row0; r < win.row0 + win.h; r++) {
			for (let q = win.col0; q < win.col0 + win.w; q++) {
				const j = (r - row0) * w + (q - col0)
				const isDry = iDry >= 0 ? dry[j] === 1 : dry[j] !== 255
				if (ev[j] !== 0 || water[j] === 255 || !isDry) continue
				sum += water[j]
				n++
				if (water[j] >= line) over++
			}
		}
		return { i: c.i, mean: n ? Math.round((sum / n) * 10) / 10 : null, likely: n ? Math.round((over / n) * 1000) / 1000 : 0, pixels: n }
	})
	const picks = [...out]
		.filter((c) => c.mean !== null)
		.sort((a, b) => b.mean! - a.mean! || b.likely - a.likely)
		.slice(0, opts.picks ?? 10)
		.map((c) => c.i)
	const day = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
	return {
		map,
		picks,
		cells: out,
		caption: `The model's ${picks.length} cells, from its map issued on ${day(map.issue_time_utc)} for the pass of ${day(map.target_time_utc)}`,
		note: `A reconstruction, not a forecast: the model was given the ${Math.round(map.rain.rain_between_mm)} mm that fell after the ${map.issued_from_sensor ?? 'radar'} map of ${day(map.issue_time_utc)}. Relative likelihood, not depth.`,
	}
}
