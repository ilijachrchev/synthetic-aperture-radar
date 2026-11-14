import { datesWithCounts, day, monthName, type SiteKey } from '@/lib/radar'

const W = 440
const H = 132
const X0 = 6
const X1 = 434
const BASE = 86

/**
 * Every NISAR pass over a site as a pulse on one thin line, like a signal trace: each peak sits on a real
 * acquisition date and stands twice as tall when two tracks passed that day. The latest pass is marked.
 */
export function PulseChart({ site, from = '2026-06-01', to = '2026-11-01', className = '' }: { site: SiteKey; from?: string; to?: string; className?: string }) {
	const passes = datesWithCounts(site)
	const t0 = Date.parse(from)
	const t1 = Date.parse(to)
	const x = (iso: string) => X0 + ((Date.parse(iso) - t0) / (t1 - t0)) * (X1 - X0)

	const peaks = passes.map((p) => ({ cx: x(p.date), a: p.count > 1 ? 40 : 22 }))
	const sigma = 3.1
	const pts: string[] = []
	for (let px = X0; px <= X1; px += 0.75) {
		let y = BASE + Math.sin(px / 9) * 1.1
		for (const p of peaks) y -= p.a * Math.exp(-(((px - p.cx) / sigma) ** 2))
		pts.push(`${px.toFixed(2)},${y.toFixed(2)}`)
	}

	const last = passes[passes.length - 1]
	const lx = x(last.date)
	const ly = BASE - (last.count > 1 ? 40 : 22)
	const months: { m: number; x: number }[] = []
	for (let m = Number(from.slice(5, 7)); m <= Number(to.slice(5, 7)) - 1; m++) {
		months.push({ m, x: x(`${from.slice(0, 4)}-${String(m).padStart(2, '0')}-01`) })
	}

	return (
		<svg viewBox={`0 0 ${W} ${H}`} className={className} role="img" aria-label={`${passes.length} NISAR acquisition dates between ${day(passes[0].date)} and ${day(last.date)}`}>
			<g stroke="var(--chart-grid)" strokeWidth="1" strokeDasharray="2 5">
				{[30, 58, BASE].map((y) => (
					<line key={y} x1={X0} x2={X1} y1={y} y2={y} />
				))}
				{months.map(({ m, x: mx }) => (
					<line key={m} x1={mx} x2={mx} y1={20} y2={BASE + 8} />
				))}
			</g>
			<polyline points={pts.join(' ')} fill="none" stroke="var(--chart)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
			<line x1={lx} x2={lx} y1={ly} y2={H - 4} stroke="var(--chart)" strokeOpacity="0.45" strokeWidth="1" />
			<circle cx={lx} cy={ly} r="3.2" fill="var(--chart)" />
			<circle cx={lx} cy={ly} r="7" fill="var(--chart)" fillOpacity="0.18" />
			<text x={lx - 8} y={ly - 10} textAnchor="end" fontSize="12" fill="var(--hero-ink)" fontWeight="500">
				{day(last.date)}
			</text>
			<g fontSize="11" fill="var(--hero-muted)">
				{months.map(({ m, x: mx }) => (
					<text key={m} x={mx + 3} y={BASE + 24}>
						{monthName(m)}
					</text>
				))}
				<text x={X1 - 6} y={BASE + 24} textAnchor="end">
					2026
				</text>
			</g>
		</svg>
	)
}
