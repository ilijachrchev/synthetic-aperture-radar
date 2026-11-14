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
// No framework in here: it is a MapLibre custom layer and can be used from any page.
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MapLibreMap } from 'maplibre-gl'
import { QUAD_VERT, buildProgram, quadMatrix, unitQuad, withClip } from './gl-quad'

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
	encoding: { linear_px: number; range_px: number; samples: number }
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
}

export const WATER_STYLE: WaterStyle = {
	open: [0.07, 0.5, 1.0],
	veg: [0.16, 0.88, 0.66],
	glow: [0.5, 0.88, 1.0],
	edge: [0.94, 0.99, 1.0],
	unseen: [0.72, 0.78, 0.9],
	opacity: 1,
	forecast: 0,
	soft: 0.85,
}

const FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_a;
uniform sampler2D u_b;
uniform sampler2D u_ref;
uniform sampler2D u_base;
uniform vec2 u_size;
uniform float u_gain;
uniform float u_loss;
uniform float u_obs;
uniform float u_time;
uniform float u_flow;
uniform float u_flash;
uniform float u_hasRef;
uniform float u_opacity;
uniform float u_forecast;
uniform float u_soft;
uniform float u_lin;
uniform float u_range;
uniform vec3 u_cOpen;
uniform vec3 u_cVeg;
uniform vec3 u_cGlow;
uniform vec3 u_cEdge;
uniform vec3 u_cUnseen;

// one byte back to a distance in grid pixels, the inverse of encode() in scripts/bake_water.py
float dist(float v) {
	float c = v * 255.0 - 128.0;
	float a = abs(c);
	float s = a <= 32.0 ? a * (u_lin / 32.0) : u_lin + (u_range - u_lin) * ((a - 32.0) / 95.0) * ((a - 32.0) / 95.0);
	return sign(c) * s;
}

void main() {
	vec3 ta = texture(u_a, v_uv, u_soft).rgb;
	vec3 tb = texture(u_b, v_uv, u_soft).rgb;
	float sea = texture(u_base, v_uv).r;

	float anyA = dist(ta.g);
	float anyB = dist(tb.g);
	float openA = dist(ta.b);
	float openB = dist(tb.b);
	// a pixel on its way into the water follows the gain clock, a pixel on its way out the loss clock
	float sAny = mix(anyA, anyB, anyB < anyA ? u_gain : u_loss);
	float sOpen = mix(openA, openB, openB < openA ? u_gain : u_loss);

	// grid pixels per screen pixel, and the slope of the field with a floor so flat patches stay sane
	float texel = max(length(fwidth(v_uv) * u_size) * 0.7071, 1e-5);
	float gAny = max(fwidth(sAny), texel * 0.35);
	float gOpen = max(fwidth(sOpen), texel * 0.35);
	float px = sAny / gAny; // signed distance to the shoreline in screen pixels, negative in water

	float water = clamp(0.5 - px, 0.0, 1.0);
	float open = clamp(0.5 - sOpen / gOpen, 0.0, 1.0);

	// is this a body of water or a speck? Read the field 8 pixels wide: specks average out, bodies do not
	float wide = mix(dist(textureLod(u_a, v_uv, 3.0).g), dist(textureLod(u_b, v_uv, 3.0).g), 0.5 * (u_gain + u_loss));
	float mass = 1.0 - smoothstep(-0.5, 3.0, wide);

	// against the reference pass: water it did not have is new, and a shoreline it did not have has moved
	float fresh = 0.0;
	float moved = 0.0;
	if (u_hasRef > 0.5) {
		vec3 tr = texture(u_ref, v_uv, u_soft).rgb;
		float refAny = dist(tr.g);
		float refOpen = dist(tr.b);
		float freshAny = clamp(0.5 + refAny / max(fwidth(refAny), texel * 0.35), 0.0, 1.0);
		float freshOpen = clamp(0.5 + refOpen / max(fwidth(refOpen), texel * 0.35), 0.0, 1.0);
		fresh = max(freshAny, open * freshOpen);
		moved = smoothstep(0.75, 3.0, abs(refAny - sAny));
	}

	vec2 fc = gl_FragCoord.xy;
	// only what the two passes disagree on is an estimate: water that both passes have is as sure between them
	float inA = clamp(0.5 - anyA / max(fwidth(anyA), texel * 0.35), 0.0, 1.0);
	float inB = clamp(0.5 - anyB / max(fwidth(anyB), texel * 0.35), 0.0, 1.0);
	float between = (1.0 - u_obs) * (1.0 - inA * inB);
	float shifting = (1.0 - u_obs) * smoothstep(0.5, 2.0, abs(anyB - anyA));

	// fill: open water is a clean wash, flooded vegetation is a lighter wash under fine dots
	vec3 cOpen = mix(u_cOpen * vec3(0.9, 0.82, 0.86), u_cOpen, fresh);
	vec3 cVeg = mix(u_cVeg * 0.74, u_cVeg, fresh);
	vec3 col = mix(cVeg, cOpen, open);
	float depth = clamp(-sAny / 18.0, 0.0, 1.0);
	col *= 1.0 - 0.2 * depth;
	float dots = smoothstep(0.66, 0.36, length(fract(fc / 5.0) - 0.5) * 2.0);
	float aOpen = mix(0.5, 0.8, fresh);
	float aVeg = mix(0.2, 0.36, fresh) + dots * mix(0.36, 0.58, fresh);
	float fill = water * mix(aVeg, aOpen, open);

	// between two passes the fill is hatched: it is an estimate, not a measurement
	float hatch = smoothstep(0.2, 0.34, abs(fract((fc.x + fc.y) / 6.0) - 0.5));
	fill *= mix(1.0, 0.66 + 0.34 * hatch, between);

	// ripples run with the shoreline: outward where water gains ground, inward where it gives it back
	float delta = anyB - anyA;
	float moving = smoothstep(1.0, 9.0, abs(delta)) * u_flow * mass;
	float dir = delta < 0.0 ? 1.0 : -1.0;
	float wave = sin(px * 0.5 - dir * u_time * 4.2);
	float ripple = smoothstep(0.74, 1.0, wave) * smoothstep(-30.0, -3.0, px) * step(px, 0.0) * moving;

	// shoreline: one crisp line, strong on a body of water that moved, faint on specks, dashed on an estimate
	float weight = mix(0.2, 1.0, mass) * mix(0.55, 1.0, moved);
	float dash = smoothstep(0.42, 0.58, abs(fract((fc.x - fc.y) / 11.0) - 0.5) * 2.0);
	float line = clamp(1.55 - abs(px), 0.0, 1.0) * weight * mix(1.0, dash, shifting);
	float halo = exp(-max(px, 0.0) / 7.0) * step(0.0, px) * mass * moved * (0.34 + 0.5 * u_flash);

	// forecast: no solid water, only stripes inside the likely extent and a dashed outline
	float stripes = smoothstep(0.34, 0.46, abs(fract((fc.x + fc.y) / 12.0) - 0.5));
	fill = mix(fill, water * (0.1 + 0.34 * (1.0 - stripes)), u_forecast);
	line = mix(line, clamp(1.55 - abs(px), 0.0, 1.0) * dash, u_forecast);
	// (the forecast outline is always dashed)
	halo *= 1.0 - u_forecast;
	ripple *= 1.0 - u_forecast;

	vec3 rgb = col;
	float alpha = fill;
	rgb = mix(rgb, u_cEdge, clamp(ripple * 0.55, 0.0, 1.0));
	alpha = max(alpha, ripple * 0.5 * water);
	// the halo sits on the land side of the shoreline, the line on top of both
	rgb = mix(rgb, u_cGlow, halo * (1.0 - water));
	alpha = max(alpha, halo * (1.0 - water));
	rgb = mix(rgb, u_cEdge, line);
	alpha = max(alpha, line);

	// ground this pass did not see: thin grey hatching, only while the picture is a pass
	float seen = mix(ta.r, tb.r, step(0.5, 0.5 * (u_gain + u_loss)));
	float miss = (1.0 - smoothstep(0.35, 0.65, seen)) * u_obs * (1.0 - u_forecast);
	float missHatch = 1.0 - smoothstep(0.06, 0.12, abs(fract((fc.x + fc.y) / 9.0) - 0.5));
	float missA = miss * missHatch * 0.3;
	rgb = mix(rgb, u_cUnseen, missA * (1.0 - alpha));
	alpha = max(alpha, missA);

	alpha *= (1.0 - smoothstep(0.35, 0.65, sea)) * u_opacity;
	fragColor = vec4(rgb * alpha, alpha);
}`

const UNIFORMS = [
	'u_matrix', 'u_a', 'u_b', 'u_ref', 'u_base', 'u_size', 'u_gain', 'u_loss', 'u_obs', 'u_time', 'u_flow', 'u_flash', 'u_hasRef',
	'u_opacity', 'u_forecast', 'u_soft', 'u_lin', 'u_range', 'u_cOpen', 'u_cVeg', 'u_cGlow', 'u_cEdge', 'u_cUnseen',
]
const MAX_TEXTURES = 8
const FLASH_MS = 650

type Slot = { tex: WebGLTexture; used: number }

export class WaterLayer {
	readonly id: string
	readonly layer: CustomLayerInterface
	style: WaterStyle
	private map: MapLibreMap | null = null
	private gl: WebGL2RenderingContext | null = null
	private program: WebGLProgram | null = null
	private vao: WebGLVertexArrayObject | null = null
	private buffer: WebGLBuffer | null = null
	private uniforms: Record<string, WebGLUniformLocation | null> = {}
	private slots = new Map<string, Slot>()
	private loading = new Set<string>()
	private pending: { key: string; bitmap: ImageBitmap }[] = []
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
		this.layer = {
			id: this.id,
			type: 'custom',
			renderingMode: '2d',
			onAdd: (map, gl) => this.onAdd(map, gl),
			onRemove: () => this.onRemove(),
			render: (gl, input) => this.render(gl, input),
		}
	}

	/** which frames to draw and how far between them the playhead is */
	set(view: Partial<WaterView>) {
		this.view = { ...this.view, ...view }
		this.want(this.view.a)
		this.want(this.view.b)
		if (this.view.ref >= 0) this.want(this.view.ref)
		this.map?.triggerRepaint()
	}

	/** 0 to 1: how much the ripples run (1 while the series plays) */
	setFlow(flow: number) {
		this.flow = flow
		this.map?.triggerRepaint()
	}

	/** a short pulse on the shoreline: the playhead has just reached a real pass */
	flash() {
		this.flashAt = performance.now()
		this.map?.triggerRepaint()
	}

	setStyle(style: Partial<WaterStyle>) {
		this.style = { ...this.style, ...style }
		this.map?.triggerRepaint()
	}

	/** draw only between these fractions of the width of the map (for the swipe) */
	setClip(x0: number, x1: number) {
		this.clip = [x0, x1]
		this.map?.triggerRepaint()
	}

	/** start loading a frame ahead of the playhead */
	want(index: number) {
		if (index < 0 || index >= this.frames.length) return
		this.load(`f${index}`, `${this.root}/${this.frames[index].file}`)
	}

	/** true when every frame of the current view is ready to draw */
	ready() {
		const { a, b, ref } = this.view
		return this.slots.has('base') && this.slots.has(`f${a}`) && this.slots.has(`f${b}`) && (ref < 0 || this.slots.has(`f${ref}`))
	}

	private load(key: string, url: string) {
		if (this.gone || this.slots.has(key) || this.loading.has(key) || this.pending.some((p) => p.key === key)) return
		this.loading.add(key)
		fetch(url)
			.then((r) => {
				if (!r.ok) throw new Error(`${url}: ${r.status}`)
				return r.blob()
			})
			// the bytes are distances, not colours: no colour management, no alpha tricks
			.then((blob) => createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' }))
			.then((bitmap) => {
				if (this.gone) return bitmap.close()
				this.pending.push({ key, bitmap })
				this.map?.triggerRepaint()
			})
			.catch((err) => console.error('water frame failed to load', err))
			.finally(() => this.loading.delete(key))
	}

	private onAdd(map: MapLibreMap, gl: WebGL2RenderingContext) {
		this.map = map
		this.gl = gl
		const program = buildProgram(gl, QUAD_VERT, FRAG)
		this.program = program
		for (const name of UNIFORMS) this.uniforms[name] = gl.getUniformLocation(program, name)
		const quad = unitQuad(gl, program)
		this.vao = quad.vao
		this.buffer = quad.buffer
		this.load('base', `${this.root}/${this.meta.base}`)
		this.set({})
	}

	private onRemove() {
		this.gone = true
		const gl = this.gl
		if (gl) {
			for (const s of this.slots.values()) gl.deleteTexture(s.tex)
			if (this.program) gl.deleteProgram(this.program)
			if (this.buffer) gl.deleteBuffer(this.buffer)
			if (this.vao) gl.deleteVertexArray(this.vao)
		}
		for (const p of this.pending) p.bitmap.close()
		this.pending = []
		this.slots.clear()
		this.map = null
		this.gl = null
	}

	/** put decoded frames on the card. Done inside render, where MapLibre expects its GL state to be touched */
	private upload(gl: WebGL2RenderingContext) {
		const job = this.pending.shift()
		if (!job) return
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
		if (this.pending.length) this.map?.triggerRepaint()
		this.onFrame?.()
	}

	private render(gl: WebGL2RenderingContext, input: CustomRenderMethodInput) {
		this.upload(gl)
		const { a, b, ref, gain, loss, observed } = this.view
		const A = this.slots.get(`f${a}`)
		const B = this.slots.get(`f${b}`)
		const base = this.slots.get('base')
		if (!this.program || !A || !B || !base) return
		const R = ref >= 0 ? this.slots.get(`f${ref}`) : undefined
		A.used = B.used = ++this.tick
		if (R) R.used = this.tick
		if (this.style.opacity <= 0.001) return

		const mat = quadMatrix(input.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>, this.meta.bounds)
		const now = performance.now()
		const flash = Math.max(0, 1 - (now - this.flashAt) / FLASH_MS)
		const u = this.uniforms
		const s = this.style
		gl.useProgram(this.program)
		gl.uniformMatrix4fv(u.u_matrix, false, mat)
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
		withClip(gl, this.clip, () => gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4))
		gl.bindVertexArray(null)

		// ripples and the pass pulse need a frame every tick; a still picture does not
		if (this.flow > 0.001 || flash > 0) this.map?.triggerRepaint()
	}
}
