// The moving water, drawn on the map by the graphics card from the baked radar frames (scripts/bake_water.py).
//
// Each frame holds, for one radar pass, the signed distance from every pixel to the nearest shoreline (negative in
// water). To show a moment between two passes the shader mixes the two distance fields and draws water where the mix
// is below zero, so a shoreline travels across the ground instead of one picture fading into the next. At a pass the
// mix is that pass alone, so the picture is exactly the map of that pass. Between passes it is an interpolation, and
// the layer draws it differently on purpose (dashed shoreline, hatched fill) so nobody takes it for a measurement.
//
// Wetting and drying run on two clocks (gain, loss). In an ordinary gap they run together. Across a storm the
// water rises first and falls after, so the page runs the gain clock with the rain and the loss clock afterwards.
//
// With 3D terrain on, MapLibre does not call render: it asks the layer to draw into each terrain tile
// (renderToTerrainTile) and lays those tiles over the ground, so the water follows the relief like the base map.
// The fragment shader is the same on both paths: it only knows its place on the baked grid.
//
// No framework in here: it is a MapLibre custom layer and can be used from any page.
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MapLibreMap } from 'maplibre-gl'
import { type LazyProgram, QUAD_VERT, TERRAIN_REDRAW_MS, TILE_VERT, quadMatrix, startProgram, tileRect, unitQuad, withClip } from './gl-quad'
import { WATER_FRAG } from './water-shader'

export type WaterFrame = {
	file: string
	time_utc?: string
	date?: string
	platform?: string
	granules: string[]
	open_ha: number
	veg_ha: number
	seen: number
}
/** hectares [open water, flooded vegetation] at evenly spaced steps along the three paths of a gap */
export type WaterGap = { both: [number, number][]; gain: [number, number][]; loss: [number, number][] }
export type WaterSeries = {
	id: string
	sensor: string
	band: string
	product: string
	stack?: string
	frames: WaterFrame[]
	between: WaterGap[]
	/** the water every pass of the series has, as one more frame */
	always?: { file: string; water_ha: number }
}
export type WaterMeta = {
	site: string
	title: string
	width: number
	height: number
	zoom: number
	/** west, south, east, north in degrees */
	bounds: [number, number, number, number]
	pixel_m: number
	encoding: { linear_px: number; range_px: number; reach_px?: number; samples: number }
	base: string
	series: WaterSeries[]
	baked_utc: string
}

export type WaterView = {
	/** frame before the playhead */
	a: number
	/** frame after the playhead */
	b: number
	/** 0 to 1: how far pixels that get wetter have travelled from frame a to frame b */
	gain: number
	/** 0 to 1: the same for pixels that dry */
	loss: number
	/** 1 when the picture is a real pass, 0 when it is an interpolation */
	observed: number
	/** frame the picture is compared with: water that is not in it is drawn as new. -1 for none */
	ref: number
}

export type WaterStyle = {
	open: [number, number, number]
	veg: [number, number, number]
	glow: [number, number, number]
	edge: [number, number, number]
	unseen: [number, number, number]
	opacity: number
	/** 0 radar water, 1 forecast (hatched, never a solid fill) */
	forecast: number
	/** 0 draws the exact radar pixels, about 0.85 rounds their corners by less than a pixel */
	soft: number
	/** how solid the fill is, 1 for water; lower lets the picture under the layer show (a burn scar) */
	fill: number
	/** how strong the shoreline and its halo are, 1 for water; lower for a layer made of many small patches */
	line: number
}

export const WATER_STYLE: WaterStyle = {
	open: [0.07, 0.5, 1.0],
	veg: [0.5, 0.78, 1.0],
	glow: [0.5, 0.88, 1.0],
	edge: [0.94, 0.99, 1.0],
	unseen: [0.72, 0.78, 0.9],
	opacity: 1,
	forecast: 0,
	soft: 0.85,
	fill: 1,
	line: 1,
}

const FRAG = WATER_FRAG

const UNIFORMS = [
	'u_matrix', 'u_rect', 'u_clip', 'u_a', 'u_b', 'u_ref', 'u_base', 'u_size', 'u_gain', 'u_loss', 'u_obs', 'u_time', 'u_flow', 'u_flash', 'u_hasRef',
	'u_opacity', 'u_forecast', 'u_soft', 'u_fill', 'u_line', 'u_reach', 'u_lin', 'u_range', 'u_cOpen', 'u_cVeg', 'u_cGlow', 'u_cEdge', 'u_cUnseen',
]
/** frames kept on the card: every pass of a story, so playing it again loads nothing; a longer series cycles */
const MAX_TEXTURES = 14
const FLASH_MS = 650
/** frames fetched ahead of time go on the card one at a time, this far apart, and not while the camera moves */
const IDLE_UPLOAD_MS = 140

type Slot = { tex: WebGLTexture; used: number }
type Prog = { lazy: LazyProgram; u: Record<string, WebGLUniformLocation | null> | null }
type TerrainTile = Parameters<NonNullable<CustomLayerInterface['renderToTerrainTile']>>[1]

export class WaterLayer {
	readonly id: string
	readonly layer: CustomLayerInterface
	style: WaterStyle
	private map: MapLibreMap | null = null
	private gl: WebGL2RenderingContext | null = null
	/** the layer drawn by the camera, and the same layer drawn into one terrain tile; each compiles when first needed */
	private flat: Prog | null = null
	private draped: Prog | null = null
	private vao: WebGLVertexArrayObject | null = null
	private buffer: WebGLBuffer | null = null
	private revision = 0
	private slots = new Map<string, Slot>()
	private loading = new Set<string>()
	/** decoded frames waiting for the card; `soon` ones are needed for the moment on screen or the next pass */
	private pending: { key: string; bitmap: ImageBitmap; soon: boolean }[] = []
	private lastIdleUpload = 0
	/** appended to every file address, so a new bake is never taken from the browser's cache */
	private version: string
	private view: WaterView = { a: 0, b: 0, gain: 0, loss: 0, observed: 1, ref: -1 }
	private flow = 0
	private flashAt = -1e9
	private clip: [number, number] = [0, 1]
	private tick = 0
	private gone = false
	private frames: WaterFrame[]
	private root: string
	private meta: WaterMeta
	/** called each time a frame lands on the card */
	onFrame: (() => void) | null = null

	constructor(opts: { id: string; root: string; meta: WaterMeta; series: WaterSeries; style?: Partial<WaterStyle> }) {
		this.id = opts.id
		this.root = opts.root.replace(/\/$/, '')
		this.meta = opts.meta
		this.frames = opts.series.frames
		this.style = { ...WATER_STYLE, ...opts.style }
		this.version = `?v=${encodeURIComponent(opts.meta.baked_utc)}`
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

	/** which frames to draw and how far between them the playhead is */
	set(view: Partial<WaterView>) {
		this.view = { ...this.view, ...view }
		this.want(this.view.a)
		this.want(this.view.b)
		if (this.view.ref >= 0) this.want(this.view.ref)
		// the next two passes, so the playhead never reaches a pass that is still on its way
		this.want(this.view.b + 1)
		this.want(this.view.b + 2)
		this.touch()
	}

	/** fetch every pass of the series, without hurry: they go on the card while the map is still */
	preloadAll() {
		for (let i = 0; i < Math.min(this.frames.length, MAX_TEXTURES - 2); i++) this.load(`f${i}`, this.url(this.frames[i].file), false)
	}

	private url(file: string) {
		return `${this.root}/${file}${this.version}`
	}

	/** 0 to 1: how much the ripples run (1 while the series plays) */
	setFlow(flow: number) {
		this.flow = flow
		this.touch()
	}

	/** a short pulse on the shoreline: the playhead has just reached a real pass */
	flash() {
		this.flashAt = performance.now()
		this.touch()
	}

	setStyle(style: Partial<WaterStyle>) {
		this.style = { ...this.style, ...style }
		this.touch()
	}

	/** draw only between these fractions of the width of the map (for the swipe) */
	setClip(x0: number, x1: number) {
		this.clip = [x0, x1]
		this.touch()
	}

	/** Draw again although nothing was set: the light on the water moves with the clock. */
	repaint() {
		this.touch()
	}

	/** What the layer draws has changed. Draped over terrain the tiles are kept as textures, and MapLibre only
	 *  draws them again when this number moves. It draws all of them, at 2048 pixels a side with everything on them,
	 *  so the number moves at most TERRAIN_REDRAW_MS apart: the camera still moves at full speed over the textures. */
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

	/** start loading a frame ahead of the playhead */
	want(index: number) {
		if (index < 0 || index >= this.frames.length) return
		this.load(`f${index}`, this.url(this.frames[index].file), true)
	}

	/** true when every frame of the current view is on the card and the layer has drawn (its program is compiled) */
	ready() {
		const { a, b, ref } = this.view
		return this.drawn && this.slots.has('base') && this.slots.has(`f${a}`) && this.slots.has(`f${b}`) && (ref < 0 || this.slots.has(`f${ref}`))
	}

	/** the layer has drawn at least once: the page shows the map only from then on */
	private drawn = false

	private load(key: string, url: string, soon: boolean) {
		if (this.gone || this.slots.has(key)) return
		// a frame fetched ahead of time that is now needed jumps the queue
		const waiting = this.pending.find((p) => p.key === key)
		if (waiting) {
			if (soon && !waiting.soon) waiting.soon = true
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
			// the bytes are distances, not colours: no colour management, no alpha tricks
			.then((blob) => createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' }))
			.then((bitmap) => {
				if (this.gone) return bitmap.close()
				this.pending.push({ key, bitmap, soon: this.urgent.has(key) })
				this.map?.triggerRepaint()
			})
			.catch((err) => console.error('water frame failed to load', err))
			.finally(() => {
				this.loading.delete(key)
				this.urgent.delete(key)
			})
	}

	/** frames asked for by the moment on screen while they were still being fetched ahead of time */
	private urgent = new Set<string>()

	private onAdd(map: MapLibreMap, gl: WebGL2RenderingContext) {
		this.map = map
		this.gl = gl
		// the terrain is on by default: its program first, the flat one only when the map is flat
		this.draped = { lazy: startProgram(gl, TILE_VERT, FRAG), u: null }
		const quad = unitQuad(gl)
		this.vao = quad.vao
		this.buffer = quad.buffer
		this.load('base', this.url(this.meta.base), true)
		this.set({})
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

	/** a program that can draw now, or null while it compiles (the layer then draws again once it is done) */
	private use(p: Prog | null): Prog | null {
		if (!p || !this.gl) return null
		if (!p.lazy.ready()) return null
		if (!p.u) {
			const u: NonNullable<Prog['u']> = {}
			for (const name of UNIFORMS) u[name] = this.gl.getUniformLocation(p.lazy.program, name)
			p.u = u
		}
		return p
	}

	/** Put decoded frames on the card. Done inside render, where MapLibre expects its GL state to be touched. The
	 *  frames the screen needs go up together, at once: while the map starts a frame of MapLibre can take a tenth of
	 *  a second, and one frame each would hold the first view for several of them. A frame fetched ahead of time
	 *  waits until the camera is still, and goes up alone. */
	private upload(gl: WebGL2RenderingContext) {
		const soon = this.pending.filter((p) => p.soon)
		if (soon.length) {
			for (const job of soon.slice(0, 6)) {
				this.pending.splice(this.pending.indexOf(job), 1)
				this.put(gl, job)
			}
		} else if (this.pending.length && performance.now() - this.lastIdleUpload > IDLE_UPLOAD_MS && !this.map?.isMoving()) {
			this.lastIdleUpload = performance.now()
			this.put(gl, this.pending.shift()!)
		} else {
			if (this.pending.length) this.map?.triggerRepaint()
			return
		}
		this.touch()
		this.onFrame?.()
	}

	/** one decoded frame onto the card */
	private put(gl: WebGL2RenderingContext, job: { key: string; bitmap: ImageBitmap }) {
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
		// keep the card light: drop the frame that was drawn longest ago
		if (this.slots.size > MAX_TEXTURES) {
			const keep = new Set(['base', `f${this.view.a}`, `f${this.view.b}`, `f${this.view.ref}`])
			const old = [...this.slots.entries()].filter(([k]) => !keep.has(k)).sort((x, y) => x[1].used - y[1].used)[0]
			if (old) {
				gl.deleteTexture(old[1].tex)
				this.slots.delete(old[0])
			}
		}
	}

	/** Runs once a frame on both paths, before anything is drawn: frames go on the card here, and a picture that
	 *  moves by itself (ripples, the pulse of a pass) asks for the next frame. */
	private prerender(gl: WebGL2RenderingContext) {
		this.upload(gl)
		// a program still compiling: look again next frame, and draw the layer again once it is done
		if (this.compiling) {
			if (this.compiling.lazy.ready()) {
				this.compiling = null
				this.touch()
			} else this.map?.triggerRepaint()
		}
		if (this.flow > 0.001 || performance.now() - this.flashAt < FLASH_MS) this.touch()
	}

	private compiling: Prog | null = null

	/** Everything the two paths share: the frames, the clocks, the colours. False when there is nothing to draw yet. */
	private begin(gl: WebGL2RenderingContext, p: Prog) {
		const { a, b, ref, gain, loss, observed } = this.view
		const A = this.slots.get(`f${a}`)
		const B = this.slots.get(`f${b}`)
		const base = this.slots.get('base')
		if (!A || !B || !base) return false
		const R = ref >= 0 ? this.slots.get(`f${ref}`) : undefined
		A.used = B.used = ++this.tick
		if (R) R.used = this.tick
		if (this.style.opacity <= 0.001) return false

		const now = performance.now()
		const flash = Math.max(0, 1 - (now - this.flashAt) / FLASH_MS)
		const u = p.u!
		const s = this.style
		gl.useProgram(p.lazy.program)
		const bind = (unit: number, tex: WebGLTexture, loc: WebGLUniformLocation | null) => {
			gl.activeTexture(gl.TEXTURE0 + unit)
			gl.bindTexture(gl.TEXTURE_2D, tex)
			gl.uniform1i(loc, unit)
		}
		bind(0, A.tex, u.u_a)
		bind(1, B.tex, u.u_b)
		bind(2, (R ?? A).tex, u.u_ref)
		bind(3, base.tex, u.u_base)
		gl.uniform2f(u.u_size, this.meta.width, this.meta.height)
		gl.uniform1f(u.u_gain, gain)
		gl.uniform1f(u.u_loss, loss)
		gl.uniform1f(u.u_obs, observed)
		gl.uniform1f(u.u_time, (now / 1000) % 3600)
		gl.uniform1f(u.u_flow, this.flow)
		gl.uniform1f(u.u_flash, flash * flash)
		gl.uniform1f(u.u_hasRef, R ? 1 : 0)
		gl.uniform1f(u.u_opacity, s.opacity)
		gl.uniform1f(u.u_forecast, s.forecast)
		gl.uniform1f(u.u_soft, s.soft)
		gl.uniform1f(u.u_fill, s.fill)
		gl.uniform1f(u.u_line, s.line)
		gl.uniform1f(u.u_reach, this.meta.encoding.reach_px ?? this.meta.encoding.range_px)
		gl.uniform1f(u.u_lin, this.meta.encoding.linear_px)
		gl.uniform1f(u.u_range, this.meta.encoding.range_px)
		gl.uniform3fv(u.u_cOpen, s.open)
		gl.uniform3fv(u.u_cVeg, s.veg)
		gl.uniform3fv(u.u_cGlow, s.glow)
		gl.uniform3fv(u.u_cEdge, s.edge)
		gl.uniform3fv(u.u_cUnseen, s.unseen)

		gl.enable(gl.BLEND)
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
		gl.bindVertexArray(this.vao)
		if (!this.drawn) {
			this.drawn = true
			this.onFrame?.()
		}
		return true
	}

	/** the flat map: one rectangle through the camera of the map */
	private render(gl: WebGL2RenderingContext, input: CustomRenderMethodInput) {
		// the camera matrix below is a Mercator one. On the globe (far out, without terrain) it would put the
		// rectangle in the wrong place, so the layer waits until the globe has turned flat, near zoom 12
		if (input.shaderData.variantName !== 'mercator') return
		this.flat ??= { lazy: startProgram(gl, QUAD_VERT, FRAG), u: null }
		const p = this.use(this.flat)
		if (!p) {
			this.compiling = this.flat
			this.map?.triggerRepaint()
			return
		}
		if (!this.begin(gl, p)) return
		gl.uniformMatrix4fv(p.u!.u_matrix, false, quadMatrix(input.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>, this.meta.bounds))
		withClip(gl, this.clip, () => gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4))
		gl.bindVertexArray(null)
	}

	/** 3D terrain: the part of one terrain tile that the site covers. The swipe line is a line on the screen and
	 *  has no place in a tile, so it does not apply here. */
	private renderTile(gl: WebGL2RenderingContext, tile: TerrainTile) {
		const at = tileRect(this.meta.bounds, tile.tileID)
		if (!at) return
		const p = this.use(this.draped)
		if (!p) {
			this.compiling = this.draped
			return
		}
		if (!this.begin(gl, p)) return
		gl.uniform4fv(p.u!.u_rect, at.rect)
		gl.uniform4fv(p.u!.u_clip, at.clip)
		gl.disable(gl.CULL_FACE)
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
		gl.bindVertexArray(null)
	}
}
