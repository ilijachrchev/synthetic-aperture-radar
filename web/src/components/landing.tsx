import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { HERO, HOW, MORE, TOUR_FILM } from '@/content/landing'
import { SITE } from '@/content/site'
import { STORIES } from '@/content/stories'
import TOLL from '@/data/dana_2024_toll.json'
import { AnchorLink } from './anchor-link'
import { type Film, MonitorStage } from './monitor'
import { SiteNav } from './site-nav'
import { Smoke } from './smoke'
import { ThemeSwitch } from './theme-switch'
import './landing.css'

/** The one film of the monitor: the guided tour's streets step (official map, then our simulation), recorded from the running app (scripts/landing_films.py). */
const FILMS: Film[] = [TOUR_FILM]

/**
 * The landing in one piece: the hook (the line, the toll of the 2024 flood with its sources, one button to the flood
 * map), centred on a lagoon panel with slow water in it, and under it the app on a monitor, playing the guided tour as
 * it runs: the streets that flooded outside every official zone, then the official map against our simulation. The
 * small navbar floats above it all.
 */
export function Hero() {
	return (
		<section className="hx">
			<div className="hx-bg" aria-hidden>
				<Smoke className="hx-smoke" />
			</div>
			<SiteNav variant="pill" end={<ThemeSwitch />} />
			<div className="hx-head">
				<h1 className="display hx-title hx-name">{HERO.name}</h1>
				<p className="hx-tagline" data-a>
					{HERO.tagline}
				</p>
				<p className="hx-small" data-a>
					{HERO.small}
				</p>
				<p className="hx-hook" data-a>
					{HERO.lines.join(' ')}
				</p>
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
					<AnchorLink to="more" className="btn-ghost">
						{HERO.stories}
					</AnchorLink>
				</div>
			</div>
			<MonitorStage films={FILMS} />
		</section>
	)
}

/** Under the monitor: the 3D story pages, nothing lost now that their films left it. */
export function MoreStories() {
	return (
		<section id="more" className="mr">
			<div className="mr-head">
				<h2 className="display mr-title">{MORE.title}</h2>
				<p>{MORE.line}</p>
			</div>
			<ul className="mr-list">
				{STORIES.map((s) => (
					<li key={s.key}>
						<Link href={s.path} className="mr-card">
							{/* eslint-disable-next-line @next/next/no-img-element */}
							<img src={`/films${s.path}-still.jpg`} alt="" width={1280} height={720} loading="lazy" />
							<span className="mr-text">
								<b>{s.title}</b>
								<small>{s.place}</small>
							</span>
							<span className="mr-go">
								{MORE.open} <ArrowUpRight size={15} strokeWidth={2.4} />
							</span>
						</Link>
					</li>
				))}
			</ul>
		</section>
	)
}

/** How it works, in four short lines: the target of the navbar's "How it works". */
export function HowItWorks() {
	return (
		<section id="how" className="hw">
			<h2 className="display hw-title">{HOW.title}</h2>
			<ol className="hw-list">
				{HOW.items.map((it, i) => (
					<li key={it.title}>
						<span className="mono hw-n">{String(i + 1).padStart(2, '0')}</span>
						<b>{it.title}</b>
						<p>{it.text}</p>
					</li>
				))}
			</ol>
			<a className="hw-repo" href={SITE.repo} target="_blank" rel="noopener noreferrer">
				{HOW.repo} <ArrowUpRight size={15} strokeWidth={2.4} />
			</a>
		</section>
	)
}
