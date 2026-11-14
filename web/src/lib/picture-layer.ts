// Real satellite pictures of one place on chosen days, drawn as a MapLibre custom layer so the app can fade from
// one day to the next, dim them under the radar layer and cut them along a swipe line.
// The pictures are Sentinel-2 true colour, untouched (scripts/fetch_optical.py). A cloudy day stays cloudy.
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MapLibreMap } from 'maplibre-gl'
import { type Bounds, QUAD_VERT, buildProgram, quadMatrix, unitQuad, withClip } from './gl-quad'

const FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_tex;
uniform float u_alpha;
uniform float u_sat;
uniform float u_bright;
void main() {
	vec3 c = texture(u_tex, v_uv).rgb;
	float l = dot(c, vec3(0.299, 0.587, 0.114));
	vec3 rgb = mix(vec3(l), c, u_sat) * u_bright;
	// the picture melts into the base map at its edges instead of ending in a hard rectangle
	float rim = min(min(v_uv.x, 1.0 - v_uv.x), min(v_uv.y, 1.0 - v_uv.y));
	float a = u_alpha * smoothstep(0.0, 0.018, rim);
	fragColor = vec4(rgb * a, a);
}`

type Shot = { key: string; tex: WebGLTexture }

export class PictureLayer {
	readonly id: string
	readonly layer: CustomLayerInterface
	private bounds: Bounds
	private map: MapLibreMap | null = null
	private program: WebGLProgram | null = null
	private vao: WebGLVertexArrayObject | null = null
	private buffer: WebGLBuffer | null = null
	private u: Record<string, WebGLUniformLocation | null> = {}
	private front: Shot | null = null
	private back: Shot | null = null
	private fadeStart = 0
	private fadeMs = 700
	private pending: { key: string; bitmap: ImageBitmap } | null = null
	private wanted: string | null = null
	private urls = new Map<string, string>()
	private cache = new Map<string, Promise<ImageBitmap>>()
	private clip: [number, number] = [0, 1]
	private opacity = 1
	private opacityFrom = 1
	private opacityTo = 1
	private opacityStart = 0
	private sat = 1
	private bright = 1
	private dim = new Map<string, [number, number]>()
	private dimmed = false
	private alpha = 1
	private maxSize: number
	private gone = false
	/** called when a picture is on screen */
	onShow: ((key: string) => void) | null = null

	constructor(opts: { id: string; bounds: Bounds; pictures: { key: string; url: string }[]; maxSize?: number }) {
		this.id = opts.id
		this.bounds = opts.bounds
		this.maxSize = opts.maxSize ?? 4096
		for (const p of opts.pictures) this.urls.set(p.key, p.url)
		this.layer = {
			id: this.id,
			type: 'custom',
			renderingMode: '2d',
			onAdd: (map, gl) => {
				this.map = map
				this.program = buildProgram(gl, QUAD_VERT, FRAG)
				for (const n of ['u_matrix', 'u_tex', 'u_alpha', 'u_sat', 'u_bright']) this.u[n] = gl.getUniformLocation(this.program, n)
				const q = unitQuad(gl, this.program)
				this.vao = q.vao
				this.buffer = q.buffer
				if (this.wanted) this.show(this.wanted)
			},
			onRemove: (_map, gl) => {
				this.gone = true
				for (const s of [this.front, this.back]) if (s) gl.deleteTexture(s.tex)
				if (this.program) gl.deleteProgram(this.program)
				if (this.buffer) gl.deleteBuffer(this.buffer)
				if (this.vao) gl.deleteVertexArray(this.vao)
				this.pending?.bitmap.close()
				this.map = null
			},
			render: (gl, input) => this.render(gl, input),
		}
	}

	/** fetch and decode a picture ahead of time */
	preload(key: string) {
		const url = this.urls.get(key)
		if (!url) return null
		let job = this.cache.get(key)
		if (!job) {
			job = fetch(url)
				.then((r) => {
					if (!r.ok) throw new Error(`${url}: ${r.status}`)
					return r.blob()
				})
				.then(async (blob) => {
					const full = await createImageBitmap(blob)
					const big = Math.max(full.width, full.height)
					if (big <= this.maxSize) return full
					const k = this.maxSize / big
					const small = await createImageBitmap(full, { resizeWidth: Math.round(full.width * k), resizeHeight: Math.round(full.height * k), resizeQuality: 'high' })
					full.close()
					return small
				})
			this.cache.set(key, job)
		}
		return job
	}

	/** fade to the picture of a day; null fades the layer out */
	show(key: string | null, fadeMs = 700) {
		if (key === this.wanted && (key === null || this.front?.key === key || this.pending?.key === key)) return
		this.wanted = key
		this.fadeMs = fadeMs
		if (key === null) {
			this.fadeTo(0, fadeMs)
			return
		}
		this.fadeTo(1, fadeMs)
		if (this.front?.key === key) return
		const job = this.preload(key)
		if (!job) return
		job.then((bitmap) => {
			if (this.gone || this.wanted !== key) return
			this.pending = { key, bitmap }
			this.cache.delete(key) // the bitmap is consumed by the upload; a later show fetches from the browser cache
			this.map?.triggerRepaint()
		}).catch((err) => console.error('picture failed to load', err))
	}

	private fadeTo(to: number, ms: number) {
		if (to === this.opacityTo) return
		this.opacityFrom = this.opacity
		this.opacityTo = to
		this.opacityStart = performance.now()
		this.fadeMs = ms
		this.map?.triggerRepaint()
	}

	/** saturation and brightness of every picture, 1 is the picture as it is */
	setTone(sat: number, bright: number) {
		this.sat = sat
		this.bright = bright
		this.map?.triggerRepaint()
	}

	/** how far one picture steps back while radar water sits on it (a sky full of cloud steps back more) */
	setDim(key: string, sat: number, bright: number) {
		this.dim.set(key, [sat, bright])
	}

	/** switch the stepping back on or off; each picture keeps its own, so a fade never flashes */
	setDimmed(on: boolean) {
		this.dimmed = on
		this.map?.triggerRepaint()
	}

	setClip(x0: number, x1: number) {
		this.clip = [x0, x1]
		this.map?.triggerRepaint()
	}

	/** an extra multiplier on the whole layer, used to let it go when the map is seen from far out */
	setAlpha(alpha: number) {
		this.alpha = alpha
		this.map?.triggerRepaint()
	}

	/** the day on screen */
	current() {
		return this.front?.key ?? null
	}

	private render(gl: WebGL2RenderingContext, input: CustomRenderMethodInput) {
		const now = performance.now()
		if (this.pending) {
			const { key, bitmap } = this.pending
			this.pending = null
			const tex = gl.createTexture()!
			gl.activeTexture(gl.TEXTURE0)
			gl.bindTexture(gl.TEXTURE_2D, tex)
			gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false)
			gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
			gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, bitmap)
			gl.generateMipmap(gl.TEXTURE_2D)
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
			gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
			bitmap.close()
			if (this.back) gl.deleteTexture(this.back.tex)
			this.back = this.front
			this.front = { key, tex }
			this.fadeStart = now
			this.onShow?.(key)
		}
		if (!this.program || !this.front) return

		const k = Math.min(1, (now - this.opacityStart) / Math.max(1, this.fadeMs))
		this.opacity = this.opacityFrom + (this.opacityTo - this.opacityFrom) * k
		const mixIn = this.back ? Math.min(1, (now - this.fadeStart) / Math.max(1, this.fadeMs)) : 1
		if (mixIn >= 1 && this.back) {
			gl.deleteTexture(this.back.tex)
			this.back = null
		}
		const shown = this.opacity * this.alpha
		if (shown <= 0.001) return

		const mat = quadMatrix(input.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>, this.bounds)
		gl.useProgram(this.program)
		gl.uniformMatrix4fv(this.u.u_matrix, false, mat)
		gl.uniform1i(this.u.u_tex, 0)
		const tone = (key: string) => {
			const d = this.dimmed ? this.dim.get(key) : undefined
			gl.uniform1f(this.u.u_sat, this.sat * (d ? d[0] : 1))
			gl.uniform1f(this.u.u_bright, this.bright * (d ? d[1] : 1))
		}
		gl.enable(gl.BLEND)
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
		gl.bindVertexArray(this.vao)
		gl.activeTexture(gl.TEXTURE0)
		const ease = (x: number) => x * x * (3 - 2 * x)
		withClip(gl, this.clip, () => {
			if (this.back) {
				gl.bindTexture(gl.TEXTURE_2D, this.back.tex)
				tone(this.back.key)
				gl.uniform1f(this.u.u_alpha, shown)
				gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
			}
			gl.bindTexture(gl.TEXTURE_2D, this.front!.tex)
			tone(this.front!.key)
			gl.uniform1f(this.u.u_alpha, shown * ease(mixIn))
			gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
		})
		gl.bindVertexArray(null)
		if (mixIn < 1 || k < 1) this.map?.triggerRepaint()
	}
}
