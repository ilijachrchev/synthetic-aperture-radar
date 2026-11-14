'use client'

import { useEffect, useRef, useState } from 'react'
import './machine.css'

type Step = { n: string; title: string; fig: string; line: string }

// which slat's back carries which step; the others carry a real radar pass. Phones get four slats, one per step,
// since eight are too narrow to hold a step's words.
const LAYOUTS = {
	wide: { slats: 8, stepAt: { 1: 0, 3: 1, 4: 2, 6: 3 } as Record<number, number> },
	narrow: { slats: 4, stepAt: { 0: 0, 1: 1, 2: 2, 3: 3 } as Record<number, number> },
}

/**
 * 8x.social's machine: a band of slats that read as one giant line, and turn as you scroll to show what is behind
 * it. Here the line is the README's promise and the backs are the four steps of the pipeline, between real passes.
 * Rotation is set straight on each slat's style from one scroll listener, so React does not render per frame.
 */
export function Machine({ lines, sr, steps, radar, after }: { lines: string[]; sr: string; steps: Step[]; radar: string[]; after: string }) {
	const section = useRef<HTMLElement>(null)
	const slats = useRef<(HTMLDivElement | null)[]>([])
	const [narrow, setNarrow] = useState(false)
	const { slats: SLATS, stepAt: STEP_AT } = narrow ? LAYOUTS.narrow : LAYOUTS.wide

	useEffect(() => {
		const mq = window.matchMedia('(max-width: 640px)')
		const on = () => setNarrow(mq.matches)
		on()
		mq.addEventListener('change', on)
		return () => mq.removeEventListener('change', on)
	}, [])

	useEffect(() => {
		const el = section.current
		if (!el) return
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		let raf = 0
		const update = () => {
			raf = 0
			const r = el.getBoundingClientRect()
			const p = reduced ? 1 : Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - window.innerHeight)))
			slats.current.forEach((s, i) => {
				if (!s) return
				const t = Math.min(1, Math.max(0, (p * 1.25 - i * 0.055) / 0.5))
				const e = t * t * (3 - 2 * t)
				s.style.setProperty('--r', `${e * 180}deg`)
				s.style.setProperty('--shade', `${Math.sin(e * Math.PI) * 0.42}`)
			})
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
	}, [narrow])

	let r = 0
	return (
		<section id="how" ref={section} className="mach">
			<div className="mach-stage">
				<p className="eyebrow mach-eyebrow">How it works</p>
				<h2 className="sr-only">{sr}</h2>
				<div className="mach-band" style={{ ['--n' as string]: SLATS }}>
					<span className="mach-rail mach-rail-top" aria-hidden />
					{Array.from({ length: SLATS }, (_, i) => {
						const step = STEP_AT[i] !== undefined ? steps[STEP_AT[i]] : null
						const img = step ? null : radar[r++ % radar.length]
						return (
							<div key={i} ref={(n) => void (slats.current[i] = n)} className="mach-slat" style={{ ['--i' as string]: i }}>
								<div className="mach-face mach-front" aria-hidden>
									<div className="mach-words display">
										{lines.map((l) => (
											<span key={l}>{l}</span>
										))}
									</div>
								</div>
								<div className="mach-face mach-back">
									{step ? (
										<div className="mach-step">
											<span className="mono">{step.n}</span>
											<b className="display">{step.title}</b>
											<strong className="display">{step.fig}</strong>
											<p>{step.line}</p>
										</div>
									) : (
										<img src={img!} alt="" loading="lazy" />
									)}
								</div>
							</div>
						)
					})}
					<span className="mach-rail mach-rail-bottom" aria-hidden />
				</div>
				<p className="mach-after">{after}</p>
			</div>
		</section>
	)
}
