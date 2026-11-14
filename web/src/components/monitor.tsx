'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { MapApp, type StoryCfg } from './map/map-app'
import { type Chapter, StoryScroll } from './story-scroll'

/**
 * The dashboard on a monitor, and the stories playing on the same screen. The monitor is pinned while the page
 * scrolls through its track: first the live app (it plays the season by itself; a picture stands in until it is
 * ready), then the four stories fade in over it and play under the reader's scroll. Both are laid out at the screen's
 * own size and drawn scaled into it, like a real display. On a phone the monitor becomes a portrait screen at the
 * phone's own size, so the stories keep their phone layout and stay readable; there a picture of the app stands in.
 */
export function Monitor({ stories, chapters, track }: { stories: StoryCfg[]; chapters: Chapter[]; track: HTMLElement | null }) {
	const glass = useRef<HTMLDivElement>(null)
	const [phone, setPhone] = useState(false)
	const [size, setSize] = useState({ w: 1600, h: 900 })
	const [live, setLive] = useState(false)
	// the app's season rests while the stories cover it, and the app is not drawn at all once they cover it fully
	const appShows = useMemo(() => ({ current: true }), [])
	const appEl = useRef<HTMLDivElement>(null)
	const cover = (o: number) => {
		appShows.current = o < 0.999
		if (appEl.current) appEl.current.style.visibility = o >= 0.999 ? 'hidden' : 'visible'
	}

	useEffect(() => {
		const pick = () => {
			const p = window.innerWidth < 760
			setPhone(p)
			setSize(p ? { w: window.innerWidth, h: Math.round(window.innerHeight * 0.86) } : { w: 1600, h: 900 })
			// the live app wants its desktop layout, which its own styles give from 900px of window up
			setLive(window.innerWidth >= 900)
		}
		pick()
		window.addEventListener('resize', pick)
		return () => window.removeEventListener('resize', pick)
	}, [])

	useEffect(() => {
		const el = glass.current
		if (!el) return
		const fit = () => el.style.setProperty('--k', String(el.clientWidth / size.w))
		fit()
		const ro = new ResizeObserver(fit)
		ro.observe(el)
		return () => ro.disconnect()
	}, [size.w])

	const layer = { width: size.w, height: size.h }
	return (
		<div className="mon" data-device={phone ? 'phone' : 'monitor'} style={{ '--ar': `${size.w} / ${size.h}` } as React.CSSProperties}>
			<div className="mon-body">
				<div ref={glass} className="mon-glass">
					<img className="mon-shot mon-day" src={phone ? '/img/app/app-phone-light.webp' : '/img/app/app-light.webp'} alt="The map app: the Albufera radar over a satellite map, with the stories, the story card and the season timeline" />
					<img className="mon-shot mon-night" src={phone ? '/img/app/app-phone-dark.webp' : '/img/app/app-dark.webp'} alt="" />
					{live ? (
						<div ref={appEl} className="mon-layer mon-app" style={layer}>
							<MapApp stories={stories} embed visible={appShows} />
						</div>
					) : null}
					<div className="mon-layer" style={layer}>
						<StoryScroll chapters={chapters} trigger={track} lead={0.1} tail={0.05} onScreen={cover} />
					</div>
				</div>
			</div>
			<div className="mon-neck" aria-hidden />
			<div className="mon-foot" aria-hidden />
		</div>
	)
}

/** The monitor's track: the page scrolls through it while the monitor stays pinned in the middle of the screen. */
export function MonitorStage({ stories, chapters }: { stories: StoryCfg[]; chapters: Chapter[] }) {
	// held as state, so the stories hook onto the track once it is in the page
	const [track, setTrack] = useState<HTMLDivElement | null>(null)
	return (
		<div ref={setTrack} id="stories" className="hx-track" style={{ '--n': chapters.length } as React.CSSProperties}>
			<div className="hx-sticky">
				<div className="mon-in">
					<Monitor stories={stories} chapters={chapters} track={track} />
				</div>
			</div>
		</div>
	)
}
