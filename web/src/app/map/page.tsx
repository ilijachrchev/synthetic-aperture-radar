import type { Metadata } from 'next'
import { MapApp, type StoryCfg } from '@/components/map/map-app'
import { STORIES } from '@/content/landing'
import { RADAR, type SiteKey } from '@/lib/radar'

export const metadata: Metadata = { title: 'Map · Dancing with the SARs' }

const PLACES: Record<string, { site: SiteKey; name: string }[]> = {
	water: [
		{ site: 'coast', name: 'Albufera' },
		{ site: 'pego', name: 'Pego-Oliva marsh' },
	],
	fire: [{ site: 'espada', name: "Serra d'Espadà" }],
	sink: [{ site: 'lorca', name: 'Lorca' }],
	quake: [{ site: 'panama', name: 'Panama' }],
}

export default function MapPage() {
	const stories: StoryCfg[] = STORIES.map((s, i) => {
		const places = PLACES[s.key].map(({ site, name }) => {
			const d = RADAR.sites[site]
			const byTrack = new Map<string, typeof d.passes>()
			for (const p of d.passes) if (p.img) byTrack.set(p.track, [...(byTrack.get(p.track) ?? []), p])
			const tracks = [...byTrack.entries()]
				.map(([id, ps]) => ({
					id,
					label: `${id} ${ps[0].dir}`,
					passes: ps.map((p) => ({ img: p.img!, dates: p.dates, crid: p.crid, granule: p.granule, collection: p.collection })),
				}))
				.sort((x, y) => y.passes.length - x.passes.length)
			return { site, name, box: d.box, product: d.product, tracks }
		})
		const c0 = s.compare[0]
		const c1 = s.compare[1]
		const pi = Math.max(0, places.findIndex((p) => p.site === c0.site))
		const ti = Math.max(0, places[pi].tracks.findIndex((t) => t.id === c0.track))
		const idx = (date: string) => places[pi].tracks[ti].passes.findIndex((p) => p.dates[p.dates.length - 1] === date)
		return {
			key: s.key,
			n: String(i + 1).padStart(2, '0'),
			tab: s.tab,
			title: s.title,
			what: s.what,
			where: s.where,
			kind: s.kind,
			note: s.note,
			places,
			initial: { pi, ti, a: Math.max(0, idx(c0.date)), b: c1 ? idx(c1.date) : null },
		}
	})
	return <MapApp stories={stories} />
}
