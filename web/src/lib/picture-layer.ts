// Real satellite pictures of one place on chosen days, drawn as a MapLibre custom layer so the app can fade from
// one day to the next, dim them under the radar layer and cut them along a swipe line.
// The pictures are Sentinel-2 true colour, untouched (scripts/fetch_optical.py). A cloudy day stays cloudy.
// With 3D terrain on, the layer is drawn into the terrain tiles instead (renderToTerrainTile), so the picture lies
// on the relief; the swipe line belongs to the screen and only works on the flat map.
//
// A picture costs a while to decode and to put on the graphics card, so the layer keeps the last few on the card
// and can fetch the next one ahead of time (`preload`): changing the day is then only a fade.
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MapLibreMap } from 'maplibre-gl'
import { type Bounds, type LazyProgram, QUAD_VERT, TERRAIN_REDRAW_MS, TILE_VERT, quadMatrix, startProgram, tileRect, unitQuad, withClip } from './gl-quad'

const FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_tex;
uniform float u_alpha;
uniform float u_sat;
uniform float u_bright;
uniform float u_feather;
void main() {
	vec3 c = texture(u_tex, v_uv).rgb;
	float l = dot(c, vec3(0.299, 0.587, 0.114));
	vec3 rgb = mix(vec3(l), c, u_sat) * u_bright;
	// the picture melts into the base map at its edges instead of ending in a hard rectangle
	float rim = min(min(v_uv.x, 1.0 - v_uv.x), min(v_uv.y, 1.0 - v_uv.y));
	float a = u_alpha * smoothstep(0.0, u_feather, rim);
	fragColor = vec4(rgb * a, a);
}`

const UNIFORMS = ['u_matrix', 'u_rect', 'u_clip', 'u_tex', 'u_alpha', 'u_sat', 'u_bright', 'u_feather']
/** pictures kept on the card: every clear picture of a story (the rice season has six), so a replay loads nothing */
const KEEP = 6
/** a picture fetched ahead of time goes on the card only while the camera is still, and this long after the last */
const IDLE_UPLOAD_MS = 250

type Prog = { lazy: LazyProgram; u: Record<string, WebGLUniformLocation | null> | null }
type TerrainTile = Parameters<NonNullable<CustomLayerInterface['renderToTerrainTile']>>[1]

export class PictureLayer {
	readonly id: string
	readonly layer: CustomLayerInterface
	private bounds: Bounds
	private map: MapLibreMap | null = null
	private gl: WebGL2RenderingContext | null = null
	/** the layer drawn by the camera, and the same layer drawn into one terrain tile; each compiles when first needed */
	private flat: Prog | null = null
	private draped: Prog | null = null
	private compiling: Prog | null = null
	private vao: WebGLVertexArrayObject | null = null
	private buffer: WebGLBuffer | null = null
	private revision = 0
	/** how far the new picture has faded in over the old one, and how visible the layer is, worked out once a frame */
	private mixIn = 1
	private shown = 0
	/** the pictures on the card, by day, and which two are drawn */
	private textures = new Map<string, { tex: WebGLTexture; used: number }>()
	private tick = 0
	private front: string | null = null
	private back: string | null = null
	private fadeStart = 0
	private fadeMs = 700
	/** decoded pictures waiting for the card; `soon` when the screen wants it now */
	private decoded: { key: string; bitmap: ImageBitmap; soon: boolean }[] = []
	private lastIdleUpload = 0
	private wanted: string | null = null
	private urls = new Map<string, string>()
	private jobs = new Map<string, Promise<void>>()
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
	private feather: number
	private maxSize: number
	private gone = false
	/** called when a picture is on screen */
	onShow: ((key: string) => void) | null = null

	/** `feather` is how far in from its edges the picture melts into the base map, as a share of its size. A tilted
	 *  view shows the whole rectangle of the picture, and wants more of it than the plan view (0.05). `maxSize` is
	 *  the longest side a picture is decoded at. */
	constructor(opts: { id: string; bounds: Bounds; pictures: { key: string; url: string }[]; maxSize?: number; feather?: number }) {
		this.id = opts.id
		this.feather = opts.feather ?? 0.05
		this.bounds = opts.bounds
		this.maxSize = opts.maxSize ?? 4096
		for (const p of opts.pictures) this.urls.set(p.key, p.url)
		this.layer = {
			id: this.id,
			type: 'custom',
			renderingMode: '2d',
			onAdd: (map, gl) => {
				this.map = map
				this.gl = gl
				// the terrain is on by default: its program first, the flat one only when the map is flat
				this.draped = { lazy: startProgram(gl, TILE_VERT, FRAG), u: null }
				const q = unitQuad(gl)
				this.vao = q.vao
				this.buffer = q.buffer
				if (this.wanted) this.show(this.wanted)
			},
			onRemove: (_map, gl) => {
				this.gone = true
				window.clearTimeout(this.redrawTimer)
				for (const t of this.textures.values()) gl.deleteTexture(t.tex)
				this.textures.clear()
				for (const p of [this.flat, this.draped]) if (p) gl.deleteProgram(p.lazy.program)
				if (this.buffer) gl.deleteBuffer(this.buffer)
				if (this.vao) gl.deleteVertexArray(this.vao)
				for (const d of this.decoded) d.bitmap.close()
				this.decoded = []
				this.map = null
				this.gl = null
			},
			prerender: (gl) => this.prerender(gl),
			render: (gl, input) => this.render(gl, input),
			renderToTerrainTile: (gl, tile) => this.renderTile(gl, tile),
			terrainTileRevision: 0,
		}
	}

	/** Fetch and decode a picture ahead of time; it goes on the card while the map is still. */
	preload(key: string, soon = false) {
		if (this.textures.has(key)) return
		const waiting = this.decoded.find((d) => d.key === key)
		if (waiting) {
			waiting.soon ||= soon
			return
		}
		if (this.jobs.has(key)) {
			if (soon) this.hurry.add(key)
			return
		}
		const url = this.urls.get(key)
		if (!url) return
		if (soon) this.hurry.add(key)
		const job = fetch(url, soon ? undefined : { priority: 'low' })
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
			.then((bitmap) => {
				if (this.gone) return bitmap.close()
				this.decoded.push({ key, bitmap, soon: this.hurry.has(key) || this.wanted === key })
				this.map?.triggerRepaint()
			})
			.catch((err) => console.error('picture failed to load', err))
			.finally(() => {
				this.jobs.delete(key)
				this.hurry.delete(key)
			})
		this.jobs.set(key, job)
	}

	/** pictures asked for by the screen while they were being fetched ahead of time */
	private hurry = new Set<string>()

	/** fade to the picture of a day; null fades the layer out */
	show(key: string | null, fadeMs = 700) {
		if (key === this.wanted && (key === null || this.front === key)) return
		this.wanted = key
		this.fadeMs = fadeMs
		if (key === null) {
			this.fadeTo(0, fadeMs)
			return
		}
		this.fadeTo(1, fadeMs)
		if (this.front === key) return
		if (this.textures.has(key)) this.bringIn(key)
		else this.preload(key, true)
	}

	/** the picture of `key` is on the card: fade from the one on screen to it */
	private bringIn(key: string) {
		if (this.front === key) return
		this.back = this.front
		this.front = key
		this.fadeStart = performance.now()
		this.onShow?.(key)
		this.touch()
	}

	private fadeTo(to: number, ms: number) {
		if (to === this.opacityTo) return
		this.opacityFrom = this.opacity
		this.opacityTo = to
		this.opacityStart = performance.now()
		this.fadeMs = ms
		this.touch()
	}

	/** What the layer draws has changed. Draped over terrain the tiles are kept as textures, and MapLibre only
	 *  draws them again when this number moves, at most TERRAIN_REDRAW_MS apart (gl-quad.ts). */
	private touch() {
		if (this.redrawQueued || this.gone) return
		const wait = TERRAIN_REDRAW_MS - (performance.now() - this.lastRedraw)
		if (wait > 0) {
			// too soon after the last one: one redraw when it is time, and no frames drawn for nothing until then
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

	/** saturation and brightness of every picture, 1 is the picture as it is */
	setTone(sat: number, bright: number) {
		this.sat = sat
		this.bright = bright
		this.touch()
	}

	/** how far one picture steps back while radar water sits on it (a sky full of cloud steps back more) */
	setDim(key: string, sat: number, bright: number) {
		this.dim.set(key, [sat, bright])
	}

	/** switch the stepping back on or off; each picture keeps its own, so a fade never flashes */
	setDimmed(on: boolean) {
		this.dimmed = on
		this.touch()
	}

	setClip(x0: number, x1: number) {
		this.clip = [x0, x1]
		this.touch()
	}

	/** an extra multiplier on the whole layer, used to let it go when the map is seen from far out */
	setAlpha(alpha: number) {
		if (alpha === this.alpha) return
		this.alpha = alpha
		this.touch()
	}

	/** how far in from its edges the picture melts into the base map (see the constructor) */
	setFeather(feather: number) {
		this.feather = feather
		this.touch()
	}

	/** the day on screen */
	current() {
		return this.front
	}

	/** Put one decoded picture on the card: the one the screen wants at once, one fetched ahead of time only while
	 *  the camera is still. A full picture is several megabytes of upload, so never more than one a frame. */
	private upload(gl: WebGL2RenderingContext) {
		let i = this.decoded.findIndex((d) => d.soon || d.key === this.wanted)
		if (i < 0 && this.decoded.length && performance.now() - this.lastIdleUpload > IDLE_UPLOAD_MS && !this.map?.isMoving()) {
			i = 0
			this.lastIdleUpload = performance.now()
		}
		if (i < 0) {
			if (this.decoded.length) this.map?.triggerRepaint()
			return
		}
		const { key, bitmap } = this.decoded.splice(i, 1)[0]
		const tex = gl.createTexture()!
		gl.activeTexture(gl.TEXTURE0)
		gl.bindTexture(gl.TEXTURE_2D, tex)
		gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false)
		gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
		gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bitmap)
		gl.generateMipmap(gl.TEXTURE_2D)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
		gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
		bitmap.close()
		this.textures.set(key, { tex, used: ++this.tick })
		// keep the card light: let go of the picture drawn longest ago, never one on screen or wanted
		if (this.textures.size > KEEP) {
			const keep = new Set([this.front, this.back, this.wanted])
			const old = [...this.textures.entries()].filter(([k]) => !keep.has(k)).sort((x, y) => x[1].used - y[1].used)[0]
			if (old) {
				gl.deleteTexture(old[1].tex)
				this.textures.delete(old[0])
			}
		}
		if (key === this.wanted) this.bringIn(key)
	}

	/** Runs once a frame on both paths, before anything is drawn: a decoded picture goes on the card here, the
	 *  fades move on, and a fade that is still running asks for the next frame. */
	private prerender(gl: WebGL2RenderingContext) {
		const now = performance.now()
		this.upload(gl)
		if (this.compiling) {
			if (this.compiling.lazy.ready()) {
				this.compiling = null
				this.touch()
			} else this.map?.triggerRepaint()
		}
		const k = Math.min(1, (now - this.opacityStart) / Math.max(1, this.fadeMs))
		this.opacity = this.opacityFrom + (this.opacityTo - this.opacityFrom) * k
		this.mixIn = this.back ? Math.min(1, (now - this.fadeStart) / Math.max(1, this.fadeMs)) : 1
		if (this.mixIn >= 1) this.back = null
		this.shown = this.opacity * this.alpha
		if (this.mixIn < 1 || k < 1) this.touch()
		const f = this.front && this.textures.get(this.front)
		if (f) f.used = ++this.tick
	}

	/** a program that can draw now, or null while it compiles (the layer then draws again once it is done) */
	private use(p: Prog | null): Prog | null {
		if (!p || !this.gl || !p.lazy.ready()) {
			if (p) this.compiling = p
			return null
		}
		if (!p.u) {
			const u: NonNullable<Prog['u']> = {}
			for (const n of UNIFORMS) u[n] = this.gl.getUniformLocation(p.lazy.program, n)
			p.u = u
		}
		return p
	}

	/** the old picture, then the new one over it as far as it has faded in */
	private draw(gl: WebGL2RenderingContext, p: Prog, clipped: boolean) {
		const u = p.u!
		const front = this.front ? this.textures.get(this.front) : undefined
		if (!front) return
		const back = this.back ? this.textures.get(this.back) : undefined
		gl.uniform1i(u.u_tex, 0)
		gl.uniform1f(u.u_feather, Math.max(0.001, this.feather))
		const tone = (key: string) => {
			const d = this.dimmed ? this.dim.get(key) : undefined
			gl.uniform1f(u.u_sat, this.sat * (d ? d[0] : 1))
			gl.uniform1f(u.u_bright, this.bright * (d ? d[1] : 1))
		}
		gl.enable(gl.BLEND)
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
		gl.bindVertexArray(this.vao)
		gl.activeTexture(gl.TEXTURE0)
		const ease = (x: number) => x * x * (3 - 2 * x)
		const both = () => {
			if (back && this.back) {
				gl.bindTexture(gl.TEXTURE_2D, back.tex)
				tone(this.back)
				gl.uniform1f(u.u_alpha, this.shown)
				gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
			}
			gl.bindTexture(gl.TEXTURE_2D, front.tex)
			tone(this.front!)
			gl.uniform1f(u.u_alpha, this.shown * (back ? ease(this.mixIn) : 1))
			gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
		}
		if (clipped) withClip(gl, this.clip, both)
		else both()
		gl.bindVertexArray(null)
	}

	/** the flat map: one rectangle through the camera of the map */
	private render(gl: WebGL2RenderingContext, input: CustomRenderMethodInput) {
		// a Mercator matrix: on the globe (far out, without terrain) the layer waits until the globe has turned flat
		if (input.shaderData.variantName !== 'mercator') return
		if (!this.front || this.shown <= 0.001) return
		this.flat ??= { lazy: startProgram(gl, QUAD_VERT, FRAG), u: null }
		const p = this.use(this.flat)
		if (!p) return
		gl.useProgram(p.lazy.program)
		gl.uniformMatrix4fv(p.u!.u_matrix, false, quadMatrix(input.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>, this.bounds))
		this.draw(gl, p, true)
	}

	/** 3D terrain: the part of one terrain tile that the picture covers */
	private renderTile(gl: WebGL2RenderingContext, tile: TerrainTile) {
		const at = tileRect(this.bounds, tile.tileID)
		if (!at || !this.front || this.shown <= 0.001) return
		const p = this.use(this.draped)
		if (!p) return
		gl.useProgram(p.lazy.program)
		gl.uniform4fv(p.u!.u_rect, at.rect)
		gl.uniform4fv(p.u!.u_clip, at.clip)
		gl.disable(gl.CULL_FACE)
		this.draw(gl, p, false)
	}
}
