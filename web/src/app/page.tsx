import { Closing, DataSources, Models } from '@/components/blocks'
import { Hero } from '@/components/hero'
import { Machine } from '@/components/machine'
import { PassMosaic, type Tile } from '@/components/pass-mosaic'
import { Reveal } from '@/components/reveal'
import { SiteFooter } from '@/components/site-footer'
import { type StoryCard, StoryTabs } from '@/components/story-tabs'
import { Title } from '@/components/title'
import { MACHINE, PASSES, STORIES, STORIES_HEAD } from '@/content/landing'
import { coverage, day, findPass, imaged, RADAR } from '@/lib/radar'

const T0 = Date.parse('2026-06-01')
const T1 = Date.parse('2026-11-01')

export default function Home() {
	const coast = imaged('coast')
	const tiles: Tile[] = coast.map((p) => ({ img: p.img!, date: p.dates[0], label: `${p.track} ${p.dir}`, track: p.track }))

	const cards: StoryCard[] = STORIES.map((s, i) => {
		const passes = s.compare.map((c) => findPass(c.site, c.date, c.track)!).filter(Boolean)
		const span = (d: string[]) => d.map(day).join(' > ')
		const views = passes.map((p, j) => ({
			img: p.img!,
			label: passes.length > 1 ? `${j === 0 ? 'Before' : 'After'} · ${span(p.dates)}` : `Pair · ${span(p.dates)}`,
		}))
		const ref = passes[passes.length - 1]
		const shown = new Set(passes.map((p) => p.dates.at(-1)))
		const ticks = RADAR.sites[s.compare[0].site].passes
			.filter((p) => p.track === ref.track)
			.map((p) => ({ at: Math.min(1, Math.max(0, (Date.parse(p.dates.at(-1)!) - T0) / (T1 - T0))), on: shown.has(p.dates.at(-1)) }))
		return {
			key: s.key,
			n: String(i + 1).padStart(2, '0'),
			tab: s.tab,
			title: s.title,
			what: s.what,
			where: s.where,
			kind: s.kind,
			coverage: coverage(s.site),
			note: s.note,
			views,
			trackLabel: `Track ${ref.track} ${ref.dir}`,
			ticks,
		}
	})

	const one = imaged('coast', '066')
	const radarBacks = [0, 3, 7, one.length - 1].map((i) => one[i].img!)

	return (
		<main>
			<Reveal />
			<Hero />
			<PassMosaic tiles={tiles} line1={PASSES.line1} beats={PASSES.beats} para={PASSES.para} />
			<section id="stories" className="stories-head">
				<Title lines={STORIES_HEAD.lines} className="stories-title" />
				<p className="lead stories-line" data-rise>
					{STORIES_HEAD.line}
				</p>
			</section>
			<StoryTabs stories={cards} />
			<Machine lines={MACHINE.lines} sr={MACHINE.sr} steps={MACHINE.steps} radar={radarBacks} after={MACHINE.after} />
			<Models />
			<DataSources />
			<Closing />
			<SiteFooter />
		</main>
	)
}
