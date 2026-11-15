// What one spot of the street map reads when it is clicked: the official flood zone there, what really flooded
// (Copernicus EMS in 2024 and 2026, NISAR in 2026), our model's likelihood under the map shown, the soil moisture
// before the storm and the land type. Every value comes from a baked file or a shape on the map, and "Sources" says
// which (explore-app.tsx gathers them).

import { X } from 'lucide-react'
import { useState } from 'react'
import { ZONES } from '@/content/explore'
import { utcDay } from '@/lib/flood-model'
import type { PredictionMap } from '@/lib/prediction'

export type ExploreSpotInfo = {
	lngLat: [number, number]
	municipality: string | null
	/** the zone of the highest probability at the spot; 'none' outside every zone; null where no zones were mapped */
	zone: 'frequent' | 'occasional' | 'rare' | 'none' | null
	floods: { year: number; code: string; observed: string }[]
	/** the damage grade of a building Copernicus graded at the spot, in 2024 */
	building: string | null
	/** a water mark surveyed at the spot after the 2024 flood, in words ("1.4 m, surveyed by UPV, Torrent") */
	mark: string | null
	/** PR #35's DANA code at the spot (0 dry, 1 water on both dates, 2 new water, 3 gone, 4 permanent), and whether the
	 *  spot is in the still-flooded layer; null outside the NISAR boxes */
	nisar: { code: number; before: string; after: string; still: boolean } | null
	model: { map: PredictionMap; evidence: number; water: number | null; dryBefore: boolean | null; evidenceText: string | null } | null
	soil: { value: number | null; date: string; median: number | null } | null
	land: string | null
	site: string | null
	sources: string[]
}

export type ExploreSpotResult = { kind: 'spot'; info: ExploreSpotInfo } | { kind: 'outside'; lngLat: [number, number] } | { kind: 'error'; message: string }

const NISAR_TEXT: Record<number, string> = {
	0: 'dry on both passes',
	1: 'open water on both passes',
	2: 'new open water: dry on the first pass, water on the second',
	3: 'open water on the first pass, gone on the second',
	4: 'permanent water',
}
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const deg = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(4)} ${v >= 0 ? pos : neg}`
const day = (iso: string) => utcDay(Date.parse(iso.length === 10 ? `${iso}T12:00:00Z` : iso), false)

export function ExploreSpot({ result, loading, onClose, onGo }: { result: ExploreSpotResult | null; loading: boolean; onClose: () => void; onGo: (place: string) => void }) {
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
					<p className="sp-text">We cover L&apos;Horta Sud, the Albufera and Pego-Oliva: the places our zones, flood maps, NISAR layers and model are made for.</p>
					<div className="sp-go">
						<button type="button" onClick={() => onGo('pego')}>
							Pego-Oliva
						</button>
						<button type="button" onClick={() => onGo('horta')}>
							L&apos;Horta Sud
						</button>
						<button type="button" onClick={() => onGo('albufera')}>
							Albufera
						</button>
					</div>
				</>
			)}
			{result?.kind === 'error' && <p className="sp-text">The files of this spot did not load: {result.message}</p>}
			{result?.kind === 'spot' && <Info info={result.info} sources={sources} setSources={setSources} />}
		</aside>
	)
}

function Info({ info, sources, setSources }: { info: ExploreSpotInfo; sources: boolean; setSources: (v: boolean) => void }) {
	const zone = ZONES.find((z) => z.key === info.zone)
	const m = info.model
	const thr = m ? Math.round(m.map.thresholds.new_water * 100) : 20
	const counted = !!m && m.evidence === 0 && m.dryBefore === true
	const flooded = info.floods.length > 0 || !!info.building || !!info.mark || (info.nisar && (info.nisar.code === 1 || info.nisar.code === 2))
	return (
		<>
			<p className="sp-head">
				This spot {info.municipality && <small>{info.municipality}</small>}
			</p>
			<p className="sp-where mono">
				{deg(info.lngLat[1], 'N', 'S')} · {deg(info.lngLat[0], 'E', 'W')}
			</p>

			<section className="sp-part">
				<h3>Official flood zone</h3>
				{info.zone === null ? (
					<p className="sp-text">No official zones loaded here: we checked the 12 towns of L&apos;Horta Sud, Chiva, Pego and Oliva.</p>
				) : zone ? (
					<ul className="sp-facts">
						<li>
							<i style={{ background: zone.color }} />
							<span>
								<b>{zone.label}</b>, {zone.name}
								<small>{zone.detail} (SNCZI)</small>
							</span>
						</li>
					</ul>
				) : (
					<p className="sp-text">Outside every official flood zone.</p>
				)}
			</section>

			<section className="sp-part">
				<h3>What really flooded</h3>
				{!flooded && !info.nisar && <p className="sp-text">No flood mapped here.</p>}
				<ul className="sp-facts">
					{info.floods.map((f) => (
						<li key={`${f.year}${f.observed}`}>
							<i style={{ background: 'var(--ems)' }} />
							<span>
								{f.year}: {f.observed === 'flood_trace' ? 'flood traces (the water had gone)' : 'water seen from space'}
								<small>Copernicus EMS {f.code}</small>
							</span>
						</li>
					))}
					{info.building && (
						<li>
							<i style={{ background: '#ff6b3d', borderRadius: '50%' }} />
							<span>
								2024: a building graded &ldquo;{info.building.toLowerCase()}&rdquo;
								<small>Copernicus EMS EMSR773</small>
							</span>
						</li>
					)}
					{info.mark && (
						<li>
							<i style={{ background: '#2463eb', borderRadius: '50%' }} />
							<span>
								2024: water stood {info.mark}
								<small>measured mark, Institut Cartogràfic Valencià</small>
							</span>
						</li>
					)}
					{info.nisar && info.nisar.code !== 255 && (
						<li>
							<i style={{ background: info.nisar.code === 2 ? '#40aaff' : info.nisar.code === 1 ? '#144096' : 'transparent', boxShadow: 'inset 0 0 0 1.5px #40aaff' }} />
							<span>
								NISAR, {day(info.nisar.before)} to {day(info.nisar.after)} 2026: {NISAR_TEXT[info.nisar.code] ?? 'no reading'}
								<small>track 066 D, the team CV model</small>
							</span>
						</li>
					)}
					{info.nisar?.still && (
						<li>
							<i style={{ background: 'var(--still)' }} />
							<span>
								Still under water on {day(info.nisar.after)}, inside the EMSR935 flood map
								<small>NISAR, the team CV model</small>
							</span>
						</li>
					)}
				</ul>
			</section>

			{m && (
				<section className="sp-part">
					<h3>Our model · {m.map.mode === 'scenario' ? m.map.caption.title : `map for ${day(m.map.target_time_utc)}`}</h3>
					{m.evidence === 255 || m.water === null ? (
						<p className="sp-text">Sea, or outside the land the model covers.</p>
					) : (
						<>
							<p className="sp-num">
								<b className="display">{m.water}</b>
								<span>of 100, relative likelihood of water</span>
							</p>
							<div className="sp-bar" aria-hidden>
								<i style={{ width: `${m.water}%` }} />
								<s style={{ left: `${m.map.thresholds.new_water * 100}%` }} />
							</div>
							<p className="sp-text">
								{counted ? (m.water >= m.map.thresholds.new_water * 100 ? `Inside the dashed line: likely new water (${thr} or more). ` : `Outside the dashed line, which starts at ${thr}. `) : ''}
								{m.evidence === 1
									? 'Permanent water.'
									: m.dryBefore
										? `Dry on the ${m.map.issued_from_sensor ?? 'radar'} map of ${day(m.map.issue_time_utc)}: water here would be new.`
										: m.dryBefore === false
											? `Already water on the ${m.map.issued_from_sensor ?? 'radar'} map of ${day(m.map.issue_time_utc)}.`
											: ''}
							</p>
							{m.evidenceText && <p className="sp-note">{cap(m.evidenceText)}.</p>}
							<p className="sp-note">Not a probability and not depth: how likely water is here compared with other ground.</p>
						</>
					)}
				</section>
			)}

			{info.soil && (
				<section className="sp-part sp-row">
					<h3>Soil before the storm</h3>
					<p className="sp-text">
						{info.soil.value === null ? (
							'No NISAR soil moisture here.'
						) : (
							<>
								<b>{info.soil.value.toFixed(2)} m³/m³</b> on {day(info.soil.date)}
								{info.soil.median !== null ? `, the area's median ${info.soil.median.toFixed(2)}` : ''}
							</>
						)}
					</p>
				</section>
			)}

			{info.land && (
				<section className="sp-part sp-row">
					<h3>Land</h3>
					<p className="sp-text">
						<b>{info.land}</b>
					</p>
				</section>
			)}

			<button type="button" className="sp-src" aria-expanded={sources} onClick={() => setSources(!sources)}>
				Sources
			</button>
			{sources && (
				<ul className="sp-sources">
					{info.sources.map((s) => (
						<li key={s}>{s}</li>
					))}
				</ul>
			)}
		</>
	)
}
