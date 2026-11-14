'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
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
			if (i === cur && seen && !calm) v.play().catch(() => {})
			else {
				v.pause()
				// once it has faded out it goes back to its first frame, so it starts from the top next time
				if (i !== cur) timers.push(window.setTimeout(() => curRef.current !== i && (v.currentTime = 0), 800))
			}
		})
		return () => timers.forEach((t) => window.clearTimeout(t))
	}, [cur, seen, calm, near])

	// one film at a time: the next one only starts to load once the one on screen is fully loaded, so the page and
	// the first film do not share the line with a second film nobody is watching yet
	if (near && !calm) reach.current = Math.max(reach.current, Math.min(N - 1, cur + (through[cur] ? 1 : 0)))
	const film = films[cur]
	return (
		<div className="mon">
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
							Open this story <ArrowUpRight size={16} strokeWidth={2.4} />
						</Link>
					</div>
					<span ref={bar} className="mon-progress" aria-hidden />
				</div>
			</div>
			<div className="mon-neck" aria-hidden />
			<div className="mon-foot" aria-hidden />
			{/* on a phone the screen is small: the story is named under the monitor, with a button a thumb can hit */}
			<div className="mon-note">
				<p className="mono">
					{String(cur + 1).padStart(2, '0')} / {String(N).padStart(2, '0')} · {film.tab}
				</p>
				<p className="display mon-note-title">{film.title}</p>
				<p>{film.place}</p>
				<Link href={film.path} className="mon-go">
					Open this story <ArrowUpRight size={16} strokeWidth={2.4} />
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
