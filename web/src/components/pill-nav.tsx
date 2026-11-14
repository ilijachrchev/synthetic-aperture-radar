'use client'

import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { useLayoutEffect, useRef, useSyncExternalStore } from 'react'
import { STORIES } from '@/content/stories'
import { storyNav } from '@/lib/story-nav'
import { Mark } from './brand'
import { ThemeSwitch } from './theme-switch'
import './pill-nav.css'

/**
 * The navbar: one glass pill that floats with the page. It names the overview and the stories, a thumb slides
 * under the one on screen (the story playing in the monitor), and each takes you there. The map is one button away:
 * it opens the first story's 3D page, and the others are on the switch there.
 */
export function PillNav({ stories }: { stories: { key: string; tab: string }[] }) {
	const active = useSyncExternalStore(storyNav.subscribe, storyNav.get, () => -1)
	const list = useRef<HTMLDivElement>(null)

	// the thumb sits under the item on screen
	useLayoutEffect(() => {
		const el = list.current
		if (!el) return
		const place = () => {
			const on = el.querySelector<HTMLElement>(`[data-i="${active}"]`)
			if (!on) return
			el.style.setProperty('--x', `${on.offsetLeft}px`)
			el.style.setProperty('--w', `${on.offsetWidth}px`)
		}
		place()
		const ro = new ResizeObserver(place)
		ro.observe(el)
		return () => ro.disconnect()
	}, [active])

	return (
		<header className="pnav">
			<Link href="/" className="pnav-brand" aria-label="Dancing with the SARs, back to the top">
				<Mark size={22} />
				<span className="display">Dancing with the SARs</span>
			</Link>
			<div ref={list} className="pnav-list" role="navigation" aria-label="Sections">
				<button type="button" data-i={-1} aria-current={active === -1 || undefined} onClick={() => storyNav.go(-1)}>
					Overview
				</button>
				{stories.map((s, i) => (
					<button key={s.key} type="button" data-i={i} aria-current={active === i || undefined} onClick={() => storyNav.go(i)}>
						<span className="mono">{String(i + 1).padStart(2, '0')}</span>
						<span className="pnav-name">{s.tab}</span>
					</button>
				))}
			</div>
			<div className="pnav-end">
				<ThemeSwitch />
				<Link href={STORIES[0].path} className="pnav-cta">
					Open the map <ArrowUpRight size={16} strokeWidth={2.4} />
				</Link>
			</div>
		</header>
	)
}
