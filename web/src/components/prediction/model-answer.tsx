'use client'

// A drop-in for the flood game's reveal screen (components/game/game-app.tsx), if its author wants it: the model's
// cells next to the player's. Not wired into the game; the game decides. Two ways to use it:
//
//   <ModelAnswerCard cells={game.cells} picked={picked} />          the words, in the reveal panel
//   paintModelCells(map, picks)                                     the cells, as dashed squares on the game's map
//
// It shows the model's picks and how many the player shares with it. It does not score the model against the
// radar (lib/model-answer.ts says why).

import type { Map as MapLibreMap } from 'maplibre-gl'
import { useEffect, useState } from 'react'
import { type GameCellBox, type ModelAnswer, modelAnswer } from '@/lib/model-answer'
import './model-answer.css'

/** the model's answer for these cells, once it is read (null until then, or when there is no model map) */
export function useModelAnswer(cells: GameCellBox[] | null | undefined, opts?: { root?: string; mapId?: string; picks?: number }) {
	const [answer, setAnswer] = useState<ModelAnswer | null>(null)
	const key = `${opts?.root ?? ''}|${opts?.mapId ?? ''}|${opts?.picks ?? ''}`
	useEffect(() => {
		if (!cells?.length) return
		let gone = false
		modelAnswer(cells, opts)
			.then((a) => !gone && setAnswer(a))
			.catch(() => !gone && setAnswer(null))
		return () => {
			gone = true
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [cells, key])
	return answer
}

export function ModelAnswerCard({ cells, picked, opts }: { cells: GameCellBox[] | null | undefined; picked: Set<number>; opts?: { root?: string; mapId?: string; picks?: number } }) {
	const answer = useModelAnswer(cells, opts)
	if (!answer) return null
	const shared = answer.picks.filter((i) => picked.has(i)).length
	return (
		<div className="ma">
			<p className="ma-head">{answer.caption}</p>
			<p className="ma-text">
				You and the model marked <b>{shared}</b> of the same cells.
			</p>
			<p className="ma-note">{answer.note}</p>
		</div>
	)
}

/** the model's cells as dashed squares on the game's map, over the game's own `cells` source (ids are cell numbers) */
export function paintModelCells(map: MapLibreMap, picks: number[], opts: { source?: string; id?: string } = {}) {
	const source = opts.source ?? 'cells'
	const id = opts.id ?? 'model-cells'
	if (!map.getSource(source)) return
	const filter = ['in', ['id'], ['literal', picks]] as never
	if (map.getLayer(id)) map.setFilter(id, filter)
	else map.addLayer({ id, type: 'line', source, filter, paint: { 'line-color': '#ffffff', 'line-width': 2.2, 'line-dasharray': [1.6, 1.2] } } as never)
}
