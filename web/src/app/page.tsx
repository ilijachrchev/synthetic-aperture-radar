import { Hero, MapPreview, type StoryCardData, Stories } from '@/components/landing'
import { LandingMotion } from '@/components/landing-motion'
import { SiteFooter } from '@/components/site-footer'
import { Smooth } from '@/components/smooth'
import { STORIES } from '@/content/landing'
import { coverage, day, findPass, imaged, RADAR } from '@/lib/radar'

export default function Home() {
	const season = imaged('valencia', '066').map((p) => ({ img: p.img!, date: p.dates[0] }))
	const albufera = RADAR.sites.albufera.passes
	const facts = [`${albufera.length} passes since ${day(albufera[0].dates[0])}`, 'One pass every 12 days', 'Sees through cloud, day or night']

	const cards: StoryCardData[] = STORIES.map((s) => {
		const [p0, p1] = s.compare.map((c) => findPass(c.site, c.date, c.track)!)
		const label = (p: NonNullable<typeof p0>) => p.dates.map(day).join(' > ')
		return {
			key: s.key,
			title: s.title,
			what: s.what,
			kind: s.kind,
			where: s.where,
			coverage: coverage(s.site),
			before: { img: p0.img!, label: label(p0) },
			after: { img: (p1 ?? p0).img!, label: label(p1 ?? p0) },
		}
	})

	return (
		<main>
			<Smooth />
			<LandingMotion />
			<Hero radar={season} track="066 D" facts={facts} />
			<Stories cards={cards} />
			<MapPreview />
			<SiteFooter />
		</main>
	)
}
