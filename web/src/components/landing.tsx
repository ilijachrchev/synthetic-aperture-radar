import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { HERO, STORIES, STORIES_HEAD } from '@/content/landing'
import { MapApp, type StoryCfg } from './map/map-app'
import { SiteNav } from './site-nav'
import { type Chapter, StoryScroll } from './story-scroll'
import './landing.css'

/**
 * The hero: one line, the way into the app and straight to each story, and under it the app itself, live and half in
 * view, growing to fill the screen as the page scrolls (landing-motion). What is shown, where and when sits on top.
 */
export function Hero({ stories, eyebrow, source }: { stories: StoryCfg[]; eyebrow: string; source: { label: string; href: string } }) {
	return (
		<section className="hx">
			<div className="hx-pin">
				<div className="hx-top">
					<SiteNav />
					<div className="hx-head">
						<p className="mono hx-eyebrow" data-a>
							{eyebrow}
						</p>
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
							<nav className="hx-jump" aria-label="Straight to a story">
								{STORIES.map((s) => (
									<Link key={s.key} href={`/map?story=${s.key}`} className="hx-chip">
										<i data-k={s.change.kind} aria-hidden />
										{s.tab}
									</Link>
								))}
							</nav>
						</div>
						<p className="mono hx-source" data-a>
							Data: <a href={source.href}>{source.label}</a>
						</p>
					</div>
				</div>
				<div className="hx-stage">
					<div className="hx-app">
						<MapApp stories={stories} embed />
					</div>
				</div>
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
