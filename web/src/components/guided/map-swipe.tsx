'use client'

// Two pictures of the same ground over the flat map, split by a line the reader drags. The map is flat (no pitch, no
// rotation), so a picture on the Web Mercator lattice sits exactly on its bounds as a plain scaled <img>: its corners
// are projected on every move of the map. Left of the line the first picture, right of it the second.

import type { Map as MapLibreMap } from 'maplibre-gl'
import { useCallback, useEffect, useRef, useState } from 'react'

export type SwipeSide = { src: string; label: string; sub?: string }

export function MapSwipe({
	map,
	bounds,
	left,
	right,
	start = 0.5,
	beside,
}: {
	map: MapLibreMap
	/** west, south, east, north of both pictures */
	bounds: [number, number, number, number]
	left: SwipeSide
	right: SwipeSide
	/** where the line starts, as a share of the screen's width */
	start?: number
	/** on a wide screen, a panel on the left (a CSS selector): the line starts in the middle of the map beside it */
	beside?: string
}) {
	const root = useRef<HTMLDivElement>(null)
	const pics = useRef<HTMLImageElement[]>([])
	const [x, setX] = useState(() => {
		const el = beside ? document.querySelector(beside) : null
		if (!el || window.innerWidth < 900) return start
		return (el.getBoundingClientRect().right + window.innerWidth) / 2 / window.innerWidth
	})
	const xRef = useRef(x)

	// the pictures follow the map
	useEffect(() => {
		const place = () => {
			const [w, s, e, n] = bounds
			const a = map.project([w, n])
			const b = map.project([e, s])
			for (const img of pics.current) {
				if (!img) continue
				img.style.left = `${a.x}px`
				img.style.top = `${a.y}px`
				img.style.width = `${b.x - a.x}px`
				img.style.height = `${b.y - a.y}px`
			}
		}
		place()
		map.on('move', place)
		map.on('resize', place)
		return () => {
			map.off('move', place)
			map.off('resize', place)
		}
	}, [map, bounds])

	const set = useCallback((v: number) => {
		const k = Math.min(0.98, Math.max(0.02, v))
		xRef.current = k
		setX(k)
	}, [])
	const down = (e: React.PointerEvent<HTMLButtonElement>) => {
		const el = root.current
		if (!el) return
		e.preventDefault()
		const r = el.getBoundingClientRect()
		const move = (ev: PointerEvent) => set((ev.clientX - r.left) / Math.max(1, r.width))
		const up = () => {
			window.removeEventListener('pointermove', move)
			window.removeEventListener('pointerup', up)
		}
		window.addEventListener('pointermove', move)
		window.addEventListener('pointerup', up)
	}
	const key = (e: React.KeyboardEvent<HTMLButtonElement>) => {
		const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
		if (!dir) return
		e.preventDefault()
		e.stopPropagation()
		set(xRef.current + dir * 0.05)
	}

	const pct = `${(x * 100).toFixed(2)}%`
	return (
		<div ref={root} className="gd-swipe" style={{ ['--x' as string]: pct }}>
			<div className="gd-swipe-side" data-side="left">
				{/* eslint-disable-next-line @next/next/no-img-element */}
				<img ref={(el) => void (pics.current[0] = el!)} src={left.src} alt="" draggable={false} />
			</div>
			<div className="gd-swipe-side" data-side="right">
				{/* eslint-disable-next-line @next/next/no-img-element */}
				<img ref={(el) => void (pics.current[1] = el!)} src={right.src} alt="" draggable={false} />
			</div>
			<div className="gd-swipe-line" />
			<span className="gd-swipe-label" data-side="left">
				<b>{left.label}</b>
				{left.sub && <small>{left.sub}</small>}
			</span>
			<span className="gd-swipe-label" data-side="right">
				<b>{right.label}</b>
				{right.sub && <small>{right.sub}</small>}
			</span>
			<button
				type="button"
				className="gd-swipe-knob"
				role="slider"
				aria-label={`${left.label} or ${right.label}`}
				aria-valuemin={0}
				aria-valuemax={100}
				aria-valuenow={Math.round(x * 100)}
				onPointerDown={down}
				onKeyDown={key}
			>
				<i />
				<i />
			</button>
		</div>
	)
}
