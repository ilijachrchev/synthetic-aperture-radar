// Shared pieces for the map's own WebGL layers: one georeferenced rectangle drawn by a custom shader.
// Bounds are west, south, east, north in degrees; the rectangle is exact in Web Mercator, which is the grid the
// frames and pictures are baked on (scripts/bake_water.py, scripts/fetch_optical.py).

export type Bounds = [number, number, number, number]

/** Over terrain MapLibre keeps each terrain tile as a texture, 2048 pixels a side, and draws all of them again, with
 *  everything on them, whenever one of our layers says it has changed. Our layers say so at most this often (about
 *  30 times a second): the camera still moves at full speed over the textures. */
export const TERRAIN_REDRAW_MS = 32

export const QUAD_VERT = `#version 300 es
in vec2 a_pos;
uniform mat4 u_matrix;
out vec2 v_uv;
void main() {
	v_uv = a_pos;
	gl_Position = u_matrix * vec4(a_pos, 0.0, 1.0);
}`

/** The same rectangle drawn into one terrain tile, which MapLibre then lays over the 3D ground (renderToTerrainTile).
 *  The tile is its own little framebuffer, so there is no camera matrix: the part of the tile the rectangle covers is
 *  given in the tile's clip space, and v_uv runs over the rectangle as in the flat path, so fragment shaders are shared. */
export const TILE_VERT = `#version 300 es
in vec2 a_pos;
uniform vec4 u_rect;
uniform vec4 u_clip;
out vec2 v_uv;
void main() {
	v_uv = mix(u_rect.xy, u_rect.zw, a_pos);
	gl_Position = vec4(mix(u_clip.xy, u_clip.zw, a_pos), 0.0, 1.0);
}`

/** Where the bounds meet a terrain tile: the part of the rectangle (0..1, north at 0) and the same corners in the
 *  tile's clip space, where (-1, -1) is the south-west corner. Null when they do not meet. */
export function tileRect(bounds: Bounds, tile: { canonical: { z: number; x: number; y: number } }) {
	const [west, south, east, north] = bounds
	const sx0 = mercX(west)
	const sx1 = mercX(east)
	const sy0 = mercY(north)
	const sy1 = mercY(south)
	const n = 2 ** tile.canonical.z
	const tx0 = tile.canonical.x / n
	const tx1 = (tile.canonical.x + 1) / n
	const ty0 = tile.canonical.y / n
	const ty1 = (tile.canonical.y + 1) / n
	const x0 = Math.max(sx0, tx0)
	const x1 = Math.min(sx1, tx1)
	const y0 = Math.max(sy0, ty0)
	const y1 = Math.min(sy1, ty1)
	if (x0 >= x1 || y0 >= y1) return null
	const u = (x: number) => (x - sx0) / (sx1 - sx0)
	const v = (y: number) => (y - sy0) / (sy1 - sy0)
	const cx = (x: number) => -1 + (2 * (x - tx0)) / (tx1 - tx0)
	const cy = (y: number) => 1 - (2 * (y - ty0)) / (ty1 - ty0)
	return { rect: new Float32Array([u(x0), v(y0), u(x1), v(y1)]), clip: new Float32Array([cx(x0), cy(y0), cx(x1), cy(y1)]) }
}

export function mercX(lon: number) {
	return (lon + 180) / 360
}

export function mercY(lat: number) {
	const s = Math.sin((lat * Math.PI) / 180)
	return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)
}

/** MapLibre's Mercator matrix times "unit square onto these bounds", composed in doubles so high zoom stays steady. */
export function quadMatrix(main: ArrayLike<number>, bounds: Bounds) {
	const [west, south, east, north] = bounds
	const x0 = mercX(west)
	const y0 = mercY(north)
	const sx = mercX(east) - x0
	const sy = mercY(south) - y0
	const mat = new Float32Array(16)
	for (let i = 0; i < 4; i++) {
		mat[i] = main[i] * sx
		mat[4 + i] = main[4 + i] * sy
		mat[8 + i] = main[8 + i]
		mat[12 + i] = main[i] * x0 + main[4 + i] * y0 + main[12 + i]
	}
	return mat
}

/** A program that compiles on its own: `ready()` is false until it can be drawn with. */
export type LazyProgram = { program: WebGLProgram; ready: () => boolean }

/**
 * Compile a program without waiting for it. Asking for the result of a compile right away holds the page until the
 * graphics driver is done, and the water shader takes the driver a long while (hundreds of milliseconds on some
 * laptops). With KHR_parallel_shader_compile the browser compiles on another thread and `ready()` turns true once
 * the program is linked; without it, `ready()` waits for the compile the first time it is asked.
 */
export function startProgram(gl: WebGL2RenderingContext, vert: string, frag: string): LazyProgram {
	const parallel = gl.getExtension('KHR_parallel_shader_compile')
	const shader = (type: number, src: string) => {
		const sh = gl.createShader(type)!
		gl.shaderSource(sh, src)
		gl.compileShader(sh)
		return sh
	}
	const vs = shader(gl.VERTEX_SHADER, vert)
	const fs = shader(gl.FRAGMENT_SHADER, frag)
	const program = gl.createProgram()!
	gl.attachShader(program, vs)
	gl.attachShader(program, fs)
	// the same slot in every program, so the flat and the draped program of a layer share one vertex array
	gl.bindAttribLocation(program, 0, 'a_pos')
	gl.linkProgram(program)
	let done = false
	return {
		program,
		ready() {
			if (done) return true
			if (parallel && !gl.getProgramParameter(program, parallel.COMPLETION_STATUS_KHR)) return false
			if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
				throw new Error(gl.getShaderInfoLog(fs) || gl.getShaderInfoLog(vs) || gl.getProgramInfoLog(program) || 'program failed to link')
			}
			gl.deleteShader(vs)
			gl.deleteShader(fs)
			done = true
			return true
		},
	}
}

/** A unit square as a triangle strip, on attribute 0, where every program here binds a_pos. Asking the program for
 *  the place of a_pos would wait for its compile to finish, which is what startProgram avoids. */
export function unitQuad(gl: WebGL2RenderingContext) {
	const vao = gl.createVertexArray()!
	const buffer = gl.createBuffer()!
	gl.bindVertexArray(vao)
	gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
	gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW)
	const loc = 0
	gl.enableVertexAttribArray(loc)
	gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
	gl.bindVertexArray(null)
	return { vao, buffer }
}

/** Limit drawing to a vertical band of the map, given as fractions of its width (for the swipe). */
export function withClip(gl: WebGL2RenderingContext, clip: [number, number], draw: () => void) {
	const full = clip[0] <= 0 && clip[1] >= 1
	if (!full) {
		const w = gl.drawingBufferWidth
		const x0 = Math.round(Math.max(0, clip[0]) * w)
		const x1 = Math.round(Math.min(1, clip[1]) * w)
		gl.enable(gl.SCISSOR_TEST)
		gl.scissor(x0, 0, Math.max(0, x1 - x0), gl.drawingBufferHeight)
	}
	draw()
	if (!full) gl.disable(gl.SCISSOR_TEST)
}
