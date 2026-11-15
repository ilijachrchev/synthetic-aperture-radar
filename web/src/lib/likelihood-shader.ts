// The fragment shader of the prediction layer: how one pixel of the model's map looks.
//
// The model gives a relative likelihood of water (scripts/bake_prediction.py, G of each frame), not a measured
// shoreline and not depth. So it is drawn as an estimate on purpose, never like a radar pass:
//   a see-through fill whose strength follows the likelihood (faint where it is low)
//   water that would be new (dry on the map the prediction was issued from) bright; water that was already there
//   deep and quiet, as on the radar layer
//   one dashed line around the likely new water: where the likelihood reaches the model's "new water" threshold on
//   ground that was dry and that the model predicts itself (evidence 0). The hectares on the page are counted
//   inside that line, by the same rule (forecast.json, "counted on evidence 0 pixels only")
//   ground where the model only extrapolates (towns, ground Sentinel-1 rarely maps) at half strength, with no line
// No light, no ripples: nothing on it moves but the change from one rain to the next. Like the water shader it only
// knows the ground (v_uv over the baked grid), so the same code draws flat and draped over the terrain.
export const LIKELIHOOD_FRAG = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_a;
uniform sampler2D u_b;
uniform float u_mix;
uniform vec2 u_size;
uniform float u_opacity;
uniform float u_thr;
uniform float u_soft;
uniform vec3 u_cLow;
uniform vec3 u_cHigh;
uniform vec3 u_cOld;
uniform vec3 u_cLine;

vec4 over(vec4 under, vec3 colour, float a) {
	a = clamp(a, 0.0, 1.0);
	return vec4(colour * a + under.rgb * (1.0 - a), a + under.a * (1.0 - a));
}

void main() {
	vec3 ta = texture(u_a, v_uv, u_soft).rgb;
	vec3 tb = texture(u_b, v_uv, u_soft).rgb;
	float trust = mix(ta.r, tb.r, u_mix);
	// G holds percent: 100 is 100/255 of the byte range
	float L = mix(ta.g, tb.g, u_mix) * (255.0 / 100.0);
	float dry = mix(ta.b, tb.b, u_mix);

	// every slope first: some drivers refuse a slope taken after a branch
	vec2 g = v_uv * u_size;
	vec2 gx = dFdx(g);
	vec2 gy = dFdy(g);
	float texel = max(length(fwidth(g)) * 0.7071, 1e-5);
	float wL = fwidth(L);
	float sx = dFdx(L);
	float sy = dFdy(L);

	float on = smoothstep(0.03, 0.2, trust) * u_opacity;
	if (on <= 0.001 || L < 0.05) {
		fragColor = vec4(0.0);
		return;
	}
	// 1 where the value is the model's own, 0 where it is extrapolated from fields
	float own = smoothstep(0.5, 0.85, trust);

	// the line of likely water in screen pixels, positive inside it
	float px = (L - u_thr) / max(wL, texel * 0.002);
	float inside = clamp(0.5 + px, 0.0, 1.0);
	float low = smoothstep(0.05, u_thr, L);
	float high = smoothstep(u_thr, 0.95, L);
	float fillA = mix(0.16 * low, 0.44 + 0.3 * high, inside);
	vec3 fill = mix(u_cLow, u_cHigh, smoothstep(0.12, 0.8, L));
	fill = mix(u_cOld, fill, smoothstep(0.25, 0.75, dry));
	fillA *= mix(0.5, 1.0, own);

	// the line is dashed, the dashes counted on the ground along the axis the line runs closest to, so they keep
	// their length whichever way it turns; from far out they merge into a lighter line instead of flickering
	float det = gx.x * gy.y - gx.y * gy.x;
	vec2 grad = vec2(sx * gy.y - sy * gx.y, sy * gx.x - sx * gy.x) / (abs(det) > 1e-10 ? det : 1e-10);
	vec2 nrm = grad / max(length(grad), 1e-6);
	vec2 tangent = vec2(-nrm.y, nrm.x);
	float along = abs(tangent.x) > abs(tangent.y) ? g.x : g.y;
	float dashes = smoothstep(0.36, 0.52, abs(fract(along / 5.0) - 0.5) * 2.0);
	float dash = mix(0.62, dashes, smoothstep(3.0, 6.0, 5.0 / texel));
	// the line only where water would be new and the value is the model's own: what the hectares count
	float counted = own * smoothstep(0.6, 0.9, dry);
	float line = clamp(1.25 - abs(px), 0.0, 1.0) * dash * counted;
	// a thin dark casing on the outer side keeps the line readable on a bright picture
	float casing = clamp(1.0 - abs(px + 1.6), 0.0, 1.0) * 0.35 * counted;

	vec4 acc = vec4(0.0);
	acc = over(acc, fill, fillA);
	acc = over(acc, vec3(0.01, 0.04, 0.09), casing);
	acc = over(acc, u_cLine, line * 0.92);
	fragColor = acc * on;
}`
