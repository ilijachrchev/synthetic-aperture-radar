'use client'

import { useEffect, useRef, useState } from 'react'
import { MapApp, type StoryCfg } from './map/map-app'

// the app is laid out at a desktop size and drawn scaled into the screen, like a real monitor showing it
const W = 1440
const H = 900

/**
 * The dashboard on a monitor. On a desktop the real app runs on the screen (it plays the season by itself and its
 * buttons work; the page scrolls past it); a picture of it stands in until it is ready, and on phones, where the
 * app's own layout would be its phone one.
 */
export function Monitor({ stories }: { stories: StoryCfg[] }) {
	const glass = useRef<HTMLDivElement>(null)
	const [live, setLive] = useState(false)

	useEffect(() => {
		const el = glass.current
		if (!el) return
		const fit = () => el.style.setProperty('--k', String(el.clientWidth / W))
		fit()
		const ro = new ResizeObserver(fit)
		ro.observe(el)
		const wide = window.matchMedia('(min-width: 900px)')
		const pick = () => setLive(wide.matches)
		pick()
		wide.addEventListener('change', pick)
		return () => {
			ro.disconnect()
			wide.removeEventListener('change', pick)
		}
	}, [])

	return (
		<div className="mon">
			<div className="mon-body">
				<div ref={glass} className="mon-glass">
					<img className="mon-shot mon-day" src="/img/app/app-light.webp" alt="The map app: the Albufera radar over a satellite map, with the stories, the story card and the season timeline" width={W} height={H} />
					<img className="mon-shot mon-night" src="/img/app/app-dark.webp" alt="" width={W} height={H} />
					{live ? (
						<div className="mon-app" style={{ width: W, height: H }}>
							<MapApp stories={stories} embed />
						</div>
					) : null}
				</div>
			</div>
			<div className="mon-neck" aria-hidden />
			<div className="mon-foot" aria-hidden />
		</div>
	)
}
