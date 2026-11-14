'use client'

import { Layers } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Mark } from './brand'
import './story-tabs.css'

export type StoryCard = {
	key: string
	n: string
	tab: string
	title: string
	what: string
	where: string
	kind: string
	coverage: string
	note: string
	/** one or two real passes: [before, after] */
	views: { img: string; label: string }[]
	trackLabel: string
	/** every pass on that track, as fractions along Jun to Oct, with the compared ones flagged */
	ticks: { at: number; on: boolean }[]
}

/**
 * 8x.social's "You brief once" tour for this project: numbered tabs across the top, one line that swaps, and one
 * product card. Scroll moves through the four stories while the stage holds still; each card is the map app showing
 * that story's real passes, with a swipe that moves on its own between the two dates.
 */
export function StoryTabs({ stories }: { stories: StoryCard[] }) {
	const wrap = useRef<HTMLDivElement>(null)
	const [k, setK] = useState(0)
	const [f, setF] = useState(0)

	useEffect(() => {
		const el = wrap.current
		if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
		let raf = 0
		const update = () => {
			raf = 0
			const r = el.getBoundingClientRect()
			const p = Math.min(0.9999, Math.max(0, -r.top / Math.max(1, r.height - window.innerHeight)))
			const x = p * stories.length
			setK(Math.floor(x))
			setF(x - Math.floor(x))
		}
		const onScroll = () => {
			if (!raf) raf = requestAnimationFrame(update)
		}
		update()
		window.addEventListener('scroll', onScroll, { passive: true })
		return () => {
			window.removeEventListener('scroll', onScroll)
			cancelAnimationFrame(raf)
		}
	}, [stories.length])

	return (
		<div ref={wrap} className="st" style={{ ['--n' as string]: stories.length }}>
			<div className="st-stage">
				<ol className="st-tabs">
					{stories.map((s, i) => (
						<li key={s.key} data-on={i === k || undefined} data-done={i < k || undefined}>
							<span className="mono st-num">{s.n}</span>
							<img src={`/img/icons/${s.key}.webp`} alt="" width={30} height={30} />
							<span className="st-tab">{s.tab}</span>
							<span className="st-rail" aria-hidden>
								<span style={{ transform: `scaleX(${i < k ? 1 : i === k ? Math.max(0.04, f) : 0})` }} />
							</span>
						</li>
					))}
				</ol>

				<div className="st-lines">
					{stories.map((s, i) => (
						<p key={s.key} className="st-line" data-pos={i < k ? 'past' : i > k ? 'next' : 'now'} aria-hidden={i !== k}>
							{s.what}
						</p>
					))}
				</div>

				<div className="st-cards">
					{stories.map((s, i) => (
						<article key={s.key} className="st-card" data-on={i === k || undefined} aria-hidden={i !== k}>
							<div className="st-bar">
								<span className="st-crumb">
									<Mark size={16} />
									<b>Map</b>
									<i>/</i>
									{s.where}
								</span>
								<span className="st-chips">
									<span>
										<Layers size={13} strokeWidth={2} aria-hidden /> {s.kind}
									</span>
									<span className="mono">{s.trackLabel}</span>
								</span>
							</div>
							<div className="st-body">
								<div className={`st-view ${s.views.length > 1 ? 'is-swipe' : ''}`}>
									<img src={s.views[0].img} alt={`NISAR, ${s.where}, ${s.views[0].label}`} loading="lazy" />
									{s.views[1] && <img className="st-after" src={s.views[1].img} alt={`NISAR, ${s.where}, ${s.views[1].label}`} loading="lazy" />}
									{s.views[1] && <span className="st-handle" aria-hidden />}
									<span className="st-tag st-tag-a">{s.views[0].label}</span>
									{s.views[1] && <span className="st-tag st-tag-b">{s.views[1].label}</span>}
								</div>
								<aside className="st-panel">
									<img className="st-icon" src={`/img/icons/${s.key}.webp`} alt="" width={84} height={84} loading="lazy" />
									<p className="eyebrow">
										{s.n} · {s.kind}
									</p>
									<h3 className="display">{s.title}</h3>
									<dl>
										<div>
											<dt>Where</dt>
											<dd>{s.where}</dd>
										</div>
										<div>
											<dt>NISAR</dt>
											<dd className="mono">{s.coverage}</dd>
										</div>
									</dl>
									<p className="st-note">{s.note}</p>
									<div className="st-ticks" aria-label={`Passes on ${s.trackLabel}`}>
										{s.ticks.map((t, j) => (
											<span key={j} style={{ left: `${t.at * 100}%` }} data-on={t.on || undefined} />
										))}
										<em style={{ left: 0 }}>Jun</em>
										<em style={{ left: '50%' }}>Aug</em>
										<em style={{ right: 0 }}>Oct</em>
									</div>
								</aside>
							</div>
						</article>
					))}
				</div>
			</div>
		</div>
	)
}
