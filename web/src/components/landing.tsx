import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { HERO, STORIES_HEAD } from '@/content/landing'
import type { StoryCfg } from './map/map-app'
import { Monitor } from './monitor'
import { SiteNav } from './site-nav'
import { Smoke } from './smoke'
import { type Chapter, StoryScroll } from './story-scroll'
import './landing.css'

/**
 * The hero: the line and the two things to do, centred on a rounded lagoon panel with slow water moving in it, and the
 * dashboard on a monitor resting on the panel's lower edge, rising into full view as the page scrolls.
 */
export function Hero({ stories }: { stories: StoryCfg[] }) {
	return (
		<section className="hx">
			<div className="hx-bg" aria-hidden>
				<Smoke className="hx-smoke" />
			</div>
			<SiteNav />
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
					<Link href="/map" className="btn">
						<span className="btn-dot">
							<ArrowUpRight size={18} strokeWidth={2.4} />
						</span>
						Open the map
					</Link>
					<Link href="/#stories" className="btn-ghost">
						See the stories
					</Link>
				</div>
			</div>
			<div className="hx-mon">
				<Monitor stories={stories} />
			</div>
		</section>
	)
}

/** The four stories: a short head, then the pinned stage where scrolling plays each season on the real passes. */
export function Stories({ chapters }: { chapters: Chapter[] }) {
	return (
		<section id="stories" className="st">
			<div className="sx-head">
				<h2 className="display sx-title">{STORIES_HEAD.title}</h2>
				<p className="lead" data-a>
					{STORIES_HEAD.line}
				</p>
			</div>
			<StoryScroll chapters={chapters} />
		</section>
	)
}
