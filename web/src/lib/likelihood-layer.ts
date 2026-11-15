// The model's map of where the water would go, drawn by the graphics card from the baked prediction frames
// (scripts/bake_prediction.py). Two frames are bound at a time and mixed, so moving the rain from one scenario to
// the next is a crossfade of the likelihood itself: the dashed line of likely water travels across the ground.
//
// Like the water layer this is a MapLibre custom layer with a flat path and a path into the terrain tiles
// (renderToTerrainTile); the fragment shader is shared (likelihood-shader.ts). Every change goes through the same
// redraw throttle as the other layers over the terrain (TERRAIN_REDRAW_MS in gl-quad.ts).
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MapLibreMap } from 'maplibre-gl'
import { type Bounds, type LazyProgram, QUAD_VERT, TERRAIN_REDRAW_MS, TILE_VERT, quadMatrix, startProgram, tileRect, unitQuad } from './gl-quad'
import { LIKELIHOOD_FRAG } from './likelihood-shader'

export type LikelihoodStyle = {
	low: [number, number, number]
	high: [number, number, number]
	old: [number, number, number]
	line: [number, number, number]
	/** mip bias: about 0.85 rounds the corners of the 19 m pixels by less than a pixel, 0 draws them exactly */
	soft: number
}

export const LIKELIHOOD_STYLE: LikelihoodStyle = {
	low: [0.55, 0.9, 1.0],
	high: [0.07, 0.5, 1.0],
	old: [0.05, 0.17, 0.36],
	line: [0.95, 0.99, 1.0],
	soft: 0.85,
}

const UNIFORMS = ['u_matrix', 'u_rect', 'u_clip', 'u_a', 'u_b', 'u_mix', 'u_size', 'u_opacity', 'u_thr', 'u_soft', 'u_cLow', 'u_cHigh', 'u_cOld', 'u_cLine']
/** frames kept on the card: the rain scenarios of a site and one more; each is about 25 MB with its mipmaps */
const MAX_TEXTURES = 5
const IDLE_UPLOAD_MS = 140

type Prog = { lazy: LazyProgram; u: Record<string, WebGLUniformLocation | null> | null }
type TerrainTile = Parameters<NonNullable<CustomLayerInterface['renderToTerrainTile']>>[1]

export class LikelihoodLayer {
	readonly id: string
	readonly layer: CustomLayerInterface
	style: LikelihoodStyle
	private map: MapLibreMap | null = null
	private gl: WebGL2RenderingContext | null = null
	private flat: Prog | null = null
	private draped: Prog | null = null
	private compiling: Prog | null = null
	private vao: WebGLVertexArrayObject | null = null
	private buffer: WebGLBuffer | null = null
	private revision = 0
	private slots = new Map<string, { tex: WebGLTexture; used: number }>()
	private loading = new Set<string>()
	private pending: { key: string; bitmap: ImageBitmap; soon: boolean }[] = []
	private lastIdleUpload = 0
	private tick = 0
	private gone = false
	private drawn = false
	private urls: Map<string, string>
	private bounds: Bounds
	private size: [number, number]
	private a = ''
	private b = ''
	private k = 0
	private thr = 0.31
	/** the opacity on screen, and the fade towards `target` */
	private opacity = 0
	private from = 0
	private target = 0
	private fadeAt = 0
	private fadeMs = 600
	/** an extra factor on the whole layer: the page lets it go when the map is seen from far out */
	private alpha = 1
	/** called each time a frame lands on the card */
	onFrame: (() => void) | null = null

	constructor(opts: { id: string; frames: { key: string; url: string }[]; bounds: Bounds; size: [number, number]; style?: Partial<LikelihoodStyle> }) {
		this.id = opts.id
		this.urls = new Map(opts.frames.map((f) => [f.key, f.url]))
		this.bounds = opts.bounds
		this.size = opts.size
		this.style = { ...LIKELIHOOD_STYLE, ...opts.style }
		this.layer = {
			id: this.id,
			type: 'custom',
			renderingMode: '2d',
			onAdd: (map, gl) => this.onAdd(map, gl),
			onRemove: () => this.onRemove(),
			prerender: (gl) => this.prerender(gl),
			render: (gl, input) => this.render(gl, input),
			renderToTerrainTile: (gl, tile) => this.renderTile(gl, tile),
			terrainTileRevision: 0,
		}
	}

	/** which two frames to draw and how far from the first to the second; `thr` is the line of likely water, 0 to 1 */
	set(a: string, b: string, k: number, thr: number) {
		if (a === this.a && b === this.b && k === this.k && thr === this.thr) return
		this.a = a
		this.b = b
		this.k = Math.min(1, Math.max(0, k))
		this.thr = thr
		this.load(a, true)
		this.load(b, true)
		this.touch()
	}

	/** fetch frames ahead of time; they go on the card while the camera is still */
	preload(keys: string[]) {
		for (const key of keys) this.load(key, false)
	}

	/** fade the whole layer in or out */
	fadeTo(to: number, ms = 600) {
		if (to === this.target) return
		this.from = this.opacity
		this.target = to
		this.fadeAt = performance.now()
		this.fadeMs = ms
		this.touch()
	}

	setAlpha(alpha: number) {
		if (alpha === this.alpha) return
		this.alpha = alpha
		this.touch()
	}

	setStyle(style: Partial<LikelihoodStyle>) {
		this.style = { ...this.style, ...style }
		this.touch()
	}

	/** both frames of the moment are on the card and the layer has drawn once */
	ready() {
		return this.drawn && this.slots.has(this.a) && this.slots.has(this.b)
	}

	/** the layer is drawn at all */
	visible() {
		return this.target > 0 || this.opacity > 0.001
	}

	private touch() {
		if (this.redrawQueued || this.gone) return
		const wait = TERRAIN_REDRAW_MS - (performance.now() - this.lastRedraw)
		if (wait > 0) {
			this.redrawQueued = true
			this.redrawTimer = window.setTimeout(() => {
				this.redrawQueued = false
				this.touch()
			}, wait)
			return
		}
		this.lastRedraw = performance.now()
		this.layer.terrainTileRevision = ++this.revision
		this.map?.triggerRepaint()
	}

	private lastRedraw = -1e9
	private redrawQueued = false
	private redrawTimer = 0
	private urgent = new Set<string>()

	private load(key: string, soon: boolean) {
		const url = this.urls.get(key)
		if (!url || this.gone || this.slots.has(key)) return
		const waiting = this.pending.find((p) => p.key === key)
		if (waiting) {
			if (soon) waiting.soon = true
			return
		}
		if (this.loading.has(key)) {
			if (soon) this.urgent.add(key)
			return
		}
		this.loading.add(key)
		if (soon) this.urgent.add(key)
		fetch(url, soon ? undefined : { priority: 'low' })
			.then((r) => {
				if (!r.ok) throw new Error(`${url}: ${r.status}`)
				return r.blob()
			})
			// the bytes are numbers, not colours
			.then((blob) => createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' }))
			.then((bitmap) => {
				if (this.gone) return bitmap.close()
				this.pending.push({ key, bitmap, soon: this.urgent.has(key) || key === this.a || key === this.b })
				this.map?.triggerRepaint()
			})
			.catch((err) => console.error('prediction frame failed to load', err))
			.finally(() => {
				this.loading.delete(key)
				this.urgent.delete(key)
			})
	}

	private onAdd(map: MapLibreMap, gl: WebGL2RenderingContext) {
		this.map = map
		this.gl = gl
		this.draped = { lazy: startProgram(gl, TILE_VERT, LIKELIHOOD_FRAG), u: null }
		const quad = unitQuad(gl)
		this.vao = quad.vao
		this.buffer = quad.buffer
		if (this.a) this.load(this.a, true)
		if (this.b) this.load(this.b, true)
	}

	private onRemove() {
		this.gone = true
		window.clearTimeout(this.redrawTimer)
		const gl = this.gl
		if (gl) {
			for (const s of this.slots.values()) gl.deleteTexture(s.tex)
			for (const p of [this.flat, this.draped]) if (p) gl.deleteProgram(p.lazy.program)
			if (this.buffer) gl.deleteBuffer(this.buffer)
			if (this.vao) gl.deleteVertexArray(this.vao)
		}
		for (const p of this.pending) p.bitmap.close()
		this.pending = []
		this.slots.clear()
		this.map = null
		this.gl = null
	}

	private use(p: Prog | null): Prog | null {
		if (!p || !this.gl) return null
		if (!p.lazy.ready()) {
			this.compiling = p
			return null
		}
		if (!p.u) {
			const u: NonNullable<Prog['u']> = {}
			for (const name of UNIFORMS) u[name] = this.gl.getUniformLocation(p.lazy.program, name)
			p.u = u
		}
		return p
	}

	/** frames the screen wants go up at once; one fetched ahead of time only while the camera is still */
	private upload(gl: WebGL2RenderingContext) {
		let i = this.pending.findIndex((p) => p.soon || p.key === this.a || p.key === this.b)
		if (i < 0 && this.pending.length && performance.now() - this.lastIdleUpload > IDLE_UPLOAD_MS && !this.map?.isMoving()) {
			i = 0
			this.lastIdleUpload = performance.now()
		}
		if (i < 0) {
			if (this.pending.length) this.map?.triggerRepaint()
			return
		}
		const job = this.pending.splice(i, 1)[0]
		const tex = gl.createTexture()!
		gl.activeTexture(gl.TEXTURE0)
		gl.bindTexture(gl.TEXTURE_2D, tex)
		gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false)
		gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
		gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE)
		gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, job.bitmap)
		gl.generateMipmap(gl.TEXTURE_2D)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
		job.bitmap.close()
		this.slots.set(job.key, { tex, used: ++this.tick })
		if (this.slots.size > MAX_TEXTURES) {
			const keep = new Set([this.a, this.b])
			const old = [...this.slots.entries()].filter(([k]) => !keep.has(k)).sort((x, y) => x[1].used - y[1].used)[0]
			if (old) {
				gl.deleteTexture(old[1].tex)
				this.slots.delete(old[0])
			}
		}
		this.touch()
		this.onFrame?.()
	}

	private prerender(gl: WebGL2RenderingContext) {
		this.upload(gl)
		if (this.compiling) {
			if (this.compiling.lazy.ready()) {
				this.compiling = null
				this.touch()
			} else this.map?.triggerRepaint()
		}
		const t = Math.min(1, (performance.now() - this.fadeAt) / Math.max(1, this.fadeMs))
		const e = t * t * (3 - 2 * t)
		this.opacity = this.from + (this.target - this.from) * e
		if (t < 1) this.touch()
	}

	private begin(gl: WebGL2RenderingContext, p: Prog) {
		const A = this.slots.get(this.a)
		const B = this.slots.get(this.b) ?? A
		if (!A || !B) return false
		A.used = B.used = ++this.tick
		const shown = this.opacity * this.alpha
		if (shown <= 0.001) return false
		const u = p.u!
		const s = this.style
		gl.useProgram(p.lazy.program)
		gl.activeTexture(gl.TEXTURE0)
		gl.bindTexture(gl.TEXTURE_2D, A.tex)
		gl.uniform1i(u.u_a, 0)
		gl.activeTexture(gl.TEXTURE1)
		gl.bindTexture(gl.TEXTURE_2D, B.tex)
		gl.uniform1i(u.u_b, 1)
		gl.uniform1f(u.u_mix, this.slots.has(this.b) ? this.k : 0)
		gl.uniform2f(u.u_size, this.size[0], this.size[1])
		gl.uniform1f(u.u_opacity, shown)
		gl.uniform1f(u.u_thr, this.thr)
		gl.uniform1f(u.u_soft, s.soft)
		gl.uniform3fv(u.u_cLow, s.low)
		gl.uniform3fv(u.u_cHigh, s.high)
		gl.uniform3fv(u.u_cOld, s.old)
		gl.uniform3fv(u.u_cLine, s.line)
		gl.enable(gl.BLEND)
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
		gl.bindVertexArray(this.vao)
		if (!this.drawn) {
			this.drawn = true
			this.onFrame?.()
		}
		return true
	}

	private render(gl: WebGL2RenderingContext, input: CustomRenderMethodInput) {
		if (input.shaderData.variantName !== 'mercator') return
		if (this.opacity * this.alpha <= 0.001 && this.target <= 0) return
		this.flat ??= { lazy: startProgram(gl, QUAD_VERT, LIKELIHOOD_FRAG), u: null }
		const p = this.use(this.flat)
		if (!p) {
			this.map?.triggerRepaint()
			return
		}
		if (!this.begin(gl, p)) return
		gl.uniformMatrix4fv(p.u!.u_matrix, false, quadMatrix(input.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>, this.bounds))
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
		gl.bindVertexArray(null)
	}

	private renderTile(gl: WebGL2RenderingContext, tile: TerrainTile) {
		if (this.opacity * this.alpha <= 0.001 && this.target <= 0) return
		const at = tileRect(this.bounds, tile.tileID)
		if (!at) return
		const p = this.use(this.draped)
		if (!p) return
		if (!this.begin(gl, p)) return
		gl.uniform4fv(p.u!.u_rect, at.rect)
		gl.uniform4fv(p.u!.u_clip, at.clip)
		gl.disable(gl.CULL_FACE)
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
		gl.bindVertexArray(null)
	}
}
