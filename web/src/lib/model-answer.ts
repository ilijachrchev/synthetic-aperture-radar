// The model's answer in the flood game (src/components/game): every cell of the game scored by one model map,
// baked by scripts/bake_prediction.py into public/layers/<site>/prediction/game.json. The game takes the model's top
// cells as its picks and judges them with its own rule against the NISAR pass, the same way it judges the player.
//
// The map is set in the bake (GAME_MAP): now the replay issued before the storm, which was given the rain that fell,
// while the player only had the forecast. The game says so.

export type ModelGame = {
	site: string
	baked_utc: string
	/** the bake of game.json the cells were scored on: another bake has other cells, and then this is not used */
	game_made_utc: string
	map: string
	issued_from_sensor: string
	issue_time_utc: string
	target_time_utc: string
	/** the rain the model was given between the two maps, and whether it is the rain that fell or a forecast */
	rain_mm: number
	rain: 'fell' | 'forecast'
	rule: string
	/** one per cell of game.json, in its order: mean likelihood of new water, 0 to 100; null for a cell with no land */
	scores: (number | null)[]
	sources: Record<string, string>
}

/** prediction/game.json of a site, or null when there is none */
export async function loadModelGame(root: string): Promise<ModelGame | null> {
	try {
		const r = await fetch(`${root}/prediction/game.json`)
		return r.ok ? ((await r.json()) as ModelGame) : null
	} catch {
		return null
	}
}

/** the model's n picks: its highest scores, the earlier cell first on a tie */
export function modelPicks(m: ModelGame, n: number): number[] {
	return m.scores
		.map((s, i) => ({ s, i }))
		.filter((x): x is { s: number; i: number } => x.s !== null)
		.sort((a, b) => b.s - a.s || a.i - b.i)
		.slice(0, n)
		.map((x) => x.i)
}
