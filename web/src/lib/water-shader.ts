// The fragment shader of the water layer: how one pixel of water, shoreline or burn looks.
//
// It only knows the ground: v_uv runs over the baked grid of the site (0..1), so the same code draws the layer flat
// on the map and draped over 3D terrain. Keep patterns in ground space (v_uv), never in screen space.
// The uniforms are set in water-layer.ts.
//
// The look, in one line each:
//   new water (not in the reference pass)   the news: bright, almost solid, a light shoreline, a glow, light on it
//   water that was there before             quiet: a thin white outline and a deep, calm fill
//   between two passes                      the shape travels; where the passes disagree it is a little see-through
//                                           and its shoreline is dashed, because it is an estimate
//   ground a pass did not see               a faint grey hatch, only at a pass
// The shape is the data. Nothing here invents depth, and nothing moves a shoreline.
export const WATER_FRAG = `#version 300 es
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
uniform float u_fill;
uniform float u_line;
uniform float u_reach;
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

// one part laid over what is already there; colours carry their alpha (premultiplied)
vec4 over(vec4 under, vec3 colour, float a) {
	a = clamp(a, 0.0, 1.0);
	return vec4(colour * a + under.rgb * (1.0 - a), a + under.a * (1.0 - a));
}

// Light on water, without drawing lines on it: slow, soft swells of brightness, as a calm surface gives back the
// sky. It lives on the ground, so it stays put under a moving camera, and it drifts slowly, so a still frame is
// calm. One unit of p is one radian of the basic wave.
float swell(vec2 p, float t, float seed) {
	// bend the ground a little first, so no straight line survives in the pattern
	p += 0.9 * vec2(sin(p.y * 0.53 + t * 0.21 + seed), cos(p.x * 0.47 - t * 0.17 + seed * 1.7));
	// three wave trains at wide angles to each other: where their crests meet the surface is brightest
	float w = sin(dot(p, vec2(0.97, 0.26)) + t * 0.31) + sin(dot(p, vec2(-0.5, 0.87)) - t * 0.23 + seed) + sin(dot(p, vec2(-0.26, -0.97)) * 1.17 + t * 0.19 + seed * 0.6);
	// a broad soft rise, and a small bright core where all three meet: the glint
	float core = smoothstep(1.5, 2.9, w);
	return smoothstep(-0.8, 2.4, w) * 0.6 + core * core * 0.4;
}

void main() {
	vec3 ta = texture(u_a, v_uv, u_soft).rgb;
	vec3 tb = texture(u_b, v_uv, u_soft).rgb;
	// the reference pass is bound to the first frame when there is none (u_hasRef says which)
	vec3 tr = texture(u_ref, v_uv, u_soft).rgb;
	float sea = texture(u_base, v_uv).r;

	// outside the water a distance counts for at most u_reach, so new water far from the old does not wait for
	// the last moment: it starts in its deepest part and grows out (the bake counts hectares the same way)
	float anyA = min(dist(ta.g), u_reach);
	float anyB = min(dist(tb.g), u_reach);
	float openA = min(dist(ta.b), u_reach);
	float openB = min(dist(tb.b), u_reach);
	// a pixel on its way into the water follows the gain clock, a pixel on its way out the loss clock
	float sAny = mix(anyA, anyB, anyB < anyA ? u_gain : u_loss);
	float sOpen = mix(openA, openB, openB < openA ? u_gain : u_loss);
	float refAny = dist(tr.g);
	float refOpen = dist(tr.b);

	// the ground in grid pixels (about 15 m each), and how many of them one screen pixel covers
	vec2 g = v_uv * u_size;
	// Every slope used below is taken here, before the shader may stop early: a slope needs all four pixels of
	// its little square, and some graphics drivers refuse one taken after a branch.
	vec2 gx = dFdx(g);
	vec2 gy = dFdy(g);
	float texel = max(length(fwidth(g)) * 0.7071, 1e-5);
	float wAny = fwidth(sAny);
	float wOpen = fwidth(sOpen);
	float wA = fwidth(anyA);
	float wB = fwidth(anyB);
	float wRef = fwidth(refAny);
	float wRefOpen = fwidth(refOpen);
	float sx = dFdx(sAny);
	float sy = dFdy(sAny);

	// ground this pass did not see: a faint grey hatch on the ground, only while the picture is a pass
	float seen = mix(ta.r, tb.r, step(0.5, 0.5 * (u_gain + u_loss)));
	float miss = (1.0 - smoothstep(0.35, 0.65, seen)) * u_obs * (1.0 - u_forecast);
	float hatch = 1.0 - smoothstep(0.07, 0.14, abs(fract((g.x + g.y) / 9.0) - 0.5));
	float missA = miss * mix(0.04, hatch * 0.09, smoothstep(3.0, 6.0, 9.0 / texel));
	float keep = (1.0 - smoothstep(0.35, 0.65, sea)) * u_opacity;

	// Far from the water of both passes (the distance has reached u_reach) nothing is drawn but that hatch: no fill,
	// no shore, no glow, no light. That is most of the ground, so stop here; the rest is the work of the water.
	if (min(anyA, anyB) >= u_reach - 0.01) {
		fragColor = vec4(u_cUnseen * missA, missA) * keep;
		return;
	}

	// the slope of the field, with a floor so flat patches stay sane
	float gAny = max(wAny, texel * 0.35);
	float px = sAny / gAny; // signed distance to the shoreline in screen pixels, negative in water
	// The same distance for everything soft (glow, rim, ripples): the field itself over the size of a pixel.
	// Far from a shore the field is stored in coarse steps, and its slope there is all noise, so px is only
	// trusted for the crisp things right at the shoreline.
	float dpx = sAny / texel;
	float water = clamp(0.5 - px, 0.0, 1.0);
	float open = clamp(0.5 - sOpen / max(wOpen, texel * 0.35), 0.0, 1.0);

	// Is this a body of water or a speck? Read the field 8 pixels wide: specks average out, bodies do not.
	// The wide field is mixed exactly as the sharp one, so a shore on its way between two passes keeps its line.
	float wideA = min(dist(textureLod(u_a, v_uv, 3.0).g), u_reach);
	float wideB = min(dist(textureLod(u_b, v_uv, 3.0).g), u_reach);
	float wide = mix(wideA, wideB, wideB < wideA ? u_gain : u_loss);
	float mass = 1.0 - smoothstep(-0.5, 3.0, wide);
	// the shore of open water, or only of water under plants? The second is drawn quieter.
	float openEdge = 1.0 - smoothstep(1.0, 3.0, sOpen - sAny);

	// Against the reference pass: water it did not have is new, a shoreline it did not have has moved.
	// With no reference there is nothing to call old, so all water is the news.
	float fresh = 1.0;
	float moved = 1.0;
	float wasLine = 0.0;
	if (u_hasRef > 0.5) {
		float gRef = max(wRef, texel * 0.35);
		float freshAny = clamp(0.5 + refAny / gRef, 0.0, 1.0);
		float freshOpen = clamp(0.5 + refOpen / max(wRefOpen, texel * 0.35), 0.0, 1.0);
		fresh = max(freshAny, open * freshOpen);
		moved = smoothstep(0.75, 3.0, abs(refAny - sAny));
		// the line between what was there and what is new: where "new" turns over, about one screen pixel wide
		wasLine = 1.0 - abs(2.0 * fresh - 1.0);
	}

	// only what the two passes disagree on is an estimate: water that both passes have is as sure between them
	float inA = clamp(0.5 - anyA / max(wA, texel * 0.35), 0.0, 1.0);
	float inB = clamp(0.5 - anyB / max(wB, texel * 0.35), 0.0, 1.0);
	float between = (1.0 - u_obs) * (1.0 - inA * inB);
	float shifting = (1.0 - u_obs) * smoothstep(0.5, 2.0, abs(anyB - anyA));

	// Which way the shore faces on the ground, not on the screen: the screen slope of the field, taken back through
	// the screen slope of the ground. So the light and the dashes below do not turn with the camera or the terrain.
	float det = gx.x * gy.y - gx.y * gy.x;
	vec2 grad = vec2(sx * gy.y - sy * gx.y, sy * gx.x - sx * gy.x) / (abs(det) > 1e-10 ? det : 1e-10);
	vec2 nrm = grad / max(length(grad), 1e-4); // from the water towards the land
	// the light comes from the north-west, as on a printed map (grid x runs east, grid y runs south)
	float face = dot(nrm, vec2(-0.7071, -0.7071));

	// Light plays on water only. A layer that is not blue (the burn scar) stays matt.
	float wet = smoothstep(0.05, 0.4, u_cOpen.b - u_cOpen.r);
	// two sizes of the same light: the fine one for close views, the broad one from far out, where the fine one
	// would be smaller than a screen pixel and shimmer
	float fine = swell(g * 0.45, u_time, 0.0) * (1.0 - smoothstep(1.2, 2.6, texel));
	float broad = swell(g * 0.16 + 5.3, u_time * 0.7, 2.1);
	float light = mix(broad, fine, 0.55) * wet;
	// and one wide, slow change of brightness across the whole surface, as a sheet of water gives back the sky.
	// Soft on purpose: a sharp band would be a straight line across the flood, and a straight line reads as a fault.
	float sheen = 0.5 + 0.5 * sin(dot(g, vec2(0.05, 0.03)) - u_time * 0.25);

	// the news: the colour of the layer at full strength; flooded vegetation in its own, calmer colour
	vec3 hero = mix(u_cVeg, u_cOpen, open);
	vec3 surf = hero * (0.92 + 0.14 * sheen * wet);
	surf = mix(surf, u_cGlow, light * mix(0.14, 0.34, open));
	// The edge of a sheet: just inside the shoreline the side that faces the light is brighter and the side away
	// from it a little deeper. A few screen pixels wide wherever you are: it is the edge, not the depth.
	float rim = exp(min(dpx, 0.0) / 3.5) * mass * moved * u_line;
	surf = mix(surf, u_cGlow, rim * mix(0.12, 0.55, max(face, 0.0)));
	surf *= 1.0 - rim * 0.22 * max(-face, 0.0);
	surf = min(surf + u_flash * 0.1, vec3(1.0));
	// What was there before: the same water, deep and quiet. Dark, not pale: a pale patch inside a flood reads as
	// an island of land, a dark one reads as the water that is always there.
	vec3 calm = hero * 0.42 + vec3(0.02, 0.03, 0.05);

	vec3 fillCol = mix(calm, surf, fresh);
	float fillA = water * mix(mix(0.6, 0.8, open), mix(0.62, 0.9, open), fresh) * u_fill;
	// an estimate is a little see-through; no pattern over it
	fillA *= mix(1.0, 0.7, between);

	// ripples run with the shoreline: outward where water gains ground, inward where it gives it back
	float delta = anyB - anyA;
	float moving = smoothstep(1.0, 9.0, abs(delta)) * u_flow * mass;
	float dir = delta < 0.0 ? 1.0 : -1.0;
	float wave = sin(dpx * 0.45 - dir * u_time * 4.2);
	float ripple = smoothstep(0.72, 1.0, wave) * smoothstep(-26.0, -3.0, dpx) * step(dpx, 0.0) * moving;
	fillCol = mix(fillCol, u_cEdge, ripple * 0.36);

	// Shoreline: a clean light line. New shore is drawn full, old shore thinner, specks faint: a speck of water
	// (the wide field says land) and a pinhole of land inside a body of water (the wide field says deep water)
	// are radar speckle more often than not, and a bright ring around each would sparkle.
	float pinhole = smoothstep(-1.2, -3.2, wide);
	float weight = mix(0.2, 1.0, mass) * (1.0 - 0.7 * pinhole) * u_line;
	float line = mix(clamp(1.1 - abs(px), 0.0, 1.0) * 0.85, clamp(1.6 - abs(px), 0.0, 1.0), moved) * weight * mix(0.45, 1.0, openEdge);
	// An estimate has a dashed shoreline. The dashes are counted on the ground along the axis the shore runs
	// closest to, so they keep their length whichever way the shore turns; from far out they merge into a
	// lighter line instead of flickering.
	vec2 tangent = vec2(-nrm.y, nrm.x);
	float along = abs(tangent.x) > abs(tangent.y) ? g.x : g.y;
	float dashes = smoothstep(0.38, 0.52, abs(fract(along / 6.0) - 0.5) * 2.0);
	float dash = mix(0.6, dashes, smoothstep(4.0, 7.0, 6.0 / texel));
	line *= mix(1.0, dash, shifting);
	// the outline of the old water also where new water now surrounds it
	line = max(line, wasLine * water * 0.85 * weight);

	// on the land side: a soft glow in the colour of the layer, a thin dark casing so the shape also holds on a
	// bright picture (cloud), and a little shade on the side away from the light
	float land = step(0.0, px) * (1.0 - water);
	float halo = exp(-max(dpx, 0.0) / 8.0) * land * mass * moved * (0.42 + 0.5 * u_flash) * u_line * mix(0.25, 1.0, openEdge);
	float casing = clamp(1.0 - abs(px - 1.7), 0.0, 1.0) * land * mass * mix(0.3, 0.5, moved) * u_line;
	float shade = exp(-max(dpx - 1.0, 0.0) / 5.0) * land * mass * moved * max(-face, 0.0) * 0.32 * u_line;

	// forecast: no solid water, only stripes on the ground inside the likely extent, and a dashed outline
	float stripes = smoothstep(0.34, 0.46, abs(fract((g.x + g.y) / 12.0) - 0.5));
	stripes = mix(0.5, stripes, smoothstep(4.0, 7.0, 12.0 / texel));
	fillA = mix(fillA, water * (0.1 + 0.34 * (1.0 - stripes)), u_forecast);
	fillCol = mix(fillCol, hero, u_forecast);
	line = mix(line, clamp(1.6 - abs(px), 0.0, 1.0) * dash * weight, u_forecast);
	halo *= 1.0 - u_forecast;
	shade *= 1.0 - u_forecast;

	// bottom to top: the hatch of unseen ground, shade, glow, casing, the water itself, the shoreline
	vec4 acc = vec4(0.0);
	acc = over(acc, u_cUnseen, missA);
	acc = over(acc, vec3(0.0, 0.02, 0.06), shade);
	acc = over(acc, u_cGlow, halo);
	acc = over(acc, u_cOpen * 0.12, casing);
	acc = over(acc, fillCol, fillA);
	acc = over(acc, u_cEdge, line);

	fragColor = acc * keep;
}`
