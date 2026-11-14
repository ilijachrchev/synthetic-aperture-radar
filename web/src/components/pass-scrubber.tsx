'use client'

import { useEffect, useRef, useState } from 'react'
import { BEATS, PASSES_HEAD, PASSES_LINE } from '@/content/landing'
import type { Pass } from '@/lib/radar'
import './pass-scrubber.css'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const fmt = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`

// Where the Albufera and the city sit inside the Valencia box (-0.78, 38.92, 0.02, 39.70).
const BOX = { w: -0.78, s: 38.92, e: 0.02, n: 39.7 }
const at = (lon: number, lat: number) => ({ left: `${((lon - BOX.w) / (BOX.e - BOX.w)) * 100}%`, top: `${((BOX.n - lat) / (BOX.n - BOX.s)) * 100}%` })
const MARKS = [
	{ name: 'Albufera', ...at(-0.35, 39.33) },
	{ name: 'Valencia', ...at(-0.376, 39.47) },
]

/**
 * The pinned stage: scrolling plays every pass of one track over the Valencia coast. The frame holds still while
 * the passes crossfade (opacity only), the readout counts, and the beat on the left follows the month.
 */
export function PassScrubber({ passes }: { passes: Pass[] }) {
	const ref = useRef<HTMLElement>(null)
	const [i, setI] = useState(passes.length - 1)
	const [progress, setProgress] = useState(1)

	useEffect(() => {
		const el = ref.current
		if (!el) return
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
		let raf = 0
		const update = () => {
			raf = 0
			const r = el.getBoundingClientRect()
			const span = r.height - window.innerHeight
			const p = Math.min(1, Math.max(0, -r.top / Math.max(1, span)))
			setProgress(p)
			setI(Math.min(passes.length - 1, Math.floor(p * passes.length)))
		}
		const onScroll = () => {
			if (!raf) raf = requestAnimationFrame(update)
		}
		update()
		window.addEventListener('scroll', onScroll, { passive: true })
		window.addEventListener('resize', onScroll)
		return () => {
			window.removeEventListener('scroll', onScroll)
			window.removeEventListener('resize', onScroll)
			cancelAnimationFrame(raf)
		}
	}, [passes.length])

	const cur = passes[i]
	const month = Number(cur.dates[0].slice(5, 7))
	const beat = BEATS.findIndex((b) => b.months.includes(month))

	return (
		<section id="passes" ref={ref} className="scrub" style={{ ['--steps' as string]: passes.length }}>
			<div className="scrub-stage">
				<div className="scrub-copy">
					<h2 className="sec-title scrub-title">
						{PASSES_HEAD.a}
						<br />
						{PASSES_HEAD.b} <em>{PASSES_HEAD.accent}</em>
					</h2>
					<p className="scrub-line">{PASSES_LINE}</p>
					<ol className="scrub-beats" aria-label="What to look for">
						{BEATS.map((b, k) => (
							<li key={b.title} data-on={k === beat || undefined}>
								<b>{b.title}</b>
								<span>{b.line}</span>
							</li>
						))}
					</ol>
				</div>

				<figure className="scrub-frame">
					<div className="scrub-window">
						{passes.map((p, k) => (
							<img key={p.img} src={p.img!} alt={k === i ? `NISAR radar, Valencia coast, ${fmt(p.dates[0])}` : ''} data-on={k === i || undefined} loading={k > 2 && k < passes.length - 1 ? 'lazy' : 'eager'} />
						))}
						{MARKS.map((m) => (
							<span key={m.name} className="scrub-mark" style={{ left: m.left, top: m.top }}>
								<i />
								{m.name}
							</span>
						))}
						<span className="scrub-corner tl" />
						<span className="scrub-corner tr" />
						<span className="scrub-corner bl" />
						<span className="scrub-corner br" />
					</div>
					<figcaption className="scrub-readout">
						<span className="scrub-date">{fmt(cur.dates[0])}</span>
						<span>
							Track {cur.track} {cur.dir === 'D' ? 'descending' : 'ascending'} · frame {cur.frame}
						</span>
						<span className="scrub-count">
							{String(i + 1).padStart(2, '0')} / {String(passes.length).padStart(2, '0')}
						</span>
						<span className="scrub-bar">
							<span style={{ transform: `scaleX(${Math.max(0.02, progress)})` }} />
						</span>
					</figcaption>
				</figure>
			</div>
		</section>
	)
}
