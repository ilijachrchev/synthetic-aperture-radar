import { ArrowUpRight, Columns2, Globe2, Play } from 'lucide-react'
import Link from 'next/link'
import { HERO, MAP_HEAD, STORIES_HEAD } from '@/content/landing'
import { LivingRadar } from './living-radar'
import { SiteNav } from './site-nav'
import { type Chapter, StoryScroll } from './story-scroll'
import './landing.css'

/** The hero: what it is on the left, the real thing on the right, a season of radar playing by itself. */
export function Hero({ radar, track, facts }: { radar: { img: string; date: string }[]; track: string; facts: string[] }) {
	return (
		<section className="hx">
			<SiteNav />
			<div className="hx-grid">
				<div className="hx-copy">
					<p className="mono hx-eyebrow" data-a>
						{HERO.eyebrow}
					</p>
					<h1 className="display hx-title">
						{HERO.lines.map((l) => (
							<span key={l} className="hx-line">
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
					<ul className="hx-facts" data-a>
						{facts.map((f) => (
							<li key={f}>{f}</li>
						))}
					</ul>
				</div>
				<div className="hx-radar">
					<div className="hx-radar-inner">
						<LivingRadar passes={radar} track={track} />
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

const ICONS = [Play, Columns2, Globe2]

/** The app, shown as itself: a real screenshot in a browser window, in the theme that is on. */
export function MapPreview() {
	return (
		<section id="map" className="mx">
			<div className="sx-head">
				<h2 className="display sx-title">
					{MAP_HEAD.lines.map((l) => (
						<span key={l} className="hx-line">
							{l}
						</span>
					))}
				</h2>
				<p className="lead" data-a>
					{MAP_HEAD.line}
				</p>
			</div>
			<div className="mx-stage">
				<Link href="/map" className="mx-frame" aria-label="Open the map">
					<span className="mx-bar" aria-hidden>
						<i />
						<i />
						<i />
						<span className="mono">dancing-with-the-sars / map</span>
					</span>
					{['light', 'dark'].map((p) => (
						<img key={p} className="mx-shot" data-t={p} src={`/img/app/app-${p}.webp`} alt={p === 'light' ? 'The map app: the Albufera radar over a satellite map, with the stories, the pass card and the season timeline' : ''} width={1440} height={900} loading="lazy" />
					))}
				</Link>
			</div>
			<div className="mx-foot" data-a-group>
				<ul className="mx-cmds">
					{MAP_HEAD.commands.map((c, i) => {
						const Icon = ICONS[i]
						return (
							<li key={c} data-a>
								<Icon size={16} strokeWidth={2.2} /> {c}
							</li>
						)
					})}
				</ul>
				<Link href="/map" className="btn" data-a>
					<span className="btn-dot">
						<ArrowUpRight size={18} strokeWidth={2.4} />
					</span>
					Open the map
				</Link>
			</div>
		</section>
	)
}
