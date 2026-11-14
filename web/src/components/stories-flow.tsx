'use client'

import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import './stories-flow.css'

export type StoryView = {
	key: string
	title: string
	what: string
	where: string
	kind: string
	coverage: string
	img: string | null
	passLabel: string
}

// Ribbons, after karma.business: the same few bands flow through every screen of the pinned section and change
// shape with the story. A sweep for the opening, long low waves for water, smoke rising for fire, one bowl for the
// sinking ground and concentric fringes, the way an interferogram draws a quake. Points share one parameter t along
// each band, so any shape morphs into the next as you scroll. The picture sits at (1080, 450) in this 1600 x 900 box.
const BANDS = 6
const POINTS = 96
const CX = 1120
const CY = 450
type Shape = (i: number, t: number, s: number) => [number, number]
// Every shape keeps clear of the copy column (x under 560) above y 690, so no band runs through text.
const SHAPES: Shape[] = [
	// opening: a low swell along the bottom, under the heading
	(i, t, s) => [-160 + 1920 * t, 790 - 70 * t + (i - 2.5) * 20 + Math.sin(t * 6 + i * 0.8 + s) * (10 + 26 * t)],
	// farm water: long low waves, the paddies' surface
	(i, t, s) => [-160 + 1920 * t, 772 + (i - 2.5) * 21 + Math.sin(t * 13 + i * 0.7 + s * 0.8) * (8 + i * 1.8)],
	// fire: the bands rise like smoke behind the picture
	(i, t, s) => [CX + (i - 2.5) * 40 + Math.sin(t * 7 + i * 0.9 + s) * (30 + 120 * t), 1020 - 1180 * t],
	// sinking ground: one bowl, rim high at the sides, sagging under the picture
	(i, t, s) => {
		const x = -160 + 1920 * t
		return [x, 120 + (i - 2.5) * 24 + 400 * Math.exp(-(((x - CX) / 300) ** 2)) + Math.sin(t * 6 + s + i) * 4]
	},
	// earthquake: concentric fringes around the picture, the way an interferogram draws it
	(i, t, s) => {
		const r = 172 + i * 54 + Math.sin(s + i) * 4
		const a = -Math.PI * 0.8 + t * Math.PI * 2.04
		return [CX + r * Math.cos(a) * 1.12, CY + r * Math.sin(a)]
	},
]
const smoother = (x: number) => x * x * x * (x * (x * 6 - 15) + 10)

export function StoriesFlow({ stories, head, line }: { stories: StoryView[]; head: { a: string; b: string; accent: string }; line: string }) {
	const section = useRef<HTMLElement>(null)
	const paths = useRef<(SVGPathElement | null)[]>([])
	const [stage, setStage] = useState(0)

	useEffect(() => {
		const el = section.current
		if (!el) return
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		let target = 0
		let pos = 0
		let raf = 0
		let running = false
		let shown = -1

		const measure = () => {
			const r = el.getBoundingClientRect()
			const span = r.height - window.innerHeight
			const p = Math.min(1, Math.max(0, -r.top / Math.max(1, span)))
			// the opening holds a moment, and the last story holds until the section lets go
			target = Math.min(stories.length, Math.max(0, p * (stories.length + 1.1) - 0.4))
		}
		const render = (time: number) => {
			pos += (target - pos) * (reduced ? 1 : 0.11)
			const k = Math.min(SHAPES.length - 2, Math.floor(pos))
			const f = smoother(Math.min(1, Math.max(0, pos - k)))
			const s = reduced ? 0 : time * 0.00055
			for (let i = 0; i < BANDS; i++) {
				const pth = paths.current[i]
				if (!pth) continue
				let d = ''
				for (let j = 0; j <= POINTS; j++) {
					const t = j / POINTS
					const [ax, ay] = SHAPES[k](i, t, s)
					const [bx, by] = SHAPES[k + 1](i, t, s)
					d += `${j ? 'L' : 'M'}${(ax + (bx - ax) * f).toFixed(1)} ${(ay + (by - ay) * f).toFixed(1)}`
				}
				pth.setAttribute('d', d)
			}
			const next = Math.round(pos)
			if (next !== shown) {
				shown = next
				setStage(next)
			}
		}
		const loop = (time: number) => {
			measure()
			render(time)
			raf = running ? requestAnimationFrame(loop) : 0
		}
		const io = new IntersectionObserver(([e]) => {
			running = e.isIntersecting
			if (running && !raf) raf = requestAnimationFrame(loop)
		})
		io.observe(el)
		measure()
		pos = target
		render(0)
		return () => {
			running = false
			cancelAnimationFrame(raf)
			io.disconnect()
		}
	}, [stories.length])

	return (
		<>
			<section id="stories" ref={section} className="sflow" style={{ ['--n' as string]: stories.length }}>
				<div className="sflow-stage">
					<svg className="sflow-ribbons" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden>
						{Array.from({ length: BANDS }, (_, i) => (
							<path key={i} ref={(n) => void (paths.current[i] = n)} className={`sflow-band b${i}`} />
						))}
					</svg>

					<div className="sflow-intro" data-on={stage === 0 || undefined}>
						<h2 className="sec-title">
							{head.a}
							<br />
							{head.b} <em>{head.accent}</em>
						</h2>
						<p className="sec-line">{line}</p>
						<p className="sflow-hint">Scroll through the four stories</p>
					</div>

					{stories.map((st, i) => (
						<article key={st.key} className="sflow-story" data-on={stage === i + 1 || undefined} aria-hidden={stage !== i + 1}>
							<div className="sflow-copy">
								<p className="sflow-count">
									<span>{String(i + 1).padStart(2, '0')}</span> / {String(stories.length).padStart(2, '0')} · {st.kind}
								</p>
								<h3>{st.title}</h3>
								<p className="sflow-what">{st.what}</p>
								<dl>
									<div>
										<dt>Where</dt>
										<dd>{st.where}</dd>
									</div>
									<div>
										<dt>NISAR</dt>
										<dd>{st.coverage}</dd>
									</div>
								</dl>
								<Link href={`/map?story=${st.key}`} className="sflow-link" tabIndex={stage === i + 1 ? 0 : -1}>
									Open in the map
									<span>
										<ArrowUpRight size={15} strokeWidth={2} />
									</span>
								</Link>
							</div>
							<figure className="sflow-visual">
								<div className="sflow-frame">
									{st.img && <img src={st.img} alt={`NISAR ${st.kind.toLowerCase()} over ${st.where}`} />}
									<figcaption>{st.passLabel}</figcaption>
								</div>
								<img className="sflow-icon" src={`/img/icons/${st.key}.webp`} alt="" width={240} height={240} />
							</figure>
						</article>
					))}

					<ol className="sflow-ticks" aria-hidden>
						{stories.map((st, i) => (
							<li key={st.key} data-on={stage === i + 1 || undefined}>
								<span />
								{st.title}
							</li>
						))}
					</ol>
				</div>
			</section>

			{/* phones and reduced motion: the same stories, stacked */}
			<section className="sflow-list" aria-label="Stories">
				<div className="sflow-list-head">
					<h2 className="sec-title">
						{head.a}
						<br />
						{head.b} <em>{head.accent}</em>
					</h2>
					<p className="sec-line">{line}</p>
				</div>
				{stories.map((st, i) => (
					<Link key={st.key} href={`/map?story=${st.key}`} className="sflow-card">
						<div className="sflow-card-radar">
							{st.img && <img src={st.img} alt="" loading="lazy" />}
							<img className="sflow-card-icon" src={`/img/icons/${st.key}.webp`} alt="" width={120} height={120} loading="lazy" />
						</div>
						<p className="sflow-count">
							<span>{String(i + 1).padStart(2, '0')}</span> · {st.kind}
						</p>
						<h3>{st.title}</h3>
						<p className="sflow-what">{st.what}</p>
						<p className="sflow-meta">
							{st.where} · {st.coverage}
						</p>
					</Link>
				))}
			</section>
		</>
	)
}
