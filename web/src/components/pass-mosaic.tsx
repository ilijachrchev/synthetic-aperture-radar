'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import './pass-mosaic.css'

export type Tile = { img: string; date: string; label: string; track: string }

const ASPECT = 273 / 433
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dd = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`

type Spot = { x: number; y: number; w: number }

/** Tiles in columns, each column nudged down by its own offset (in tile heights), centred in the area. */
function grid(n: number, counts: number[], offsets: number[], w: number, h: number, gap: number, fill: number): Spot[] {
	const cols = counts.length
	const tallest = Math.max(...counts.map((c, i) => c + offsets[i]))
	const tw = Math.min((w - (cols - 1) * gap) / cols, ((h * fill - (Math.max(...counts) - 1) * gap) / tallest) * ASPECT)
	const th = tw / ASPECT
	const gw = cols * tw + (cols - 1) * gap
	const gh = tallest * th + (Math.max(...counts) - 1) * gap
	const x0 = (w - gw) / 2
	const y0 = (h - gh) / 2
	const out: Spot[] = []
	counts.forEach((c, ci) => {
		for (let r = 0; r < c && out.length < n; r++) out.push({ x: x0 + ci * (tw + gap), y: y0 + offsets[ci] * th + r * (th + gap), w: tw })
	})
	return out
}

/**
 * 8x.social's "One brief" section in this project's world: the stage holds still while scroll plays three beats.
 * One pass of the coast, then every pass of one track (every 12 days), then all of them on three tracks. The first
 * line of the heading stays, the second swaps out of its mask, and the tiles fly to their places.
 */
export function PassMosaic({ tiles, line1, beats, para }: { tiles: Tile[]; line1: string; beats: string[]; para: string }) {
	const section = useRef<HTMLElement>(null)
	const area = useRef<HTMLDivElement>(null)
	const [beat, setBeat] = useState(2)
	const [size, setSize] = useState({ w: 760, h: 680 })

	useEffect(() => {
		const el = section.current
		const ar = area.current
		if (!el || !ar) return
		const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
		ro.observe(ar)
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return () => ro.disconnect()
		let raf = 0
		const update = () => {
			raf = 0
			const r = el.getBoundingClientRect()
			const p = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - window.innerHeight)))
			setBeat(p < 0.3 ? 0 : p < 0.64 ? 1 : 2)
		}
		const onScroll = () => {
			if (!raf) raf = requestAnimationFrame(update)
		}
		update()
		window.addEventListener('scroll', onScroll, { passive: true })
		return () => {
			ro.disconnect()
			window.removeEventListener('scroll', onScroll)
			cancelAnimationFrame(raf)
		}
	}, [])

	const lastIdx = tiles.length - 1 - [...tiles].reverse().findIndex((t) => t.track === '066')
	const oneTrack = tiles.map((t, i) => (t.track === '066' ? i : -1)).filter((i) => i >= 0)

	const layout = useMemo(() => {
		const { w, h } = size
		const big = h * 0.66 * ASPECT
		const b0: Spot = { x: (w - big) / 2, y: (h - h * 0.66) / 2, w: big }
		const b1 = grid(oneTrack.length, [3, 3, 3, 2], [0.12, 0, 0.2, 0.06], w, h, 12, 0.9)
		const b2 = grid(tiles.length, [4, 5, 4, 5, 4, 5, 4], [0.35, 0, 0.5, 0.15, 0.55, 0.05, 0.4], w, h, 9, 1.08)
		const pos1 = new Map(oneTrack.map((ti, k) => [ti, b1[k]]))
		return { base: big, b0, pos1, b2 }
	}, [size, tiles.length, oneTrack])

	const words = [...beats, `${tiles.length} passes.`]

	return (
		<section id="passes" ref={section} className="mos">
			<div className="mos-stage">
				<div className="mos-copy">
					<h2 className="display mos-title">
						<span className="mos-l1">{line1}</span>
						<span className="mos-swap">
							{words.map((wd, k) => (
								<span key={wd} className="accent" data-pos={k < beat ? 'past' : k > beat ? 'next' : 'now'} aria-hidden={k !== beat}>
									{wd}
								</span>
							))}
						</span>
					</h2>
					<p className="lead mos-para">{para}</p>
					<ol className="mos-steps" aria-hidden>
						{words.map((wd, k) => (
							<li key={wd} data-on={k === beat || undefined} />
						))}
					</ol>
				</div>

				<div ref={area} className="mos-area" data-beat={beat}>
					{tiles.map((t, i) => {
						const at = beat === 0 ? (i === lastIdx ? layout.b0 : layout.pos1.get(i) ?? layout.b2[i]) : beat === 1 ? (layout.pos1.get(i) ?? layout.b2[i]) : layout.b2[i]
						const shown = beat === 2 || (beat === 1 && layout.pos1.has(i)) || (beat === 0 && i === lastIdx)
						const s = at.w / layout.base
						return (
							<figure
								key={t.img}
								className="mos-tile"
								data-shown={shown || undefined}
								style={{
									width: layout.base,
									transform: `translate3d(${at.x}px, ${at.y}px, 0) scale(${shown ? s : s * 0.86})`,
									['--s' as string]: s,
									['--d' as string]: `${(i % 7) * 28}ms`,
								}}
							>
								<img src={t.img} alt={shown ? `NISAR radar, Valencia coast, ${dd(t.date)} 2026, track ${t.label}` : ''} loading={i === lastIdx ? 'eager' : 'lazy'} />
								<figcaption>
									<b>{dd(t.date)}</b> <span>{t.label}</span>
								</figcaption>
							</figure>
						)
					})}
				</div>
			</div>
		</section>
	)
}
