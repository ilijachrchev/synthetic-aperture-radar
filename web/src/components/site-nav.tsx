'use client'

// The small navbar of every page: the flood map (the guided tour), Explore (every layer), Stories (the 3D pages of how
// the land changes over time) and How it works. On the landing it floats as a glass pill with the name of the site,
// one row on a wide screen and a compact menu on a phone. On the map pages the map comes first: no name, and the
// navbar shows one item (the page you are on) with a >> button that opens the rest, white on glass in the top left.
// On paper pages it takes the ink of the theme.

import { ChevronDown, ChevronsLeft, ChevronsRight, Menu, X } from 'lucide-react'
import Link from 'next/link'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { SITE } from '@/content/site'
import { STORIES } from '@/content/stories'
import { Mark } from './brand'
import './site-nav.css'

export type NavKey = 'map' | 'explore' | 'stories' | 'how'

export const NAV_STORIES = 'How the land changes over time, seen by NISAR every 12 days.'

const LABELS: Record<NavKey, string> = { map: 'The flood map', explore: 'Explore', stories: 'Stories', how: 'How it works' }

export function SiteNav({
	active,
	variant = 'map',
	onGo,
	end,
}: {
	/** the item of the page on screen */
	active?: NavKey
	/** pill: the landing's floating glass pill; map: folded over a map photograph; page: on the theme's paper */
	variant?: 'pill' | 'map' | 'page'
	/** /explore switches between the guide and every layer without reloading: return true when it did */
	onGo?: (k: 'map' | 'explore') => boolean
	/** something more at the end of the row (the landing's day and night switch) */
	end?: ReactNode
}) {
	const [stories, setStories] = useState(false)
	const [menu, setMenu] = useState(false)
	/** the map pages: the navbar folded to one item, or open */
	const [open, setOpen] = useState(false)
	const root = useRef<HTMLElement>(null)
	const folds = variant === 'map'

	// a click elsewhere or Escape closes what is open
	useEffect(() => {
		if (!stories && !menu && !open) return
		const away = (e: PointerEvent) => {
			if (root.current && !root.current.contains(e.target as Node)) {
				setStories(false)
				setMenu(false)
				setOpen(false)
			}
		}
		const key = (e: KeyboardEvent) => {
			if (e.key === 'Escape') {
				setStories(false)
				setMenu(false)
				setOpen(false)
			}
		}
		window.addEventListener('pointerdown', away)
		window.addEventListener('keydown', key)
		return () => {
			window.removeEventListener('pointerdown', away)
			window.removeEventListener('keydown', key)
		}
	}, [stories, menu, open])

	const go = (k: 'map' | 'explore') => (e: React.MouseEvent) => {
		if (onGo?.(k)) {
			e.preventDefault()
			setMenu(false)
			setOpen(false)
		}
	}
	const cur = (k: NavKey) => (active === k ? 'page' : undefined)
	// /explore and /explore?all are one page: plain links, so the page reads its address again
	const items = (
		<>
			<a href="/explore" aria-current={cur('map')} onClick={go('map')}>
				{LABELS.map}
			</a>
			<a href="/explore?all" aria-current={cur('explore')} onClick={go('explore')}>
				{LABELS.explore}
			</a>
		</>
	)
	const storyList = (
		<>
			<p>{NAV_STORIES}</p>
			{STORIES.map((s) => (
				<Link key={s.key} href={s.path} onClick={() => setStories(false)}>
					<b>{s.title}</b>
					<small>{s.place}</small>
				</Link>
			))}
		</>
	)
	const all = (
		<>
			{items}
			<div className="snav-more">
				<button type="button" aria-expanded={stories} aria-current={cur('stories')} onClick={() => setStories((v) => !v)}>
					{LABELS.stories} <ChevronDown size={14} strokeWidth={2.6} />
				</button>
				{stories && <div className="snav-pop">{storyList}</div>}
			</div>
			<Link href="/#how" aria-current={cur('how')}>
				{LABELS.how}
			</Link>
		</>
	)

	// the map pages: one item and a >> button, no name; the button opens the rest
	if (folds) {
		return (
			<nav ref={root} className="snav" data-variant="map" data-open={open || undefined} aria-label="Site">
				<div className="snav-items">
					{open ? (
						all
					) : active ? (
						<span className="snav-here" aria-current="page">
							{LABELS[active]}
						</span>
					) : (
						<a href="/explore">{LABELS.map}</a>
					)}
					<button type="button" className="snav-toggle" aria-expanded={open} aria-label={open ? 'Show less' : 'Show every page'} onClick={() => setOpen((v) => !v)}>
						{open ? <ChevronsLeft size={17} strokeWidth={2.4} /> : <ChevronsRight size={17} strokeWidth={2.4} />}
					</button>
				</div>
			</nav>
		)
	}

	return (
		<nav ref={root} className="snav" data-variant={variant} aria-label="Site">
			<Link href="/" className="snav-brand" aria-label={`${SITE.name}, home`}>
				<Mark size={variant === 'pill' ? 22 : 20} />
				<span className={variant === 'pill' ? 'display' : undefined}>{SITE.name}</span>
			</Link>
			<div className="snav-items">{all}</div>
			{end && <div className="snav-end">{end}</div>}
			<button type="button" className="snav-menu" aria-expanded={menu} aria-label={menu ? 'Close the menu' : 'Open the menu'} onClick={() => setMenu((v) => !v)}>
				{menu ? <X size={18} strokeWidth={2.4} /> : <Menu size={18} strokeWidth={2.4} />}
			</button>
			{menu && (
				<div className="snav-sheet">
					{items}
					<div className="snav-sheet-stories">
						<span>{LABELS.stories}</span>
						{storyList}
					</div>
					<Link href="/#how" aria-current={cur('how')} onClick={() => setMenu(false)}>
						{LABELS.how}
					</Link>
				</div>
			)}
		</nav>
	)
}
