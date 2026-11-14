'use client'

import { useEffect, useRef } from 'react'

/**
 * Slow lagoon water behind the hero, the way 8x.sale's hero has smoke but quieter: domain-warped noise in three
 * colours of the theme (--smoke-0 base, --smoke-1 body, --smoke-2 the brightest wisps), drawn by one small shader at a
 * third of the panel's size and scaled up, so it costs almost nothing. It runs at 30fps while on screen, holds still
 * under reduced motion, and the panel's own gradient shows if WebGL is not there.
 */
const VERT = 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}'
const FRAG = `precision mediump float;
uniform vec2 r;uniform float t;uniform vec3 c0;uniform vec3 c1;uniform vec3 c2;
float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float n(vec2 p){vec2 i=floor(p),f=fract(p);vec2 u=f*f*(3.-2.*f);
return mix(mix(h(i),h(i+vec2(1.,0.)),u.x),mix(h(i+vec2(0.,1.)),h(i+vec2(1.,1.)),u.x),u.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int k=0;k<5;k++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}
void main(){
vec2 uv=gl_FragCoord.xy/r;vec2 p=uv*vec2(r.x/r.y,1.)*1.5;float s=t*.03;
vec2 q=vec2(fbm(p+vec2(0.,s)),fbm(p+vec2(5.2,1.3)-s));
vec2 w=vec2(fbm(p+3.*q+vec2(1.7,9.2)+s*1.3),fbm(p+3.*q+vec2(8.3,2.8)-s));
float f=fbm(p+2.6*w);
vec3 col=mix(c0,c1,smoothstep(.3,.85,f));
col=mix(col,c2,smoothstep(.62,1.05,length(w))*.75);
gl_FragColor=vec4(col,1.);}`

/** A CSS colour as 0 to 1 channels: #rgb, #rrggbb (the build shortens #ffffff to #fff) or rgb(). */
function rgb(v: string): [number, number, number] {
	const s = v.trim()
	let m = s.match(/^#([0-9a-f]{3})$/i)
	if (m) return [0, 1, 2].map((i) => parseInt(m![1][i] + m![1][i], 16) / 255) as [number, number, number]
	m = s.match(/^#([0-9a-f]{6})$/i)
	if (m) {
		const x = parseInt(m[1], 16)
		return [((x >> 16) & 255) / 255, ((x >> 8) & 255) / 255, (x & 255) / 255]
	}
	const n = s.match(/rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i)
	if (n) return [Number(n[1]) / 255, Number(n[2]) / 255, Number(n[3]) / 255]
	return [1, 1, 1]
}

export function Smoke({ className = '' }: { className?: string }) {
	const ref = useRef<HTMLCanvasElement>(null)
	useEffect(() => {
		const c = ref.current
		if (!c) return
		const gl = c.getContext('webgl', { antialias: false, alpha: false, preserveDrawingBuffer: false })
		if (!gl) return
		const shader = (type: number, src: string) => {
			const s = gl.createShader(type)!
			gl.shaderSource(s, src)
			gl.compileShader(s)
			return s
		}
		const prog = gl.createProgram()!
		gl.attachShader(prog, shader(gl.VERTEX_SHADER, VERT))
		gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAG))
		gl.linkProgram(prog)
		if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return
		gl.useProgram(prog)
		const buf = gl.createBuffer()
		gl.bindBuffer(gl.ARRAY_BUFFER, buf)
		gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
		const loc = gl.getAttribLocation(prog, 'a')
		gl.enableVertexAttribArray(loc)
		gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
		const uR = gl.getUniformLocation(prog, 'r')
		const uT = gl.getUniformLocation(prog, 't')
		const uC = [gl.getUniformLocation(prog, 'c0'), gl.getUniformLocation(prog, 'c1'), gl.getUniformLocation(prog, 'c2')]

		const colours = () => {
			const s = getComputedStyle(c)
			;['--smoke-0', '--smoke-1', '--smoke-2'].forEach((v, i) => gl.uniform3fv(uC[i], rgb(s.getPropertyValue(v))))
		}
		const size = () => {
			// a third of the panel: the noise is soft, so the scaled-up picture loses nothing
			c.width = Math.max(2, Math.round(c.clientWidth / 3))
			c.height = Math.max(2, Math.round(c.clientHeight / 3))
			gl.viewport(0, 0, c.width, c.height)
			gl.uniform2f(uR, c.width, c.height)
		}
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		const t0 = performance.now() - 40000
		const draw = (now: number) => {
			gl.uniform1f(uT, (now - t0) / 1000)
			gl.drawArrays(gl.TRIANGLES, 0, 3)
		}
		colours()
		size()
		draw(performance.now())
		c.dataset.on = ''

		let raf = 0
		let last = 0
		let seen = true
		const io = new IntersectionObserver(([e]) => (seen = e.isIntersecting))
		io.observe(c)
		const loop = (now: number) => {
			raf = requestAnimationFrame(loop)
			if (!seen || document.hidden || now - last < 33) return
			last = now
			draw(now)
		}
		if (!reduced) raf = requestAnimationFrame(loop)
		const ro = new ResizeObserver(() => {
			size()
			draw(performance.now())
		})
		ro.observe(c)
		const mo = new MutationObserver(() => {
			colours()
			draw(performance.now())
		})
		mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
		return () => {
			cancelAnimationFrame(raf)
			io.disconnect()
			ro.disconnect()
			mo.disconnect()
		}
	}, [])
	return <canvas ref={ref} className={className} aria-hidden />
}
