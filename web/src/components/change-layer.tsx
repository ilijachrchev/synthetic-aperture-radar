// Used only inside client components (the map app and the hero), so it needs no directive of its own.
import { useEffect, useRef } from 'react'

export type ChangeKind = 'water' | 'fire' | 'sink' | 'quake'

/**
 * Change, animated from the radar itself. Every pass of a track is read pixel by pixel into one value per pixel:
 *  water  how dark the pixel is (open water and flooded fields send the pulse away, so they read dark)
 *  fire   how much canopy brightness (the green, cross-polarised channel) it lost against the passes before the fire
 *  sink   the ground-motion colour of a pair, from blue through white to red, as one signed value
 *  quake  the fringe pattern of a pair, read from its brightness
 * Between two passes the value is eased from one to the next and drawn through a threshold, so edges move like a
 * shoreline: water spreads and drains, a scar burns in, contour lines and fringes flow. A quick estimate from the
 * public previews, not the project's models; the app says so beside it.
 */

type Fields = { w: number; h: number; v: Float32Array[]; a: Uint8Array[]; perm: Uint8Array | null; rgb: Uint8ClampedArray[] | null }

const smooth = (e0: number, e1: number, x: number) => {
	const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)))
	return t * t * (3 - 2 * t)
}

/** A separable box blur: speckle stops flickering and thresholds trace smooth edges, like a shoreline. */
function blur(src: Float32Array, w: number, h: number, r: number) {
	if (r < 1) return src
	const tmp = new Float32Array(src.length)
	const out = new Float32Array(src.length)
	const k = 2 * r + 1
	for (let y = 0; y < h; y++) {
		let acc = 0
		const row = y * w
		for (let x = -r; x <= r; x++) acc += src[row + Math.min(w - 1, Math.max(0, x))]
		for (let x = 0; x < w; x++) {
			tmp[row + x] = acc / k
			acc += src[row + Math.min(w - 1, x + r + 1)] - src[row + Math.max(0, x - r)]
		}
	}
	for (let x = 0; x < w; x++) {
		let acc = 0
		for (let y = -r; y <= r; y++) acc += tmp[Math.min(h - 1, Math.max(0, y)) * w + x]
		for (let y = 0; y < h; y++) {
			out[y * w + x] = acc / k
			acc += tmp[Math.min(h - 1, y + r + 1) * w + x] - tmp[Math.max(0, y - r) * w + x]
		}
	}
	return out
}
const BLUR: Record<ChangeKind, number> = { water: 1, fire: 2, sink: 2, quake: 1 }

/** A cyclic ramp through the Lagoon colours for fringes: abyss, deep, glow, white, back to the abyss. */
const STOPS = [
	[6, 15, 19],
	[0, 131, 194],
	[127, 224, 240],
	[246, 253, 255],
	[6, 15, 19],
]
function cyc(ph: number, out: number[]) {
	const s = ph * 4
	const i = Math.min(3, Math.floor(s))
	const f = s - i
	const A = STOPS[i]
	const B = STOPS[i + 1]
	out[0] = A[0] + (B[0] - A[0]) * f
	out[1] = A[1] + (B[1] - A[1]) * f
	out[2] = A[2] + (B[2] - A[2]) * f
}

function load(src: string) {
	return new Promise<HTMLImageElement>((ok, bad) => {
		const im = new Image()
		im.onload = () => ok(im)
		im.onerror = bad
		im.src = src
	})
}

function readFields(kind: ChangeKind, imgs: HTMLImageElement[], refCount: number, keepRgb: boolean): Fields {
	const w = imgs[imgs.length - 1].naturalWidth
	const h = imgs[imgs.length - 1].naturalHeight
	const c = document.createElement('canvas')
	c.width = w
	c.height = h
	const ctx = c.getContext('2d', { willReadFrequently: true })!
	const n = w * h
	const v: Float32Array[] = []
	const a: Uint8Array[] = []
	const green: Float32Array[] = []
	const luma: Float32Array[] = []
	const rgbs: Uint8ClampedArray[] = []
	for (const im of imgs) {
		ctx.clearRect(0, 0, w, h)
		ctx.drawImage(im, 0, 0, w, h)
		const d = ctx.getImageData(0, 0, w, h).data
		if (keepRgb) rgbs.push(d)
		const val = new Float32Array(n)
		const al = new Uint8Array(n)
		const g = new Float32Array(n)
		const l = new Float32Array(n)
		for (let p = 0; p < n; p++) {
			const r = d[p * 4] / 255
			const gg = d[p * 4 + 1] / 255
			const b = d[p * 4 + 2] / 255
			al[p] = d[p * 4 + 3]
			const L = 0.3 * r + 0.59 * gg + 0.11 * b
			l[p] = L
			g[p] = gg
			if (kind === 'water') val[p] = smooth(0.46, 0.16, L)
			else if (kind === 'sink') val[p] = r - b
			else if (kind === 'quake') val[p] = L
		}
		v.push(val)
		a.push(al)
		green.push(g)
		luma.push(l)
	}
	if (kind === 'fire') {
		const k = Math.max(1, Math.min(refCount, imgs.length))
		const gRef = new Float32Array(n)
		const lRef = new Float32Array(n)
		for (let f = 0; f < k; f++)
			for (let p = 0; p < n; p++) {
				gRef[p] += green[f][p] / k
				lRef[p] += luma[f][p] / k
			}
		for (let f = 0; f < imgs.length; f++)
			for (let p = 0; p < n; p++) v[f][p] = Math.min(1, Math.max(0, ((gRef[p] - green[f][p]) * 0.7 + (lRef[p] - luma[f][p]) * 0.3) * 5 - 0.12))
	}
	for (let f = 0; f < v.length; f++) v[f] = blur(v[f], w, h, BLUR[kind])
	let perm: Uint8Array | null = null
	if (kind === 'water') {
		perm = new Uint8Array(n)
		for (let p = 0; p < n; p++) {
			let wet = 0
			for (let f = 0; f < v.length; f++) if (v[f][p] > 0.5) wet++
			perm[p] = wet >= 0.85 * v.length ? 1 : 0
		}
	}
	return { w, h, v, a, perm, rgb: keepRgb ? rgbs : null }
}

const rgb = [0, 0, 0]
/** base > 0 paints the radar itself under the change (eased between the same two passes, quieted), so the picture
 *  and its change can never drift apart; base 0 paints the change alone over pictures drawn elsewhere. */
function paint(out: Uint8ClampedArray, F: Fields, kind: ChangeKind, t: number, time: number, reveal: number, epi: [number, number], revealAt: number, base: number) {
	const live = revealAt < 0 || Math.round(t) === revealAt
	const { w, h, v, a, perm } = F
	const RA = base > 0 && F.rgb ? F.rgb[Math.max(0, Math.min(v.length - 1, Math.floor(t)))] : null
	const RB = base > 0 && F.rgb ? F.rgb[Math.min(v.length - 1, Math.max(0, Math.floor(t)) + 1)] : null
	const i0 = Math.max(0, Math.min(v.length - 1, Math.floor(t)))
	const i1 = Math.min(v.length - 1, i0 + 1)
	const f = t - i0
	const e = f * f * (3 - 2 * f)
	const A = v[i0]
	const B = v[i1]
	const aA = a[i0]
	const aB = a[i1]
	const n = w * h
	for (let p = 0; p < n; p++) {
		const o = p * 4
		const alpha = aA[p] + (aB[p] - aA[p]) * e
		if (alpha < 12) {
			out[o + 3] = 0
			continue
		}
		const x = A[p] + (B[p] - A[p]) * e
		let r = 0
		let g = 0
		let b = 0
		let al = 0
		if (kind === 'water') {
			if (perm && perm[p]) {
				r = 30
				g = 80
				b = 150
				al = 0.32
			} else {
				const fill = smooth(0.3, 0.78, x)
				const edge = Math.max(0, 1 - Math.abs(x - 0.55) * 7)
				r = 54 + 160 * edge
				g = 214 + 40 * edge
				b = 255
				al = Math.min(0.95, fill * 0.85 + edge * 0.3)
			}
		} else if (kind === 'fire') {
			const fill = smooth(0.24, 0.5, x)
			const edge = Math.max(0, 1 - Math.abs(x - 0.36) * 9)
			const hot = smooth(0.3, 0.85, x)
			r = 255 - 75 * hot
			g = 196 - 150 * hot
			b = 80 - 50 * hot
			const flicker = 0.65 + 0.35 * Math.sin(time * 7 + (p % w) * 0.21 + Math.floor(p / w) * 0.17)
			al = Math.min(1, fill * 0.82 + edge * 0.6 * flicker)
		} else if (kind === 'sink') {
			const m = Math.min(1, Math.abs(x) * 1.6)
			if (x < 0) {
				r = 70
				g = 150
				b = 255
			} else {
				r = 255
				g = 110
				b = 90
			}
			al = 0.1 + m * 0.42
			// contour lines, drawn as a soft band so they stay smooth when the picture is scaled up
			const c = (((x * 4 + time * 0.22) % 1) + 1) % 1
			const line = 1 - smooth(0.018, 0.06, Math.min(c, 1 - c))
			if (line > 0) {
				r += (255 - r) * line
				g += (255 - g) * line
				b += (255 - b) * line
				al = Math.max(al, 0.85 * line)
			}
		} else {
			const ph = (((x * 2.4 + time * 0.3) % 1) + 1) % 1
			cyc(ph, rgb)
			r = rgb[0]
			g = rgb[1]
			b = rgb[2]
			al = live ? 0.92 : 0.42
			if (live && reveal < 1) {
				const dx = (p % w) / w - epi[0]
				const dy = Math.floor(p / w) / h - epi[1]
				const d = Math.sqrt(dx * dx * ((w / h) * (w / h)) + dy * dy)
				const R = reveal * 1.6
				al *= smooth(R + 0.04, R - 0.04, d)
				const ring = Math.max(0, 1 - Math.abs(d - R) * 40)
				if (ring > 0) {
					r += (255 - r) * ring
					g += (255 - g) * ring
					b += (255 - b) * ring
					al = Math.max(al, ring)
				}
			}
		}
		if (RA && RB) {
			// the radar, eased between the two passes and quieted, with the change laid over it
			const br = RA[o] + (RB[o] - RA[o]) * e
			const bg = RA[o + 1] + (RB[o + 1] - RA[o + 1]) * e
			const bb = RA[o + 2] + (RB[o + 2] - RA[o + 2]) * e
			const L = 0.3 * br + 0.59 * bg + 0.11 * bb
			const qr = (L + (br - L) * 0.5) * 0.62
			const qg = (L + (bg - L) * 0.5) * 0.62
			const qb = (L + (bb - L) * 0.5) * 0.66
			out[o] = qr + (r - qr) * al
			out[o + 1] = qg + (g - qg) * al
			out[o + 2] = qb + (b - qb) * al
			out[o + 3] = Math.max(base, al) * alpha
			continue
		}
		out[o] = r
		out[o + 1] = g
		out[o + 2] = b
		out[o + 3] = al * alpha
	}
}

export function ChangeLayer({
	kind,
	frames,
	index = 0,
	playing = false,
	onIndex,
	refCount = 1,
	speed = 0.55,
	epicentre = [0.5, 0.5],
	revealAt = -1,
	scrub,
	active = true,
	base = 0,
	className,
}: {
	kind: ChangeKind
	frames: string[]
	index?: number
	playing?: boolean
	onIndex?: (i: number) => void
	refCount?: number
	/** passes per second while playing */
	speed?: number
	/** where a quake's reveal starts, as fractions of the frame */
	epicentre?: [number, number]
	/** the pass (a pair spanning the event) that reveals from the epicentre and plays at full strength; -1 for all */
	revealAt?: number
	/** driven from outside (the page's scroll): the pass position, 0 to frames - 1, read every frame */
	scrub?: { current: number }
	/** off while hidden under another scene: nothing is painted */
	active?: boolean
	/** above 0, the radar itself is painted under the change at this opacity */
	base?: number
	className?: string
}) {
	const canvas = useRef<HTMLCanvasElement>(null)
	const fields = useRef<Fields | null>(null)
	const st = useRef({ t: index, target: index, playing, reveal: 1, revealFor: -1, shown: index, drawn: -1 })
	const cb = useRef(onIndex)
	cb.current = onIndex
	const epi = useRef(epicentre)
	epi.current = epicentre
	const rev = useRef(revealAt)
	rev.current = revealAt
	const on = useRef(active)
	on.current = active
	const scr = useRef(scrub)
	scr.current = scrub
	st.current.target = index
	st.current.playing = playing
	const key = `${kind}|${refCount}|${base > 0}|${frames.join('|')}`

	useEffect(() => {
		let gone = false
		let idle = 0
		fields.current = null
		Promise.all(frames.map(load))
			.then((imgs) => {
				if (gone || !canvas.current) return
				// reading every pass is the heavy part: do it when the page is idle, so scrolling never stalls on it
				const read = () => {
					if (gone || !canvas.current) return
					const F = readFields(kind, imgs, refCount, base > 0)
					canvas.current.width = F.w
					canvas.current.height = F.h
					fields.current = F
					st.current.t = scr.current ? scr.current.current : st.current.target
					st.current.drawn = -1
				}
				if ('requestIdleCallback' in window) idle = window.requestIdleCallback(read, { timeout: 900 })
				else read()
			})
			.catch(() => {})
		return () => {
			gone = true
			if (idle && 'cancelIdleCallback' in window) window.cancelIdleCallback(idle)
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [key])

	useEffect(() => {
		const el = canvas.current
		if (!el) return
		const ctx = el.getContext('2d')!
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		// water has no motion of its own, so a still scrubbed water layer is not repainted
		const lives = kind !== 'water'
		let raf = 0
		let last = 0
		let seen = true
		let img: ImageData | null = null
		const io = new IntersectionObserver(([en]) => (seen = en.isIntersecting))
		io.observe(el)
		const loop = (now: number) => {
			raf = requestAnimationFrame(loop)
			if (!seen || !on.current) return
			const F = fields.current
			if (!F) return
			const s = st.current
			const n = F.v.length
			const driven = scr.current
			if (driven) {
				const t = Math.min(n - 1, Math.max(0, driven.current))
				// scrolled: paint on this frame; still: only what moves on its own, at about 30fps
				const moved = Math.abs(t - s.drawn) > 0.0005
				if (!moved && (!lives || reduced || now - last < 33)) return
				last = now
				s.t = t
				s.drawn = t
				// the pair that spans a quake reveals from the epicentre as it is scrolled into
				s.reveal = rev.current >= 1 ? Math.min(1, Math.max(0, t - (rev.current - 1))) : 1
				if (!img || img.width !== F.w || img.height !== F.h) img = ctx.createImageData(F.w, F.h)
				paint(img.data, F, kind, t, reduced ? 0 : now / 1000, s.reveal, epi.current, rev.current, base)
				ctx.putImageData(img, 0, 0)
				return
			}
			if (now - last < 33) return
			const dt = Math.min(0.1, (now - (last || now)) / 1000)
			last = now
			if (s.playing && !reduced) {
				s.t += dt * speed
				if (s.t > n - 1) s.t = 0
				const fi = Math.floor(s.t)
				if (fi !== s.shown) {
					s.shown = fi
					cb.current?.(fi)
				}
			} else {
				s.t = reduced ? s.target : s.t + (s.target - s.t) * Math.min(1, dt * 5)
				s.shown = Math.round(s.target)
			}
			// a quake pair reveals from the epicentre each time it comes up
			const cur = Math.round(s.t)
			if (kind === 'quake' && cur !== s.revealFor && cur === rev.current) {
				s.revealFor = cur
				s.reveal = 0
			}
			if (s.reveal < 1) s.reveal = Math.min(1, s.reveal + dt * 0.55)
			if (!img || img.width !== F.w || img.height !== F.h) img = ctx.createImageData(F.w, F.h)
			paint(img.data, F, kind, Math.min(n - 1, Math.max(0, s.t)), reduced ? 0 : now / 1000, reduced ? 1 : s.reveal, epi.current, rev.current, base)
			ctx.putImageData(img, 0, 0)
		}
		raf = requestAnimationFrame(loop)
		return () => {
			cancelAnimationFrame(raf)
			io.disconnect()
		}
	}, [kind, speed, base])

	return <canvas ref={canvas} className={className} aria-hidden />
}
