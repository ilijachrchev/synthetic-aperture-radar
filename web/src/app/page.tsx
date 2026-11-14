import { Hero, MapPreview, Stories } from '@/components/landing'
import { LandingMotion } from '@/components/landing-motion'
import { SiteFooter } from '@/components/site-footer'
import { Smooth } from '@/components/smooth'
import type { Chapter } from '@/components/story-scroll'
import { STORIES } from '@/content/landing'
import ground from '@/data/context.json'
import { day, imaged, monthName, RADAR } from '@/lib/radar'

const GROUND = ground as unknown as Record<string, { w: number; h: number; box: [number, number, number, number] }>

/** Each story's pinned chapter: every imaged pass of the track it is told on, laid on its satellite ground. */
function chapters(): Chapter[] {
	return STORIES.map((s) => {
		const { site, track } = s.compare[s.compare.length - 1]
		const passes = imaged(site, track)
		const last = (p: (typeof passes)[number]) => p.dates[p.dates.length - 1]
		const t = passes.map((p) => Date.parse(last(p)))
		const lo = Math.min(...t) - 6 * 864e5
		const hi = Math.max(...t) + 6 * 864e5
		const at = (v: number) => (v - lo) / (hi - lo)
		const months: Chapter['months'] = []
		const d = new Date(lo)
		d.setUTCDate(1)
		d.setUTCMonth(d.getUTCMonth() + 1)
		while (d.getTime() < hi) {
			months.push({ label: monthName(d.getUTCMonth() + 1), at: at(d.getTime()) })
			d.setUTCMonth(d.getUTCMonth() + 1)
		}
		const ev = s.change.event
		const [w, so, e, n] = RADAR.sites[site].box
		const epi: [number, number] = s.change.epicentre ? [(s.change.epicentre[0] - w) / (e - w), (n - s.change.epicentre[1]) / (n - so)] : [0.5, 0.5]
		return {
			key: s.key,
			kind: s.kind,
			title: s.title,
			what: s.what,
			where: s.where,
			legend: s.change.legend,
			change: s.change.kind,
			track: `${track} ${passes[0].dir}`,
			frames: passes.map((p) => p.img!),
			dates: passes.map((p) => ({ day: day(last(p)), pair: p.dates.length > 1 ? `${day(p.dates[0])} > ${day(last(p))}` : null })),
			at: t.map(at),
			months,
			refCount: ev ? Math.max(1, passes.filter((p) => p.dates[0] < ev).length) : 1,
			revealAt: s.change.kind === 'quake' && ev ? passes.findIndex((p) => p.dates[0] < ev && last(p) >= ev) : -1,
			epi,
			ground: { src: `/img/context/${site}.webp`, ...GROUND[site] },
		}
	})
}

export default function Home() {
	const season = imaged('valencia', '066').map((p) => ({ img: p.img!, date: p.dates[0] }))
	const albufera = RADAR.sites.albufera.passes
	const facts = [`${albufera.length} passes since ${day(albufera[0].dates[0])}`, 'One pass every 12 days', 'Sees through cloud, day or night']

	return (
		<main>
			<Smooth />
			<LandingMotion />
			<Hero radar={season} track="066 D" facts={facts} />
			<Stories chapters={chapters()} />
			<MapPreview />
			<SiteFooter />
		</main>
	)
}
