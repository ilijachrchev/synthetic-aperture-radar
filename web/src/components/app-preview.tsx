'use client'

import { Layers, Pause, Play } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { BEATS } from '@/content/landing'
import type { Pass } from '@/lib/radar'
import './app-preview.css'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dd = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`
const RAIL = [
	{ key: 'water', label: 'Farm water', where: 'Albufera' },
	{ key: 'fire', label: 'Fire scar', where: "Serra d'Espadà" },
	{ key: 'sink', label: 'Sinking ground', where: 'Lorca' },
	{ key: 'quake', label: 'Earthquake', where: 'Panama' },
]
// where the city and the lagoon sit in the Valencia box (-0.78, 38.92, 0.02, 39.70)
const pin = (lon: number, lat: number) => ({ left: `${((lon + 0.78) / 0.8) * 100}%`, top: `${((39.7 - lat) / 0.78) * 100}%` })

/** The map app shown as itself in a browser window: the season over the Albufera plays pass by pass while in view. */
export function AppPreview({ passes, head, line }: { passes: Pass[]; head: { a: string; b: string; accent: string }; line: string }) {
	const ref = useRef<HTMLDivElement>(null)
	const [i, setI] = useState(passes.length - 1)
	const [playing, setPlaying] = useState(true)
	const [inView, setInView] = useState(false)

	useEffect(() => {
		const el = ref.current
		if (!el) return
		const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.35 })
		io.observe(el)
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) setPlaying(false)
		return () => io.disconnect()
	}, [])
	useEffect(() => {
		if (!playing || !inView) return
		const id = window.setInterval(() => setI((v) => (v + 1) % passes.length), 1150)
		return () => window.clearInterval(id)
	}, [playing, inView, passes.length])

	const cur = passes[i]
	const month = Number(cur.dates[0].slice(5, 7))
	const beat = BEATS.find((b) => b.months.includes(month))

	return (
		<section id="app" className="sec appv">
			<div className="sec-head" data-reveal="rise">
				<h2 className="sec-title">
					{head.a}
					<br />
					{head.b} <em>{head.accent}</em>
				</h2>
				<p className="sec-line">{line}</p>
			</div>

			<div ref={ref} className="appv-window" data-reveal="rise">
				<div className="appv-bar">
					<span className="appv-dots">
						<i />
						<i />
						<i />
					</span>
					<span className="appv-url">dancing-with-the-sars / map</span>
					<span />
				</div>
				<div className="appv-app">
					<aside className="appv-rail">
						<p className="appv-rail-title">Stories</p>
						{RAIL.map((r, k) => (
							<div key={r.key} className="appv-story" data-on={k === 0 || undefined}>
								<img src={`/img/icons/${r.key}.webp`} alt="" width={40} height={40} />
								<span>
									<b>{r.label}</b>
									<small>{r.where}</small>
								</span>
							</div>
						))}
					</aside>

					<div className="appv-map">
						<div className="appv-radar">
							{passes.map((p, k) => (
								<img key={p.img} src={p.img!} alt={k === i ? `NISAR radar over the Valencia coast, ${dd(p.dates[0])}` : ''} data-on={k === i || undefined} loading="lazy" />
							))}
							<span className="appv-pin" style={pin(-0.376, 39.47)}>
								<i />
								Valencia
							</span>
							<span className="appv-pin" style={pin(-0.35, 39.33)}>
								<i />
								Albufera
							</span>
						</div>
						<div className="appv-chip appv-crumb">Albufera · Valencia</div>
						<div className="appv-chip appv-layer">
							<Layers size={14} strokeWidth={1.8} /> Radar · HH, HV
						</div>

						<div className="appv-panel">
							<p className="appv-k">Pass</p>
							<p className="appv-date">{dd(cur.dates[0])}</p>
							<p className="appv-sub">
								Track {cur.track} {cur.dir === 'D' ? 'descending' : 'ascending'} · frame {cur.frame}
							</p>
							{beat && (
								<div className="appv-beat">
									<b>{beat.title}</b>
									<span>{beat.line}</span>
								</div>
							)}
						</div>

						<div className="appv-timeline">
							<button type="button" className="appv-play" onClick={() => setPlaying((v) => !v)} aria-label={playing ? 'Pause' : 'Play'}>
								{playing ? <Pause size={15} strokeWidth={2} /> : <Play size={15} strokeWidth={2} />}
							</button>
							<ol>
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
											aria-label={`Show ${dd(p.dates[0])}`}
										>
											<span />
										</button>
										{(k === 0 || p.dates[0].slice(5, 7) !== passes[k - 1].dates[0].slice(5, 7)) && <em>{MONTHS[Number(p.dates[0].slice(5, 7)) - 1]}</em>}
									</li>
								))}
							</ol>
							<span className="appv-count">
								{String(i + 1).padStart(2, '0')} / {String(passes.length).padStart(2, '0')}
							</span>
						</div>
					</div>
				</div>
			</div>
		</section>
	)
}
