'use client'

import { Pause, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ChangeLayer } from './change-layer'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dd = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`

// where the city and the lagoon sit in the Valencia box (-0.78, 38.92, 0.02, 39.70)
const pin = (lon: number, lat: number) => ({ left: `${((lon + 0.78) / 0.8) * 100}%`, top: `${((39.7 - lat) / 0.78) * 100}%` })

/**
 * The hero's picture is the product itself: every pass of one track over the Valencia coast, and the water read
 * from each pass animated on top of it, spreading and draining through the season. It keeps moving while it is on
 * screen and has a pause button; under reduced motion it rests on the latest pass.
 */
export function LivingRadar({ passes, track }: { passes: { img: string; date: string }[]; track: string }) {
	const [i, setI] = useState(0)
	const [playing, setPlaying] = useState(true)

	useEffect(() => {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
			setPlaying(false)
			setI(passes.length - 1)
		}
	}, [passes.length])

	return (
		<div className="lr">
			<div className="lr-frame">
				{passes.map((p, k) => (
					<img key={p.img} src={p.img} alt={k === i ? `NISAR radar of the Valencia coast, ${dd(p.date)} 2026` : ''} data-on={k === i || undefined} />
				))}
				<ChangeLayer className="lr-change" kind="water" frames={passes.map((p) => p.img)} index={i} playing={playing} onIndex={setI} speed={0.6} />
				<span className="lr-pin" style={pin(-0.376, 39.47)}>
					<i /> Valencia
				</span>
				<span className="lr-pin" style={pin(-0.35, 39.33)}>
					<i /> Albufera
				</span>
				<p className="lr-live mono">
					<span /> Real NISAR passes · track {track}
				</p>
				<div className="lr-date">
					<b className="display" key={passes[i].date}>
						{dd(passes[i].date)}
					</b>
					<small className="mono">2026</small>
				</div>
				<p className="lr-key">
					<i aria-hidden /> Wet ground, read from each pass
				</p>
			</div>
			<div className="lr-bar">
				<button type="button" onClick={() => setPlaying((v) => !v)} aria-label={playing ? 'Pause the season' : 'Play the season'}>
					{playing ? <Pause size={15} strokeWidth={2.4} /> : <Play size={15} strokeWidth={2.4} />}
				</button>
				<ol aria-label="Passes">
					{passes.map((p, k) => (
						<li key={p.img}>
							<button
								type="button"
								data-on={k === i || undefined}
								data-past={k < i || undefined}
								onClick={() => {
									setPlaying(false)
									setI(k)
								}}
								aria-label={`Show ${dd(p.date)}`}
							/>
						</li>
					))}
				</ol>
				<span className="mono lr-count">
					{String(i + 1).padStart(2, '0')}/{passes.length}
				</span>
			</div>
		</div>
	)
}
