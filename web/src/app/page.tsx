import { AppPreview } from '@/components/app-preview'
import { Hero } from '@/components/hero'
import { Closing, Data, How } from '@/components/sections'
import { SiteFooter } from '@/components/site-footer'
import { StoriesFlow, type StoryView } from '@/components/stories-flow'
import { PASSES_HEAD, PASSES_LINE, STORIES, STORIES_HEAD, STORIES_LINE } from '@/content/landing'
import { coverage, findPass, imaged } from '@/lib/radar'

export default function Home() {
	const stories: StoryView[] = STORIES.map((s) => {
		const p = findPass(s.site, s.show.date, s.show.track)
		return {
			key: s.key,
			title: s.title,
			what: s.what,
			where: s.where,
			kind: s.kind,
			coverage: coverage(s.site),
			img: p?.img ?? null,
			passLabel: p ? `${p.dates.join(' > ')} · track ${p.track} ${p.dir}` : '',
		}
	})
	return (
		<main className="grain min-h-svh">
			<Hero />
			<StoriesFlow stories={stories} head={STORIES_HEAD} line={STORIES_LINE} />
			<AppPreview passes={imaged('valencia', '066')} head={PASSES_HEAD} line={PASSES_LINE} />
			<How />
			<Data />
			<Closing />
			<SiteFooter />
		</main>
	)
}
