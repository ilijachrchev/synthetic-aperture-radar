import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { HERO, STORIES } from '@/content/landing'
import type { StoryCfg } from './map/map-app'
import { MonitorStage } from './monitor'
import { PillNav } from './pill-nav'
import { Smoke } from './smoke'
import { StoryLink } from './story-link'
import type { Chapter } from './story-scroll'
import './landing.css'

/**
 * The landing in one piece: the line and the two things to do, centred on a lagoon panel with slow water in it, and
 * under them the dashboard on a monitor. The monitor pins as the page scrolls and the four stories play on its screen;
 * the pill navbar floats above it all and lights the story on screen.
 */
export function Hero({ stories, chapters }: { stories: StoryCfg[]; chapters: Chapter[] }) {
	return (
		<section className="hx">
			<div className="hx-bg" aria-hidden>
				<Smoke className="hx-smoke" />
			</div>
			<PillNav stories={STORIES.map((s) => ({ key: s.key, tab: s.tab }))} />
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
					<StoryLink className="btn-ghost">See the stories</StoryLink>
				</div>
			</div>
			<MonitorStage stories={stories} chapters={chapters} />
		</section>
	)
}
