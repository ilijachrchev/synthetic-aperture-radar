// Shared pieces for the map's own WebGL layers: one georeferenced rectangle drawn by a custom shader.
// Bounds are west, south, east, north in degrees; the rectangle is exact in Web Mercator, which is the grid the
// frames and pictures are baked on (scripts/bake_water.py, scripts/fetch_optical.py).

export type Bounds = [number, number, number, number]

export const QUAD_VERT = `#version 300 es
in vec2 a_pos;
uniform mat4 u_matrix;
out vec2 v_uv;
void main() {
	v_uv = a_pos;
	gl_Position = u_matrix * vec4(a_pos, 0.0, 1.0);
}`

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

export function buildProgram(gl: WebGL2RenderingContext, vert: string, frag: string) {
	const compile = (type: number, src: string) => {
		const sh = gl.createShader(type)!
		gl.shaderSource(sh, src)
		gl.compileShader(sh)
		if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) ?? 'shader failed to compile')
		return sh
	}
	const program = gl.createProgram()!
	gl.attachShader(program, compile(gl.VERTEX_SHADER, vert))
	gl.attachShader(program, compile(gl.FRAGMENT_SHADER, frag))
	gl.linkProgram(program)
	if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? 'program failed to link')
	return program
}

/** A unit square as a triangle strip, bound to the program's a_pos. */
export function unitQuad(gl: WebGL2RenderingContext, program: WebGLProgram) {
	const vao = gl.createVertexArray()!
	const buffer = gl.createBuffer()!
	gl.bindVertexArray(vao)
	gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
	gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW)
	const loc = gl.getAttribLocation(program, 'a_pos')
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
