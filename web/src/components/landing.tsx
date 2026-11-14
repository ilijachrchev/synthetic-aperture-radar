import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { HERO } from '@/content/landing'
import { STORIES } from '@/content/stories'
import { type Film, MonitorStage } from './monitor'
import { PillNav } from './pill-nav'
import { Smoke } from './smoke'
import { StoryLink } from './story-link'
import './landing.css'

/** The stories as the monitor plays them: a film of each real 3D page, made by scripts/landing_films.py. */
const FILMS: Film[] = STORIES.map((s) => ({
	key: s.key,
	tab: s.tab,
	title: s.title,
	place: s.place,
	path: s.path,
	src: `/films${s.path}.mp4`,
	poster: `/films${s.path}.jpg`,
	still: `/films${s.path}-still.jpg`,
}))

/**
 * The landing in one piece: the line and the two things to do, centred on a lagoon panel with slow water in it, and
 * under them the app on a monitor. The monitor pins as the page scrolls and the stories play on its screen, each one
 * a film of its real 3D map page; the pill navbar floats above it all and lights the story on screen.
 */
export function Hero() {
	return (
		<section className="hx">
			<div className="hx-bg" aria-hidden>
				<Smoke className="hx-smoke" />
			</div>
			<PillNav stories={FILMS.map((f) => ({ key: f.key, tab: f.tab }))} />
			<div className="hx-head">
				<h1 className="display hx-title">
					{HERO.lines.map((l, i) => (
						<span key={l} className="hx-line">
							{i > 0 ? ' ' : ''}
							{l}
						</span>
					))}
				</h1>
				<p className="lead hx-lead" data-a>
					{HERO.lead}
				</p>
				<div className="hx-cta" data-a>
					<Link href={STORIES[0].path} className="btn">
						<span className="btn-dot">
							<ArrowUpRight size={18} strokeWidth={2.4} />
						</span>
						Open the map
					</Link>
					<StoryLink className="btn-ghost">See the stories</StoryLink>
				</div>
			</div>
			<MonitorStage films={FILMS} />
		</section>
	)
}
