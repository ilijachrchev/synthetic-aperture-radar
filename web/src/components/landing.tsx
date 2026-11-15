import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { HERO } from '@/content/landing'
import { STORIES } from '@/content/stories'
import TOLL from '@/data/dana_2024_toll.json'
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
 * The landing in one piece: the hook (the line, the toll of the 2024 flood with its sources, one button to the flood
 * map), centred on a lagoon panel with slow water in it, and under it the app on a monitor. The monitor pins as the
 * page scrolls and the other NISAR stories play on its screen, each one a film of its real 3D map page; the pill navbar
 * floats above it all and lights the story on screen.
 */
export function Hero() {
	return (
		<section className="hx">
			<div className="hx-bg" aria-hidden>
				<Smoke className="hx-smoke" />
			</div>
			<PillNav stories={FILMS.map((f) => ({ key: f.key, tab: f.tab }))} />
			<div className="hx-head">
				<p className="hx-eyebrow" data-a>
					{HERO.eyebrow}
				</p>
				<h1 className="display hx-title hx-hook">
					{HERO.lines.map((l, i) => (
						<span key={l} className="hx-line">
							{i > 0 ? ' ' : ''}
							{l}
						</span>
					))}
				</h1>
				<div className="hx-toll" data-a>
					<p>
						<b className="display">{TOLL.lives_lost}</b>
						<span>{HERO.toll.lives}</span>
					</p>
					<p>
						<b className="display">€{TOLL.damage_eur_billion} billion</b>
						<span>{HERO.toll.damage}</span>
					</p>
				</div>
				<p className="hx-caption" data-a>
					{HERO.toll.caption}, {TOLL.date}. Sources:{' '}
					{TOLL.sources.map((src, i) => (
						<span key={src.url}>
							{i > 0 ? ', ' : ''}
							<a href={src.url} target="_blank" rel="noopener noreferrer">
								{src.name}
							</a>
						</span>
					))}
				</p>
				<div className="hx-cta" data-a>
					<Link href={HERO.primary.href} className="btn">
						<span className="btn-dot">
							<ArrowUpRight size={18} strokeWidth={2.4} />
						</span>
						{HERO.primary.label}
					</Link>
					<StoryLink className="btn-ghost">{HERO.stories}</StoryLink>
				</div>
			</div>
			<MonitorStage films={FILMS} />
		</section>
	)
}
