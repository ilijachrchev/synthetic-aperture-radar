// The flood game: one level, the DANA "Adam" storm replayed at the Pego-Oliva marsh. The player sees the last NISAR
// pass before the rain, marks the cells they think will be under water on the next pass, and is scored against that
// pass. Every number on the page comes from the baked files under public/layers/pego_oliva/ (game.json by
// scripts/bake_game.py, the frames by scripts/bake_water.py) or is named here with its source.

export const GAME = {
	key: 'game',
	path: '/game',
	root: '/layers/pego_oliva',
	series: 'nisar_066_D_069',
	title: 'Where will the water go?',
	place: 'Pego-Oliva marsh, Valencia',
	/** how many cells the player may mark */
	picks: 10,
	/** the storm, as the flood story dates it (content/stories.ts): the rain between the two passes */
	storm: { from: '2026-10-18T00:00:00Z', to: '2026-10-20T00:00:00Z' },
	/** what the team's flood alert said on the evening of the pass before, from the DANA replay in
	 *  data/prediction/flood/forecast.json (run 2026-10-16, ECMWF IFS 9 km): 82.6 mm over three days, amber */
	alert: { run: '16 Oct', mm3d: 83, level: 'amber' as const, threshold: 100 },
	brief: [
		'This is the marsh on the evening of 16 Oct 2026, on the last NISAR pass before the storm. The blue is the water the radar saw.',
		'That evening the weather model gave 83 mm of rain over the next three days: an amber alert, short of the 100 mm that counts as red.',
		'The next pass comes on 28 Oct. Mark the ten cells you think will be under new water by then.',
	],
	credit: 'NISAR: NASA-ISRO · Sentinel-1 water: OPERA DSWx-S1, NASA JPL · Flood map: Copernicus EMS · Terrain: Mapterhorn, MDT02 · Rain: Open-Meteo · EOX · OpenStreetMap',
	meta: {
		title: 'Where will the water go? · Through the Clouds',
		description: 'A game on real radar passes: see the Pego-Oliva marsh before the October 2026 storm, mark where you think the water will be, and learn from the pass that followed.',
	},
} as const
