'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { ArrowUpRight, Pause, Play } from 'lucide-react'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { DECK } from '@/content/landing'
import { STORIES } from '@/content/stories'
import { storyNav } from '@/lib/story-nav'
import { warmMaplibre, warmStory, whenIdle } from '@/lib/warm'
import { lenisRef } from './smooth'

gsap.registerPlugin(ScrollTrigger, useGSAP)

/** One story as the monitor plays it: a film of its real 3D page (scripts/landing_films.py), and the page it opens. */
export type Film = {
	key: string
	tab: string
	title: string
	place: string
	/** the 3D page of the story */
	path: string
	src: string
	/** the first frame, shown until the film starts */
	poster: string
	/** a frame from late in the film, for people who ask for less motion */
	still: string
	/** the words of the button that opens the page (by default "Open this story") */
	cta?: string
	/** what the film shows and from which second (the deck under the monitor marks them on its timeline) */
	chapters?: Chapter[]
	/** the film's length in seconds, shown until the film itself has loaded */
	duration?: number
}

/** one chapter of a film: the second it starts, and what the film shows then */
export type Chapter = { at: number; label: string; value: string }

/** m:ss */
const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`
/** the chapter on screen at second t */
const chapterAt = (chapters: Chapter[], t: number) => {
	let k = 0
	chapters.forEach((c, i) => {
		if (t >= c.at) k = i
	})
	return k
}

/** the share of the track before the first story takes the navbar, and the hold after the last */
const LEAD = 0.08
const TAIL = 0.05
const clamp = (v: number) => Math.min(1, Math.max(0, v))

/**
 * The app on a monitor: the screen plays the real 3D story pages. The monitor is pinned while the page scrolls
 * through its track, and the scroll picks the story: the flood first, then the others. Each film is the page itself
 * telling its story (the Earth, one move down onto the place, the radar passes), recorded from the running app, so
 * nothing on the screen is a stand-in. A film only loads when its story is near and only plays while the monitor is
 * on screen. People who ask for less motion get a still frame of each story. The button opens the story's page.
 *
 * Under it, a slim deck: play and pause, a timeline as wide as the monitor with a playhead to drag (mouse, touch, a
 * click jumps, arrow keys move it), the chapters of the film marked on it, and the time. Dragging pauses the film and
 * lets it play on when released, if it was playing. With less motion asked for, nothing plays until Play is pressed.
 */
export function Monitor({ films, track }: { films: Film[]; track: HTMLElement | null }) {
	const glass = useRef<HTMLDivElement>(null)
	const videos = useRef<(HTMLVideoElement | null)[]>([])
	const bar = useRef<HTMLSpanElement>(null)
	const curRef = useRef(0)
	// the furthest film that has been given its file: the one on screen, and the next once that one is fully loaded
	const reach = useRef(-1)
	const [through, setThrough] = useState<boolean[]>(() => films.map(() => false))
	const [cur, setCur] = useState(0)
	const [seen, setSeen] = useState(false)
	const [near, setNear] = useState(false)
	const [calm, setCalm] = useState(false)
	// the deck: whether the reader pressed play or pause (null: not yet, so the film plays unless less motion is
	// asked for), whether the deck asked for the film to load, the chapter on screen and the film's length
	const [choice, setChoice] = useState<boolean | null>(null)
	const [load, setLoad] = useState(false)
	const [chap, setChap] = useState(0)
	const [dur, setDur] = useState(films[0]?.duration ?? 0)
	const want = choice ?? !calm
	const line = useRef<HTMLDivElement>(null)
	const elapsed = useRef<HTMLSpanElement>(null)
	const chapRef = useRef(0)
	const secRef = useRef(-1)
	// a drag in progress (and whether the film played before it), and the seeking: the time the deck shows, the one
	// waiting for the seek on its way to finish, whether a seek is on its way
	const drag = useRef<{ resume: boolean } | null>(null)
	const seek = useRef<{ shown: number; next: number | null; busy: boolean }>({ shown: 0, next: null, busy: false })
	const N = films.length

	useEffect(() => {
		setCalm(window.matchMedia('(prefers-reduced-motion: reduce)').matches)
		const el = glass.current
		if (!el) return
		const on = new IntersectionObserver(([e]) => setSeen(e.isIntersecting && e.intersectionRatio > 0.3), { threshold: [0, 0.3, 0.6] })
		// start fetching the first film when the monitor is about a screen away
		const close = new IntersectionObserver(([e]) => e.isIntersecting && setNear(true), { rootMargin: '100% 0px' })
		on.observe(el)
		close.observe(el)
		return () => {
			on.disconnect()
			close.disconnect()
		}
	}, [])

	// "Open the map" opens the flood: once the landing is up, its map code and its first view come in quietly, so
	// the click shows the map at once
	useEffect(
		() =>
			whenIdle(() => {
				warmMaplibre()
				warmStory(STORIES[0])
			}),
		[],
	)

	// the track's scroll picks the story
	useGSAP(
		() => {
			if (!track) return
			const drive = (raw: number) => {
				const p = clamp((raw - LEAD) / (1 - LEAD - TAIL))
				const c = Math.min(N - 1, Math.floor(p * N))
				if (bar.current) bar.current.style.transform = `scaleX(${p})`
				if (c !== curRef.current) {
					curRef.current = c
					setCur(c)
				}
				storyNav.set(raw < LEAD * 0.6 ? -1 : c)
			}
			const st = ScrollTrigger.create({ trigger: track, start: 'top top', end: 'bottom bottom', onUpdate: (self) => drive(self.progress), onRefresh: (self) => drive(self.progress) })
			drive(st.progress)
			return () => st.kill()
		},
		{ dependencies: [track, N] },
	)

	// the navbar takes the reader to a story (or back to the top) through here
	useEffect(() => {
		storyNav.register((i) => {
			const scroll = (y: number) => {
				if (lenisRef.current) lenisRef.current.scrollTo(y, { duration: 1.6 })
				else window.scrollTo({ top: y, behavior: 'smooth' })
			}
			if (i < 0) return scroll(0)
			if (!track) return
			const top = track.getBoundingClientRect().top + window.scrollY
			const span = track.offsetHeight - window.innerHeight
			scroll(top + (LEAD + ((i + 0.1) / N) * (1 - LEAD - TAIL)) * span)
		})
	}, [track, N])

	// the story on screen plays while the monitor is in view; the others rest at their start
	useEffect(() => {
		const timers: number[] = []
		videos.current.forEach((v, i) => {
			if (!v) return
			if (i === cur && seen && want && !drag.current) v.play().catch(() => {})
			else {
				v.pause()
				// once it has faded out it goes back to its first frame, so it starts from the top next time
				if (i !== cur) timers.push(window.setTimeout(() => curRef.current !== i && (v.currentTime = 0), 800))
			}
		})
		return () => timers.forEach((t) => window.clearTimeout(t))
	}, [cur, seen, calm, near, want])

	// the deck follows the film on screen, every frame while the monitor is in view: the playhead, the time, the
	// chapter. While a drag or a seek is on its way it shows where the reader put it, not the frame still coming.
	useEffect(() => {
		if (!seen) return
		let raf = 0
		// the timeline's width, for the playhead's transform in px
		let w = line.current?.clientWidth ?? 0
		const ro = new ResizeObserver(([e]) => void (w = e.contentRect.width))
		if (line.current) ro.observe(line.current)
		const paint = () => {
			raf = requestAnimationFrame(paint)
			const v = videos.current[curRef.current]
			const f = films[curRef.current]
			const d = v && Number.isFinite(v.duration) && v.duration > 0 ? v.duration : (f?.duration ?? 0)
			if (!d || !line.current) return
			const s = seek.current
			const t = drag.current || s.busy || s.next !== null || !v ? s.shown : v.currentTime
			const p = Math.min(1, Math.max(0, t / d))
			line.current.style.setProperty('--p', String(p))
			line.current.style.setProperty('--x', `${(p * w).toFixed(1)}px`)
			const sec = Math.floor(t)
			if (sec !== secRef.current) {
				secRef.current = sec
				if (elapsed.current) elapsed.current.textContent = clock(t)
				line.current.setAttribute('aria-valuenow', String(sec))
				line.current.setAttribute('aria-valuetext', `${clock(t)} of ${clock(d)}`)
			}
			const k = f?.chapters ? chapterAt(f.chapters, t) : 0
			if (k !== chapRef.current) {
				chapRef.current = k
				setChap(k)
			}
		}
		raf = requestAnimationFrame(paint)
		return () => {
			cancelAnimationFrame(raf)
			ro.disconnect()
		}
	}, [seen, films])

	// one film at a time: the next one only starts to load once the one on screen is fully loaded, so the page and
	// the first film do not share the line with a second film nobody is watching yet
	if (near && (want || load)) reach.current = Math.max(reach.current, Math.min(N - 1, cur + (through[cur] ? 1 : 0)))
	const film = films[cur]

	// the deck: send the film to second t, one seek at a time (the newest waits for the one on its way), so a drag
	// stays smooth instead of queueing seeks the decoder cannot keep up with
	const toSecond = (t: number) => {
		const v = videos.current[curRef.current]
		const d = v && Number.isFinite(v.duration) && v.duration > 0 ? v.duration : dur
		const s = seek.current
		s.shown = Math.min(Math.max(0, t), Math.max(0, d - 0.05))
		setLoad(true)
		if (!v || v.readyState < 1) {
			// not loaded yet: it goes there once it is (onLoadedMetadata)
			s.next = s.shown
			return
		}
		if (s.busy) {
			s.next = s.shown
			return
		}
		s.busy = true
		s.next = null
		v.currentTime = s.shown
	}
	const seeked = (v: HTMLVideoElement) => {
		const s = seek.current
		s.busy = false
		if (s.next !== null && Math.abs(s.next - v.currentTime) > 0.02) {
			const t = s.next
			s.next = null
			s.busy = true
			v.currentTime = t
		} else s.next = null
	}
	const secondAt = (x: number) => {
		const r = line.current?.getBoundingClientRect()
		return r && r.width ? Math.min(1, Math.max(0, (x - r.left) / r.width)) * dur : 0
	}
	const grab = (e: React.PointerEvent<HTMLDivElement>) => {
		if (e.pointerType === 'mouse' && e.button !== 0) return
		const v = videos.current[curRef.current]
		e.currentTarget.setPointerCapture(e.pointerId)
		drag.current = { resume: v ? !v.paused : want }
		v?.pause()
		toSecond(secondAt(e.clientX))
	}
	const move = (e: React.PointerEvent<HTMLDivElement>) => {
		if (drag.current) toSecond(secondAt(e.clientX))
	}
	const release = () => {
		const d = drag.current
		if (!d) return
		drag.current = null
		if (d.resume && seen) videos.current[curRef.current]?.play().catch(() => {})
	}
	const key = (e: React.KeyboardEvent<HTMLDivElement>) => {
		const list = film.chapters ?? []
		const s = seek.current
		const now = s.busy || s.next !== null ? s.shown : (videos.current[curRef.current]?.currentTime ?? s.shown)
		const step = e.shiftKey ? 5 : 1
		let t: number | null = null
		if (e.key === 'ArrowRight' || e.key === 'ArrowUp') t = now + step
		else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') t = now - step
		else if (e.key === 'Home') t = 0
		else if (e.key === 'End') t = dur
		else if (e.key === 'PageUp') t = list[Math.min(list.length - 1, chapterAt(list, now) + 1)]?.at ?? null
		else if (e.key === 'PageDown') t = list[Math.max(0, chapterAt(list, now) - 1)]?.at ?? null
		if (t === null) return
		e.preventDefault()
		toSecond(t)
	}
	const toggle = () => {
		const v = videos.current[curRef.current]
		if (want) {
			setChoice(false)
			v?.pause()
		} else {
			setChoice(true)
			setLoad(true)
		}
	}
	const chapters = film.chapters ?? []
	const on = chapters[Math.min(chap, chapters.length - 1)]
	return (
		<div className="mon" data-deck={chapters.length > 0 || undefined}>
			<div className="mon-body">
				<div ref={glass} className="mon-glass">
					{films.map((f, i) => (
						<video
							key={f.key}
							ref={(n) => void (videos.current[i] = n)}
							className="mon-film"
							data-on={i === cur || undefined}
							src={i <= reach.current ? f.src : undefined}
							poster={calm ? f.still : f.poster}
							muted
							loop
							playsInline
							preload="auto"
							onLoadedMetadata={(e) => {
								const v = e.currentTarget
								if (i !== curRef.current) return
								if (Number.isFinite(v.duration) && v.duration > 0) setDur(v.duration)
								// a time the deck asked for before the film had loaded
								const s = seek.current
								if (s.next !== null) {
									const t = s.next
									s.next = null
									s.busy = true
									v.currentTime = t
								}
							}}
							onSeeked={(e) => i === curRef.current && seeked(e.currentTarget)}
							onProgress={(e) => {
								// the whole film is in: the next one may start to load
								const v = e.currentTarget
								const end = v.buffered.length ? v.buffered.end(v.buffered.length - 1) : 0
								if (v.duration && end >= v.duration - 0.5) setThrough((t) => (t[i] ? t : t.map((x, k) => x || k === i)))
							}}
							aria-label={`${f.title}, ${f.place}: the story playing on its 3D map page`}
						/>
					))}
					<div className="mon-over">
						<span className="mono mon-count">
							{String(cur + 1).padStart(2, '0')} / {String(N).padStart(2, '0')}
						</span>
						<Link href={film.path} className="mon-go">
							{film.cta ?? 'Open this story'} <ArrowUpRight size={16} strokeWidth={2.4} />
						</Link>
					</div>
					<span ref={bar} className="mon-progress" aria-hidden />
				</div>
			</div>
			<div className="mon-neck" aria-hidden />
			<div className="mon-foot" aria-hidden />
			{chapters.length > 0 && dur > 0 && (
				<div className="deck" role="group" aria-label={`${film.title}: the film's controls`}>
					<div className="deck-line">
						<div
							ref={line}
							className="deck-track"
							role="slider"
							tabIndex={0}
							aria-label={DECK.timeline}
							aria-valuemin={0}
							aria-valuemax={Math.floor(dur)}
							aria-valuenow={0}
							aria-valuetext={`0:00 of ${clock(dur)}`}
							onPointerDown={grab}
							onPointerMove={move}
							onPointerUp={release}
							onPointerCancel={release}
							onLostPointerCapture={release}
							onKeyDown={key}
						>
							<span className="deck-rail" aria-hidden>
								<span className="deck-fill" />
							</span>
							<span className="deck-head" aria-hidden />
						</div>
						{chapters.map((c, i) => (
							<button
								key={c.at}
								type="button"
								className="deck-mark"
								style={{ left: `${(c.at / dur) * 100}%` }}
								data-on={i === chap || undefined}
								aria-label={`${DECK.jump} ${c.label}, ${c.value}`}
								onClick={() => toSecond(c.at + 0.05)}
							>
								<span className="mono">{c.value}</span>
							</button>
						))}
					</div>
					<div className="deck-row">
						<button type="button" className="deck-play" aria-label={want ? DECK.pause : DECK.play} onClick={toggle}>
							{want ? <Pause size={15} strokeWidth={2.6} fill="currentColor" /> : <Play size={15} strokeWidth={2.6} fill="currentColor" />}
						</button>
						<span className="mono deck-time">
							<span ref={elapsed}>0:00</span> / {clock(dur)}
						</span>
						{on && (
							<span className="deck-chap">
								<i aria-hidden />
								<span className="mono">{on.value}</span>
								<b>{on.label}</b>
							</span>
						)}
					</div>
				</div>
			)}
			{/* on a phone the screen is small: the story is named under the monitor, with a button a thumb can hit */}
			<div className="mon-note">
				<p className="mono">
					{String(cur + 1).padStart(2, '0')} / {String(N).padStart(2, '0')} · {film.tab}
				</p>
				<p className="display mon-note-title">{film.title}</p>
				<p>{film.place}</p>
				<Link href={film.path} className="mon-go">
					{film.cta ?? 'Open this story'} <ArrowUpRight size={16} strokeWidth={2.4} />
				</Link>
			</div>
		</div>
	)
}

/** The monitor's track: the page scrolls through it while the monitor stays pinned in the middle of the screen. */
export function MonitorStage({ films }: { films: Film[] }) {
	// held as state, so the stories hook onto the track once it is in the page
	const [track, setTrack] = useState<HTMLDivElement | null>(null)
	return (
		<div ref={setTrack} id="stories" className="hx-track" style={{ '--n': films.length } as React.CSSProperties}>
			<div className="hx-sticky">
				<div className="mon-in">
					<Monitor films={films} track={track} />
				</div>
			</div>
		</div>
	)
}
