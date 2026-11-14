'use client'

import { useEffect, useRef } from 'react'

// The footer's land, after 8x.social's: misty ridges drawn as a halftone screen, dots large where the land is dark
// and gone where the mist lies, the mist drifting slowly along the valleys. Everything is procedural (no image), so
// it needs no SI watermark. Ridges stand for the hills behind the Albufera; the flat band at the bottom is the
// paddies. Dots in the palette's 30% colour (--deep). Runs only while on screen; reduced motion draws one frame.

const CELL = 6

function hash(n: number) {
	const s = Math.sin(n * 127.1 + 311.7) * 43758.5453
	return s - Math.floor(s)
}
function noise1(x: number) {
	const i = Math.floor(x)
	const f = x - i
	const u = f * f * (3 - 2 * f)
	return hash(i) * (1 - u) + hash(i + 1) * u
}
function fbm1(x: number, oct = 4) {
	let v = 0
	let a = 0.5
	let f = 1
	for (let o = 0; o < oct; o++) {
		v += a * noise1(x * f + o * 17.3)
		f *= 2.03
		a *= 0.5
	}
	return v
}
function hash2(x: number, y: number) {
	const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
	return s - Math.floor(s)
}
function noise2(x: number, y: number) {
	const xi = Math.floor(x)
	const yi = Math.floor(y)
	const xf = x - xi
	const yf = y - yi
	const u = xf * xf * (3 - 2 * xf)
	const v = yf * yf * (3 - 2 * yf)
	const a = hash2(xi, yi)
	const b = hash2(xi + 1, yi)
	const c = hash2(xi, yi + 1)
	const d = hash2(xi + 1, yi + 1)
	return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}

// ridge layers, far to near. Each crest is a range of named peaks (x, height, width) so the silhouettes read as
// mountains, with a little noise on top for rock. base: the valley floor of the layer; tone: dot density at the
// crest; fade: how far below the crest the mist takes over; jag: a tree line on the near hills.
type Layer = { base: number; peaks: [number, number, number][]; tone: number; fade: number; jag: number; rough: number }
const LAYERS: Layer[] = [
	{ base: 0.5, peaks: [[0.16, 0.36, 0.13], [0.47, 0.26, 0.16], [0.83, 0.38, 0.12], [1.05, 0.22, 0.1]], tone: 0.34, fade: 0.16, jag: 0, rough: 0.03 },
	{ base: 0.62, peaks: [[0.0, 0.2, 0.1], [0.33, 0.3, 0.12], [0.66, 0.24, 0.15], [0.97, 0.18, 0.1]], tone: 0.52, fade: 0.16, jag: 0, rough: 0.025 },
	{ base: 0.74, peaks: [[0.22, 0.16, 0.16], [0.55, 0.1, 0.12], [0.88, 0.17, 0.14]], tone: 0.72, fade: 0.18, jag: 0.008, rough: 0.02 },
	{ base: 0.86, peaks: [[0.1, 0.06, 0.12], [0.42, 0.05, 0.18], [0.75, 0.07, 0.12]], tone: 0.92, fade: 0.26, jag: 0.014, rough: 0.012 },
]
function crestAt(L: Layer, xn: number, k: number) {
	let lift = 0
	// a power under 2 gives ridges a peak rather than a dome
	for (const [px, ph, pw] of L.peaks) lift = Math.max(lift, ph * Math.exp(-(Math.abs((xn - px) / pw) ** 1.35)))
	const rock = L.rough * (fbm1(xn * 9 + k * 7.7) - 0.5) * 2
	const trees = L.jag ? L.jag * (noise1(xn * 260 + k) - 0.5) * 2 : 0
	return L.base - lift + rock + trees
}

export function HalftoneLand({ className = '' }: { className?: string }) {
	const ref = useRef<HTMLCanvasElement>(null)

	useEffect(() => {
		const canvas = ref.current
		if (!canvas) return
		const ctx = canvas.getContext('2d')
		if (!ctx) return
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		let cols = 0
		let rows = 0
		let base = new Float32Array(0)
		let mist = new Float32Array(0)
		let w = 0
		let h = 0
		let raf = 0
		let visible = false
		let last = 0

		const build = () => {
			const r = canvas.getBoundingClientRect()
			const dpr = Math.min(2, window.devicePixelRatio || 1)
			w = r.width
			h = r.height
			canvas.width = Math.round(w * dpr)
			canvas.height = Math.round(h * dpr)
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
			const cell = w < 640 ? 5 : CELL
			cols = Math.ceil(w / cell) + 1
			rows = Math.ceil(h / cell) + 1
			base = new Float32Array(cols * rows)
			mist = new Float32Array(cols * rows)
			// narrow screens see a window of the same range at the same scale, so peaks keep their shape
			const span = Math.min(1, w / 1200)
			for (let cx = 0; cx < cols; cx++) {
				const xn = 0.5 - span / 2 + (cx / cols) * span
				const crest = LAYERS.map((L, k) => crestAt(L, xn, k))
				for (let cy = 0; cy < rows; cy++) {
					const yn = cy / rows
					let d = 0.015
					let m = 0
					for (let k = LAYERS.length - 1; k >= 0; k--) {
						const below = yn - crest[k]
						if (below >= 0) {
							const L = LAYERS[k]
							const t = Math.min(1, below / L.fade)
							d = L.tone * (1 - t * t * (3 - 2 * t)) * 0.82 + L.tone * 0.12
							m = Math.exp(-(((below - L.fade * 0.85) / (L.fade * 0.5)) ** 2))
							break
						}
					}
					// the foot of the land darkens into the paddies, where the wordmark sits
					if (yn > 0.86) d = Math.max(d, 0.7 + (yn - 0.86) * 2)
					base[cy * cols + cx] = d
					mist[cy * cols + cx] = m
				}
			}
		}

		const draw = (time: number) => {
			ctx.clearRect(0, 0, w, h)
			ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--deep').trim() || '#0b3d57'
			const cell = w < 640 ? 5 : CELL
			const maxR = cell * 0.62
			const drift = time * 0.000035
			ctx.beginPath()
			for (let cy = 0; cy < rows; cy++) {
				for (let cx = 0; cx < cols; cx++) {
					const i = cy * cols + cx
					let d = base[i]
					const m = mist[i]
					if (m > 0.02) {
						const f = noise2(cx * 0.045 + drift * 60, cy * 0.11 + Math.sin(drift * 9 + cx * 0.01) * 0.6)
						d *= 1 - 0.85 * m * Math.min(1, f * 1.35)
					}
					const r = maxR * Math.sqrt(d)
					if (r < 0.32) continue
					const x = cx * cell + (cy % 2 ? cell / 2 : 0)
					const y = cy * cell
					ctx.moveTo(x + r, y)
					ctx.arc(x, y, r, 0, Math.PI * 2)
				}
			}
			ctx.fill()
		}

		const loop = (t: number) => {
			raf = requestAnimationFrame(loop)
			if (t - last < 42) return // about 24 frames a second is plenty for drifting mist
			last = t
			draw(t)
		}

		build()
		draw(0)
		const ro = new ResizeObserver(() => {
			build()
			draw(performance.now())
		})
		ro.observe(canvas)
		const io = new IntersectionObserver(([e]) => {
			visible = e.isIntersecting
			cancelAnimationFrame(raf)
			if (visible && !reduced) raf = requestAnimationFrame(loop)
		})
		io.observe(canvas)
		const mo = new MutationObserver(() => draw(performance.now()))
		mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-palette'] })
		return () => {
			cancelAnimationFrame(raf)
			ro.disconnect()
			io.disconnect()
			mo.disconnect()
		}
	}, [])

	return <canvas ref={ref} className={className} aria-hidden />
}
