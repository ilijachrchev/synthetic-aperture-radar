// What one spot of ground reads when it is clicked: the model's likelihood under the map shown, the NISAR water
// history of the pixel, the soil moisture before the storm and the land type. Every number is read from the baked
// files (lib/prediction.ts) and comes with the file it is from behind "Sources".

import { X } from 'lucide-react'
import { useState } from 'react'
import { utcDay } from '@/lib/flood-model'
import type { Prediction, SpotResult } from '@/lib/prediction'

const STATE = ['not seen', 'dry', 'water under plants', 'open water']
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const deg = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(4)} ${v >= 0 ? pos : neg}`

export function SpotPanel({
	result,
	loading,
	prediction,
	onClose,
	onGo,
}: {
	result: SpotResult | null
	loading: boolean
	/** the prediction.json of the site the spot lies in, for the sources */
	prediction: Prediction | null
	onClose: () => void
	onGo: (site: 'pego_oliva' | 'albufera') => void
}) {
	const [sources, setSources] = useState(false)
	if (!result && !loading) return null
	return (
		<aside className="sp" role="dialog" aria-label="This spot" data-loading={loading || undefined}>
			<button type="button" className="sp-close" onClick={onClose} aria-label="Close">
				<X size={15} strokeWidth={2.4} />
			</button>
			{loading && !result && <p className="sp-wait">Reading the files</p>}
			{result?.kind === 'outside' && (
				<>
					<p className="sp-head">No data here</p>
					<p className="sp-text">We cover Albufera and Pego-Oliva, the two boxes our model and our NISAR layers are made for.</p>
					<div className="sp-go">
						<button type="button" onClick={() => onGo('pego_oliva')}>
							Pego-Oliva
						</button>
						<button type="button" onClick={() => onGo('albufera')}>
							Albufera
						</button>
					</div>
				</>
			)}
			{result?.kind === 'error' && <p className="sp-text">The files of this spot did not load: {result.message}</p>}
			{result?.kind === 'spot' && <Spot spot={result.spot} prediction={prediction} sources={sources} setSources={setSources} />}
		</aside>
	)
}

function Spot({ spot, prediction, sources, setSources }: { spot: Extract<SpotResult, { kind: 'spot' }>['spot']; prediction: Prediction | null; sources: boolean; setSources: (v: boolean) => void }) {
	const m = spot.model
	const thr = m ? Math.round(m.map.thresholds.water * 100) : 31
	const seen = spot.history?.filter((h) => h.state > 0) ?? []
	const wet = seen.filter((h) => h.state >= 2)
	const issued = m ? utcDay(Date.parse(m.map.issue_time_utc), false) : ''
	const evidence = m && m.evidence !== 0 && m.evidence !== 255 ? prediction?.evidence?.[String(m.evidence)] : null
	return (
		<>
			<p className="sp-head">
				This spot <small>{spot.name}</small>
			</p>
			<p className="sp-where mono">
				{deg(spot.lngLat[1], 'N', 'S')} · {deg(spot.lngLat[0], 'E', 'W')}
			</p>

			<section className="sp-part">
				<h3>Model{m ? ` · ${m.map.mode === 'scenario' ? m.map.caption.title : `map for ${utcDay(Date.parse(m.map.target_time_utc), false)}`}` : ''}</h3>
				{!m || m.evidence === 255 || m.water === null ? (
					<p className="sp-text">Sea, or outside the land the model covers.</p>
				) : (
					<>
						<p className="sp-num">
							<b className="display">{m.water}</b>
							<span>of 100, relative likelihood of water</span>
						</p>
						<div className="sp-bar" aria-hidden>
							<i style={{ width: `${m.water}%` }} />
							<s style={{ left: `${m.map.thresholds.water * 100}%` }} />
						</div>
						<p className="sp-text">
							{m.water >= m.map.thresholds.water * 100 ? `Inside the dashed line: likely water (${thr} or more).` : `Outside the dashed line, which starts at ${thr}.`}{' '}
							{m.evidence === 1
								? 'Permanent water.'
								: m.dryBefore
									? `Dry on the ${m.map.issued_from_sensor ?? 'radar'} map of ${issued}: water here would be new.`
									: m.dryBefore === false
										? `Already water on the ${m.map.issued_from_sensor ?? 'radar'} map of ${issued}.`
										: ''}
						</p>
						{evidence && <p className="sp-note">{cap(evidence)}.</p>}
						<p className="sp-note">Not a probability and not depth: how likely water is here compared with other ground.</p>
					</>
				)}
			</section>

			{spot.history && (
				<section className="sp-part">
					<h3>NISAR water, pass by pass</h3>
					<ol className="sp-dots">
						{spot.history.map((h) => (
							<li key={h.time} data-state={h.state} title={`${utcDay(Date.parse(h.time))}: ${STATE[h.state]}`} />
						))}
					</ol>
					<p className="sp-ends mono">
						<span>{utcDay(Date.parse(spot.history[0].time), false)}</span>
						<span>{utcDay(Date.parse(spot.history[spot.history.length - 1].time), false)}</span>
					</p>
					<p className="sp-text">
						{seen.length === 0
							? 'No pass saw this pixel.'
							: wet.length === 0
								? `Dry on all ${seen.length} passes that saw it.`
								: `Water on ${wet.length} of ${seen.length} passes, last on ${utcDay(Date.parse(wet[wet.length - 1].time), false)}.`}
					</p>
					{spot.note && <p className="sp-note">{spot.note}</p>}
				</section>
			)}

			{spot.soil && (
				<section className="sp-part sp-row">
					<h3>Soil before the storm</h3>
					<p className="sp-text">
						{spot.soil.value === null ? (
							'No NISAR soil moisture here.'
						) : (
							<>
								<b>{spot.soil.value.toFixed(2)} m³/m³</b> on {utcDay(Date.parse(`${spot.soil.date}T12:00:00Z`), false)}
								{spot.soil.median !== null ? `, the site's median ${spot.soil.median.toFixed(2)}` : ''}
							</>
						)}
					</p>
				</section>
			)}

			{spot.land && (
				<section className="sp-part sp-row">
					<h3>Land</h3>
					<p className="sp-text">
						<b>{spot.land.name}</b>
					</p>
				</section>
			)}

			<button type="button" className="sp-src" aria-expanded={sources} onClick={() => setSources(!sources)}>
				Sources
			</button>
			{sources && prediction && (
				<ul className="sp-sources">
					{m && (
						<li>
							<b>Model</b> {prediction.model}, {String(m.map.sources.water_likelihood)} (model {prediction.source.model_sha256_16}, baked {prediction.baked_utc})
						</li>
					)}
					{prediction.inspect.history && (
						<li>
							<b>Water history</b> {prediction.inspect.history.product}: {prediction.inspect.history.source}
						</li>
					)}
					{prediction.inspect.soil && (
						<li>
							<b>Soil</b> {prediction.inspect.soil.product} ({prediction.inspect.soil.maturity?.toLowerCase()}, {prediction.inspect.soil.resolution_m} m cells): {prediction.inspect.soil.source}
						</li>
					)}
					{prediction.inspect.landcover && (
						<li>
							<b>Land</b> {prediction.inspect.landcover.product}: {prediction.inspect.landcover.source}
						</li>
					)}
				</ul>
			)}
		</>
	)
}
