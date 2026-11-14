'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'
import { storyNav } from '@/lib/story-nav'
import { ChangeLayer, type ChangeKind } from './change-layer'
import { lenisRef } from './smooth'
import './story-scroll.css'

gsap.registerPlugin(ScrollTrigger, useGSAP)

export type Chapter = {
	key: string
	kind: string
	title: string
	what: string
	where: string
	legend: string
	change: ChangeKind
	track: string
	/** every imaged pass of the track, in order */
	frames: string[]
	/** the big date of each pass, and the pair it closes when it is a pair */
	dates: { day: string; pair: string | null }[]
	/** where each pass and each month sits on the time axis, 0 to 1 */
	at: number[]
	months: { label: string; at: number }[]
	refCount: number
	revealAt: number
	epi: [number, number]
	/** the satellite ground around the radar box, and the box on it as fractions */
	ground: { src: string; w: number; h: number; box: [number, number, number, number] }
}

const T = 0.2 // the share of a chapter spent flying in from the one before
const CAM = 1.1 // how far the camera has pushed in by the end of a chapter

const clamp = (v: number) => Math.min(1, Math.max(0, v))
const step = (a: number, b: number, x: number) => {
	const t = clamp((x - a) / (b - a))
	return t * t * (3 - 2 * t)
}
const inOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)

type Fit = { left: number; top: number; w: number; h: number; ox: number; oy: number }

/** Size and place a chapter's ground so its radar box sits where the copy leaves room, and the ground covers the stage. */
function fit(sw: number, sh: number, g: Chapter['ground'], phone: boolean): Fit {
	const [x0, y0, x1, y1] = g.box
	const bw = (x1 - x0) * g.w
	const bh = (y1 - y0) * g.h
	let k = phone ? Math.min((sw * 0.84) / bw, (sh * 0.4) / bh) : Math.min((sw * 0.4) / bw, (sh * 0.64) / bh)
	k = Math.max(k, sw / g.w, sh / g.h)
	const w = g.w * k
	const h = g.h * k
	const ox = ((x0 + x1) / 2) * w
	const oy = ((y0 + y1) / 2) * h
	const fx = phone ? 0.5 : 0.63
	const fy = phone ? 0.3 : 0.47
	const left = Math.min(0, Math.max(sw - w, fx * sw - ox))
	const top = Math.min(0, Math.max(sh - h, fy * sh - oy))
	return { left, top, w, h, ox, oy }
}

/**
 * The four stories, played on the monitor's screen. The page scrolls through a tall track (trigger) while the monitor
 * stays pinned: for the first part (lead) the screen still shows the dashboard and this fades in over it, then
 * scrolling flies from place to place over the real ground (Sentinel-2 cloudless) and, inside each place, scrubs
 * through the NISAR passes, so the change plays out under the reader's own hand: water spreads and drains, the scar
 * burns in, the ground's motion flows, the quake's fringes open from the epicentre. Everything moves by transform and
 * opacity, written straight from the scroll position; the copy and the timeline follow, and the pill navbar lights the
 * story on screen. Reduced motion steps from chapter to chapter and shows each finished season.
 */
export function StoryScroll({
	chapters,
	trigger,
	lead = 0.08,
	tail = 0.05,
	onScreen,
}: {
	chapters: Chapter[]
	/** the tall track whose scroll drives the screen (given once it is in the page) */
	trigger: HTMLElement | null
	/** share of the track before the first story (the dashboard shows), and after the last */
	lead?: number
	tail?: number
	/** how much of the screen the stories cover, 0 to 1, as they fade in over the dashboard */
	onScreen?: (o: number) => void
}) {
	const win = useRef<HTMLDivElement>(null)
	const scenes = useRef<(HTMLDivElement | null)[]>([])
	const geos = useRef<(HTMLDivElement | null)[]>([])
	const copies = useRef<(HTMLElement | null)[]>([])
	const dateEls = useRef<(HTMLElement | null)[]>([])
	const pairEls = useRef<(HTMLElement | null)[]>([])
	const bar = useRef<HTMLSpanElement>(null)
	const fill = useRef<HTMLSpanElement>(null)
	const tickBox = useRef<HTMLDivElement>(null)
	const fits = useRef<Fit[]>([])
	const shown = useRef<number[]>(chapters.map(() => -1))
	const scrubs = useMemo(() => chapters.map(() => ({ current: 0 })), [chapters])
	// which chapters are on screen at all, read by their change layers every frame
	const shows = useMemo(() => chapters.map((_, i) => ({ current: i === 0 })), [chapters])
	const progress = useRef(0)
	const [cur, setCur] = useState(0)
	const [near, setNear] = useState(false)
	const curRef = useRef(0)
	const N = chapters.length

	// start reading the passes once the stage is about a screen and a half away
	useEffect(() => {
		const el = win.current
		if (!el) return
		const io = new IntersectionObserver(
			([e]) => {
				if (!e.isIntersecting) return
				setNear(true)
				// decode every ground before it flies in, so no chapter waits on a picture
				el.querySelectorAll<HTMLImageElement>('.st-ground').forEach((im) => im.decode().catch(() => {}))
			},
			{ rootMargin: '150% 0px' },
		)
		io.observe(el)
		return () => io.disconnect()
	}, [])

	const render = useRef<(p: number) => void>(() => {})
	render.current = (p: number) => {
		progress.current = p
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		const x = p * N
		const c = Math.min(N - 1, Math.floor(x))
		const q = x - c
		for (let i = 0; i < N; i++) {
			const scene = scenes.current[i]
			const geo = geos.current[i]
			const copy = copies.current[i]
			const n = chapters[i].frames.length
			let o = 0
			let s = 1
			let t = i < c ? n - 1 : 0
			let co = 0
			let cy = 0
			if (i === c) {
				const enter = i === 0 || reduced ? 1 : step(0, T, q)
				const u = reduced ? 1 : clamp((q - (i === 0 ? 0.03 : T)) / (0.9 - (i === 0 ? 0.03 : T)))
				o = enter
				s = reduced ? 1 : (0.8 + 0.2 * (1 - (1 - enter) ** 3)) * (1 + (CAM - 1) * inOut(u))
				t = u * (n - 1)
				const a = i === 0 || reduced ? 1 : step(T * 0.35, T + 0.06, q)
				co = a
				cy = (1 - a) * 44
			} else if (i === c - 1 && !reduced) {
				const k = step(0, T, q)
				o = 1 - k
				s = CAM * (1 + 0.38 * k * k)
				t = n - 1
				const b = step(0, T * 0.55, q)
				co = 1 - b
				cy = -b * 44
			}
			if (scene) {
				scene.style.opacity = String(o)
				scene.style.visibility = o > 0.002 ? 'visible' : 'hidden'
			}
			shows[i].current = o > 0.002
			if (geo) geo.style.transform = `scale(${s})`
			if (copy) {
				copy.style.opacity = String(co)
				copy.style.transform = `translate3d(0, ${cy}px, 0)`
				copy.style.visibility = co > 0.01 ? 'visible' : 'hidden'
			}
			scrubs[i].current = t
			// the big date follows the nearest pass
			const near = Math.round(t)
			if (near !== shown.current[i]) {
				shown.current[i] = near
				const d = chapters[i].dates[near]
				if (dateEls.current[i]) dateEls.current[i]!.textContent = d.day
				if (pairEls.current[i]) pairEls.current[i]!.textContent = d.pair ?? `pass ${near + 1} of ${n}`
				if (i === curRef.current && tickBox.current) tickBox.current.querySelectorAll('i').forEach((el, k) => el.toggleAttribute('data-on', k === near))
			}
		}
		// the chapter on show: the one flying in takes over halfway through its arrival
		const d = c > 0 && q < T * 0.5 && !reduced ? c - 1 : c
		if (fill.current) {
			// the fill ends at the date being shown, between the two passes it is easing through
			const ch = chapters[d]
			const tt = scrubs[d].current
			const i0 = Math.floor(tt)
			const i1 = Math.min(ch.at.length - 1, i0 + 1)
			fill.current.style.transform = `scaleX(${ch.at[i0] + (ch.at[i1] - ch.at[i0]) * (tt - i0)})`
		}
		if (bar.current) bar.current.style.transform = `scaleX(${p})`
		if (d !== curRef.current) {
			curRef.current = d
			setCur(d)
		}
	}

	// the track's scroll, split into the dashboard's lead, the stories, and a short hold at the end
	const drive = useRef<(raw: number) => void>(() => {})
	drive.current = (raw: number) => {
		const span = 1 - lead - tail
		const p = clamp((raw - lead) / span)
		// the stories fade in over the dashboard during the last two thirds of the lead
		const o = lead > 0 ? clamp((raw - lead * 0.35) / (lead * 0.65)) : 1
		if (win.current) {
			win.current.style.opacity = String(o)
			win.current.style.visibility = o > 0.002 ? 'visible' : 'hidden'
		}
		onScreen?.(o)
		render.current(p)
		storyNav.set(o < 0.5 ? -1 : curRef.current)
	}

	// lay each ground out for the stage's size
	useEffect(() => {
		const el = win.current
		if (!el) return
		const lay = () => {
			const sw = el.clientWidth
			const sh = el.clientHeight
			const phone = sw < 760
			fits.current = chapters.map((ch) => fit(sw, sh, ch.ground, phone))
			fits.current.forEach((f, i) => {
				const g = geos.current[i]
				if (!g) return
				g.style.left = `${f.left}px`
				g.style.top = `${f.top}px`
				g.style.width = `${f.w}px`
				g.style.height = `${f.h}px`
				g.style.transformOrigin = `${f.ox}px ${f.oy}px`
			})
		}
		lay()
		const ro = new ResizeObserver(lay)
		ro.observe(el)
		return () => ro.disconnect()
	}, [chapters])

	// after a chapter change the ticks are new elements: light the current pass
	useEffect(() => {
		shown.current[cur] = -1
		render.current(progress.current)
	}, [cur])

	useGSAP(
		() => {
			if (!trigger) return
			const st = ScrollTrigger.create({ trigger, start: 'top top', end: 'bottom bottom', onUpdate: (self) => drive.current(self.progress), onRefresh: (self) => drive.current(self.progress) })
			drive.current(st.progress)
			return () => st.kill()
		},
		{ dependencies: [trigger] },
	)

	// the navbar takes the reader to a story (or back to the top) through here
	useEffect(() => {
		storyNav.register((i) => {
			const scroll = (y: number) => {
				if (lenisRef.current) lenisRef.current.scrollTo(y, { duration: 1.6 })
				else window.scrollTo({ top: y, behavior: 'smooth' })
			}
			if (i < 0) return scroll(0)
			const el = trigger
			if (!el) return
			const top = el.getBoundingClientRect().top + window.scrollY
			const span = el.offsetHeight - window.innerHeight
			const into = (i + (i === 0 ? 0.04 : T + 0.04)) / N
			scroll(top + (lead + into * (1 - lead - tail)) * span)
		})
	}, [trigger, lead, tail, N])

	const ch = chapters[cur]
	return (
		<div ref={win} className="st-window" style={{ opacity: 0, visibility: 'hidden' }}>
			{chapters.map((c, i) => (
				<div key={c.key} ref={(n) => void (scenes.current[i] = n)} className="st-scene" style={i === 0 ? undefined : { opacity: 0, visibility: 'hidden' }}>
					<div ref={(n) => void (geos.current[i] = n)} className="st-geo">
						<img className="st-ground" src={c.ground.src} alt="" width={c.ground.w} height={c.ground.h} decoding="async" />
						<div
							className="st-box"
							style={{
								left: `${c.ground.box[0] * 100}%`,
								top: `${c.ground.box[1] * 100}%`,
								width: `${(c.ground.box[2] - c.ground.box[0]) * 100}%`,
								height: `${(c.ground.box[3] - c.ground.box[1]) * 100}%`,
							}}
						>
							{near ? (
								<ChangeLayer className="st-change" kind={c.change} frames={c.frames} scrub={scrubs[i]} active={Math.abs(i - cur) <= 1} visible={shows[i]} base={0.94} refCount={c.refCount} revealAt={c.revealAt} epicentre={c.epi} />
							) : null}
							<span className="st-tag mono">NISAR · track {c.track}</span>
						</div>
					</div>
				</div>
			))}
			<div className="st-shade" aria-hidden />

			{chapters.map((c, i) => (
				<article key={c.key} ref={(n) => void (copies.current[i] = n)} className="st-copy" style={i === 0 ? undefined : { opacity: 0, visibility: 'hidden' }} aria-label={c.title}>
					<p className="mono st-num">
						<span>{String(i + 1).padStart(2, '0')}</span> / {String(N).padStart(2, '0')} · {c.kind}
					</p>
					<h3 className="display st-title">{c.title}</h3>
					<p className="st-what">{c.what}</p>
					<div className="st-when">
						<b className="display" ref={(n) => void (dateEls.current[i] = n)}>
							{c.dates[0].day}
						</b>
						<small className="mono" ref={(n) => void (pairEls.current[i] = n)}>
							{c.dates[0].pair ?? `pass 1 of ${c.frames.length}`}
						</small>
					</div>
					<p className="st-legend">
						<i data-k={c.change} aria-hidden /> {c.legend}
					</p>
					<Link href={`/map?story=${c.key}`} className="st-go">
						Open in the map <ArrowUpRight size={16} strokeWidth={2.4} />
					</Link>
				</article>
			))}

			<div className="st-rail" aria-hidden>
				<div className="st-time">
					<div ref={tickBox} className="st-ticks" key={ch.key}>
						{ch.at.map((a, k) => (
							<i key={k} style={{ left: `${a * 100}%` }} />
						))}
						<span className="st-fill" ref={fill} />
					</div>
					<div className="st-months">
						{ch.months.map((m) => (
							<em key={m.label + m.at} style={{ left: `${m.at * 100}%` }}>
								{m.label}
							</em>
						))}
					</div>
				</div>
			</div>
			<span ref={bar} className="st-progress" aria-hidden />
			<p className="st-credit">Ground: Sentinel-2 cloudless 2020 by EOX · Radar: NASA-ISRO NISAR via ASF DAAC</p>
		</div>
	)
}
