import data from '@/data/passes.json'

// Real NISAR passes from NASA's public catalogue (scripts/fetch_radar.py). A pass with img null is real and counted;
// it only does not cover that site's box well enough to draw.
export type Pass = {
	dates: string[]
	track: string
	dir: 'A' | 'D'
	frame: string
	mode: string
	crid: string | null
	collection: string
	granule: string
	img: string | null
	valid: number
	px: [number, number]
}
export type SiteKey = 'albufera' | 'pego' | 'espada' | 'lorca' | 'panama' | 'valencia'
export type SiteData = { product: 'GCOV' | 'GUNW'; box: [number, number, number, number]; point: [number, number]; passes: Pass[] }

export const RADAR = data as unknown as { source: string; sites: Record<SiteKey, SiteData> }

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2026-10-28" as "28 Oct". Built by hand so server and browser always agree. */
export function day(iso: string) {
	const [, m, d] = iso.split('-').map(Number)
	return `${d} ${MONTHS[m - 1]}`
}
export function dayYear(iso: string) {
	return `${day(iso)} ${iso.slice(0, 4)}`
}
export function monthName(m: number) {
	return MONTHS[m - 1]
}

/** Acquisition dates for a backscatter site, each with how many passes (tracks) landed that day. */
export function datesWithCounts(site: SiteKey) {
	const counts = new Map<string, number>()
	for (const p of RADAR.sites[site].passes) {
		const d = p.dates[p.dates.length - 1]
		counts.set(d, (counts.get(d) ?? 0) + 1)
	}
	return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, count]) => ({ date, count }))
}

export function imaged(site: SiteKey, track?: string) {
	return RADAR.sites[site].passes.filter((p) => p.img && (!track || p.track === track))
}

export function latest(site: SiteKey, track?: string) {
	const list = imaged(site, track)
	return list[list.length - 1]
}

/** Coordinates the way a chart caption writes them: 39.33° N, 0.35° W. */
export function coords([lon, lat]: [number, number]) {
	const ns = lat >= 0 ? 'N' : 'S'
	const ew = lon >= 0 ? 'E' : 'W'
	return `${Math.abs(lat).toFixed(2)}° ${ns}, ${Math.abs(lon).toFixed(2)}° ${ew}`
}

/** The pass (or pair) on a site whose last date and track match. */
export function findPass(site: SiteKey, date: string, track: string) {
	return RADAR.sites[site].passes.find((p) => p.dates[p.dates.length - 1] === date && p.track === track && p.img)
}

/** "31 passes · 18 Jun to 28 Oct" for a backscatter site, "16 pairs · ..." for ground motion. */
export function coverage(site: SiteKey) {
	const s = RADAR.sites[site]
	const first = s.passes[0].dates[0]
	const last = s.passes[s.passes.length - 1].dates.at(-1)!
	const unit = s.product === 'GUNW' ? 'pairs' : 'passes'
	return `${s.passes.length} ${unit} · ${day(first)} to ${day(last)}`
}
