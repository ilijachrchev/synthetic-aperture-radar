'use client'

import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import './page-ground.css'

gsap.registerPlugin(ScrollTrigger)

/** The page grounds on trial, numbered as on the reference page (design-refs/backgrounds). */
export const GROUNDS = [
	{ id: '1', name: 'Wind lines' },
	{ id: '2', name: 'Currents' },
	{ id: '4', name: 'Radar texture' },
	{ id: '7', name: 'Swath lines' },
	{ id: '8', name: 'Terrain and rivers' },
] as const

const attr = (name: string, fallback: string) => () => document.documentElement.getAttribute(name) ?? fallback
const watch = (names: string[]) => (on: () => void) => {
	const mo = new MutationObserver(on)
	mo.observe(document.documentElement, { attributes: true, attributeFilter: names })
	return () => mo.disconnect()
}
const readGround = attr('data-ground', '8')
const readTheme = attr('data-theme', 'light')
const onGround = watch(['data-ground'])
const onTheme = watch(['data-theme'])

/** A small seeded random, so a drawn ground is the same on every visit. */
function seeded(seed: number) {
	let s = seed >>> 0
	return () => {
		s = (s + 0x6d2b79f5) >>> 0
		let t = s
		t = Math.imul(t ^ (t >>> 15), t | 1)
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296
	}
}
const cssVar = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** 1. The storm's wind: a few long trails turning slowly round a low over the sea, east of the page. */
function Wind() {
	const ref = useRef<HTMLCanvasElement>(null)
	const theme = useSyncExternalStore(onTheme, readTheme, () => 'light')
	useEffect(() => {
		const c = ref.current
		if (!c) return
		const ctx = c.getContext('2d')!
		// faint lines need few pixels: the canvas is drawn at three quarters of the screen's size and scaled up
		const dpr = 0.75
		const rnd = seeded(11)
		let w = 0
		let h = 0
		let parts: { x: number; y: number; age: number; life: number }[] = []
		const colour = cssVar('--wind-line')
		const spawn = (p: { x: number; y: number; age: number; life: number }, fresh: boolean) => {
			p.x = rnd() * w
			p.y = rnd() * h
			p.age = fresh ? Math.floor(rnd() * 120) : 0
			p.life = 110 + rnd() * 130
		}
		const size = () => {
			w = window.innerWidth
			h = window.innerHeight
			c.width = Math.round(w * dpr)
			c.height = Math.round(h * dpr)
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
			// sparse on purpose: about one trail per 18,000 square pixels
			const n = Math.round((w * h) / 18000)
			parts = Array.from({ length: n }, () => {
				const p = { x: 0, y: 0, age: 0, life: 0 }
				spawn(p, true)
				return p
			})
		}
		// a cut-off low turning anticlockwise (as seen from above) and drawing air in, inside a slow westerly
		const vel = (x: number, y: number) => {
			const cx = w * 0.86
			const cy = h * 0.5
			const dx = x - cx
			const dy = y - cy
			const R = Math.max(w, h) * 0.5
			const r = Math.sqrt(dx * dx + dy * dy) + 1
			const s = 1.25 * Math.exp(-(r * r) / (R * R))
			return [(dy / r) * s - (dx / r) * s * 0.18 + 0.32, (-dx / r) * s - (dy / r) * s * 0.18 + 0.04]
		}
		const pen = () => {
			ctx.lineWidth = 1.25
			ctx.lineCap = 'round'
			ctx.strokeStyle = colour
		}
		size()
		pen()
		const step = () => {
			ctx.globalCompositeOperation = 'destination-out'
			ctx.fillStyle = 'rgba(0,0,0,0.035)'
			ctx.fillRect(0, 0, w, h)
			ctx.globalCompositeOperation = 'source-over'
			ctx.beginPath()
			for (const p of parts) {
				const [vx, vy] = vel(p.x, p.y)
				const nx = p.x + vx * 3.6
				const ny = p.y + vy * 3.6
				ctx.moveTo(p.x, p.y)
				ctx.lineTo(nx, ny)
				p.x = nx
				p.y = ny
				p.age++
				if (p.age > p.life || p.x < -20 || p.x > w + 20 || p.y < -20 || p.y > h + 20) spawn(p, false)
			}
			ctx.stroke()
		}
		if (reducedMotion()) {
			// one still frame: the trails drawn out once, no fading
			for (let k = 0; k < 140; k++) {
				ctx.beginPath()
				for (const p of parts) {
					const [vx, vy] = vel(p.x, p.y)
					ctx.moveTo(p.x, p.y)
					p.x += vx * 3.6
					p.y += vy * 3.6
					ctx.lineTo(p.x, p.y)
				}
				ctx.stroke()
			}
			return
		}
		// rest while the stories' stage covers the screen: the wind is hidden behind it there. The track's place on the
		// page is measured when its size changes; each frame only compares it with the scroll position.
		const track = document.querySelector<HTMLElement>('.st-track')
		let span = [Infinity, -Infinity]
		const measure = () => {
			if (!track) return
			const r = track.getBoundingClientRect()
			span = [r.top + window.scrollY, r.bottom + window.scrollY]
		}
		measure()
		const io = track ? new ResizeObserver(measure) : null
		if (track && io) io.observe(track)
		let raf = 0
		let last = 0
		const loop = (t: number) => {
			raf = requestAnimationFrame(loop)
			const y = window.scrollY
			const covered = y >= span[0] && y + window.innerHeight <= span[1]
			if (document.hidden || covered || t - last < 33) return
			last = t
			step()
		}
		raf = requestAnimationFrame(loop)
		const resize = () => {
			size()
			pen()
		}
		window.addEventListener('resize', resize)
		return () => {
			cancelAnimationFrame(raf)
			io?.disconnect()
			window.removeEventListener('resize', resize)
		}
	}, [theme])
	return <canvas ref={ref} className="pg-canvas" aria-hidden />
}

/** 2. Currents: eddies drawn once as fine strokes, the way the Perpetual Ocean paints the sea, then left to drift. */
function Currents() {
	const ref = useRef<HTMLCanvasElement>(null)
	const theme = useSyncExternalStore(onTheme, readTheme, () => 'light')
	useEffect(() => {
		const c = ref.current
		if (!c) return
		const ctx = c.getContext('2d')!
		const dpr = Math.min(2, window.devicePixelRatio || 1)
		const draw = () => {
			// drawn a little larger than the screen so the slow drift never shows an edge
			const w = window.innerWidth * 1.1
			const h = window.innerHeight * 1.1
			c.width = Math.round(w * dpr)
			c.height = Math.round(h * dpr)
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
			const rnd = seeded(7)
			const R = Math.max(w, h)
			const eddies = Array.from({ length: 18 }, () => ({ x: rnd() * w, y: rnd() * h, r: R * (0.05 + rnd() * 0.11), s: rnd() < 0.5 ? -1 : 1 }))
			const vel = (x: number, y: number) => {
				let vx = 0.18
				let vy = 0.05
				for (const e of eddies) {
					const dx = x - e.x
					const dy = y - e.y
					const k = (e.s * Math.exp(-(dx * dx + dy * dy) / (e.r * e.r))) / e.r
					vx += dy * k * 2.2
					vy -= dx * k * 2.2
				}
				const m = Math.hypot(vx, vy) || 1
				return [vx / m, vy / m]
			}
			ctx.clearRect(0, 0, w, h)
			ctx.lineCap = 'round'
			ctx.strokeStyle = cssVar('--current-line')
			const gap = 40
			for (let gy = 0; gy < h; gy += gap)
				for (let gx = 0; gx < w; gx += gap) {
					let x = gx + rnd() * gap
					let y = gy + rnd() * gap
					const n = 14 + Math.floor(rnd() * 22)
					ctx.lineWidth = 0.7 + rnd() * 0.9
					ctx.beginPath()
					ctx.moveTo(x, y)
					for (let k = 0; k < n; k++) {
						const [vx, vy] = vel(x, y)
						x += vx * 3
						y += vy * 3
						ctx.lineTo(x, y)
					}
					ctx.stroke()
				}
		}
		draw()
		window.addEventListener('resize', draw)
		return () => window.removeEventListener('resize', draw)
	}, [theme])
	return <canvas ref={ref} className="pg-canvas pg-drift" aria-hidden />
}

/** 4 and 8: a baked picture of real data, by day and by night, that eases in a touch as the page scrolls. */
function Picture({ name }: { name: 'radar' | 'terrain' }) {
	const ref = useRef<HTMLDivElement>(null)
	useEffect(() => {
		if (!ref.current || reducedMotion()) return
		const tw = gsap.fromTo(ref.current, { scale: 1.02 }, { scale: 1.14, ease: 'none', scrollTrigger: { start: 0, end: 'max', scrub: true } })
		return () => {
			tw.scrollTrigger?.kill()
			tw.kill()
		}
	}, [])
	return (
		<div ref={ref} className="pg-picture" data-name={name}>
			<img className="pg-day" src={`/img/ground/${name}-day.webp`} alt="" decoding="async" />
			<img className="pg-night" src={`/img/ground/${name}-night.webp`} alt="" decoding="async" />
		</div>
	)
}

/** 7. The swath: a fan of fine lines that pinches at each section's heading and spreads between them, threading the
 *  page together, and draws itself on as the page scrolls. */
function Swath() {
	const svg = useRef<SVGSVGElement>(null)
	useEffect(() => {
		const el = svg.current
		if (!el) return
		const NS = 'http://www.w3.org/2000/svg'
		const host = el.parentElement!
		const build = () => {
			const W = host.clientWidth
			const H = host.offsetHeight
			el.setAttribute('viewBox', `0 0 ${W} ${H}`)
			const top = host.getBoundingClientRect().top
			const at = (sel: string, fx: number) => {
				const n = document.querySelector(sel)
				if (!n) return null
				const r = n.getBoundingClientRect()
				return [r.left + r.width * fx, r.top - top + r.height / 2] as [number, number]
			}
			const y = (sel: string) => at(sel, 0.5)?.[1] ?? null
			const ys = [y('.hx-radar'), y('.st .sx-title'), y('#map .sx-title'), y('.foot8-mark')]
			const xs = [W * 0.74, -W * 0.06, W * 1.06, W * 0.5]
			const pins = [[W * 1.12, -80] as [number, number], ...ys.map((v, k) => (v == null ? null : ([xs[k], v] as [number, number]))), [W * 0.5, H + 120] as [number, number]].filter(Boolean) as [number, number][]
			const N = 36
			while (el.firstChild) el.removeChild(el.firstChild)
			for (let i = 0; i < N; i++) {
				const o = i / (N - 1) - 0.5
				let d = ''
				for (let k = 0; k < pins.length - 1; k++) {
					const [x0, y0] = pins[k]
					const [x1, y1] = pins[k + 1]
					const steps = Math.max(8, Math.round((y1 - y0) / 40))
					const spread = W * (k === 0 ? 0.45 : 0.8)
					for (let s = k === 0 ? 0 : 1; s <= steps; s++) {
						const t = s / steps
						const e = t * t * (3 - 2 * t)
						const x = x0 + (x1 - x0) * e + o * spread * Math.sin(Math.PI * t) * (0.6 + 0.4 * Math.cos(i * 0.7 + k))
						const y = y0 + (y1 - y0) * t
						d += `${d ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`
					}
				}
				const p = document.createElementNS(NS, 'path')
				p.setAttribute('d', d)
				p.setAttribute('pathLength', '1')
				el.appendChild(p)
			}
		}
		build()
		const ro = new ResizeObserver(() => build())
		ro.observe(host)
		const reduced = reducedMotion()
		const draw = () => {
			const H = document.documentElement.scrollHeight
			const p = reduced ? 1 : Math.min(1, (window.scrollY + window.innerHeight * 1.15) / H)
			el.style.setProperty('--draw', p.toFixed(4))
		}
		draw()
		const st = ScrollTrigger.create({ start: 0, end: 'max', onUpdate: draw, onRefresh: draw })
		return () => {
			ro.disconnect()
			st.kill()
		}
	}, [])
	return <svg ref={svg} className="pg-swath" aria-hidden preserveAspectRatio="none" />
}

/** The page's ground: whichever one is picked, behind everything. */
export function PageGround() {
	const g = useSyncExternalStore(onGround, readGround, () => '')
	if (g === '1') return <div className="pg">{<Wind />}</div>
	if (g === '2') return <div className="pg">{<Currents />}</div>
	if (g === '4') return <div className="pg">{<Picture name="radar" />}</div>
	if (g === '7') return <Swath />
	if (g === '8') return <div className="pg">{<Picture name="terrain" />}</div>
	return null
}

/** The picker for the grounds on trial: a numbered pill in the corner, remembered across visits. */
export function GroundSwitch() {
	const g = useSyncExternalStore(onGround, readGround, () => '8')
	const self = useRef<HTMLDivElement>(null)
	// on a phone it sits at the bottom, so it steps aside while the stories' stage (and its own controls) fills the
	// screen, and over the footer's wordmark at the very end
	useEffect(() => {
		const track = document.querySelector<HTMLElement>('.st-track')
		if (!track || !self.current) return
		let span = [Infinity, -Infinity]
		const measure = () => {
			const r = track.getBoundingClientRect()
			span = [r.top + window.scrollY, r.bottom + window.scrollY]
		}
		let raf = 0
		const check = () => {
			raf = 0
			const y = window.scrollY
			const end = y + window.innerHeight > document.documentElement.scrollHeight - 150
			self.current?.toggleAttribute('data-aside', end || (y + window.innerHeight > span[0] + 40 && y < span[1] - window.innerHeight * 0.6))
		}
		const onScroll = () => {
			if (!raf) raf = requestAnimationFrame(check)
		}
		measure()
		check()
		const ro = new ResizeObserver(() => {
			measure()
			check()
		})
		ro.observe(track)
		window.addEventListener('scroll', onScroll, { passive: true })
		return () => {
			ro.disconnect()
			window.removeEventListener('scroll', onScroll)
			cancelAnimationFrame(raf)
		}
	}, [])
	const pick = useCallback((id: string) => {
		const apply = () => {
			document.documentElement.setAttribute('data-ground', id)
			try {
				localStorage.setItem('ground', id)
			} catch {}
			requestAnimationFrame(() => ScrollTrigger.refresh())
		}
		if (!document.startViewTransition || reducedMotion()) return apply()
		document.startViewTransition(apply)
	}, [])
	return (
		<div ref={self} className="gpick" role="group" aria-label="Page background">
			<span className="mono">BG</span>
			{GROUNDS.map((x) => (
				<button key={x.id} type="button" aria-pressed={g === x.id} title={`${x.id}. ${x.name}`} onClick={() => pick(x.id)}>
					{x.id}
				</button>
			))}
		</div>
	)
}
