import { ArrowUpRight, Columns2, Globe2, Play } from 'lucide-react'
import Link from 'next/link'
import { HERO, MAP_HEAD, STORIES_HEAD } from '@/content/landing'
import { LivingRadar } from './living-radar'
import { SiteNav } from './site-nav'
import './landing.css'

function Marked({ text, mark }: { text: string; mark: string }) {
	const at = text.lastIndexOf(mark)
	if (at < 0) return <>{text}</>
	return (
		<>
			{text.slice(0, at)}
			<span className="mark">{mark}</span>
			{text.slice(at + mark.length)}
		</>
	)
}

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
								<Marked text={l} mark={HERO.mark} />
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

export type StoryCardData = { key: string; title: string; what: string; kind: string; where: string; coverage: string; before: { img: string; label: string }; after: { img: string; label: string } }

/** Four cards, one per story: the real after-pass, the pass before on hover, the 3D icon, one line. */
export function Stories({ cards }: { cards: StoryCardData[] }) {
	return (
		<section id="stories" className="sx">
			<div className="sx-head">
				<h2 className="display sx-title">{STORIES_HEAD.title}</h2>
				<p className="lead" data-a>
					{STORIES_HEAD.line}
				</p>
			</div>
			<div className="sx-grid" data-a-group>
				{cards.map((c) => (
					<Link key={c.key} href={`/map?story=${c.key}`} className="sc" data-a>
						<div className="sc-img">
							<img src={c.before.img} alt={`NISAR, ${c.where}, ${c.before.label}`} loading="lazy" />
							<img className="sc-after" src={c.after.img} alt={`NISAR, ${c.where}, ${c.after.label}`} loading="lazy" />
							<span className="sc-tag sc-tag-after mono">{c.after.label}</span>
							<span className="sc-tag sc-tag-before mono">{c.before.label}</span>
						</div>
						<img className="sc-icon" src={`/img/icons/${c.key}.webp`} alt="" width={96} height={96} loading="lazy" />
						<div className="sc-body">
							<p className="mono sc-kind">{c.kind}</p>
							<h3 className="display">{c.title}</h3>
							<p className="sc-what">{c.what}</p>
							<p className="mono sc-meta">
								{c.where} · {c.coverage}
							</p>
						</div>
						<span className="sc-go" aria-hidden>
							<ArrowUpRight size={18} strokeWidth={2.2} />
						</span>
					</Link>
				))}
			</div>
		</section>
	)
}

const ICONS = [Play, Columns2, Globe2]

/** The app, shown as itself: a real screenshot in a browser window, in the palette that is on. */
export function MapPreview() {
	return (
		<section id="map" className="mx">
			<div className="sx-head">
				<h2 className="display sx-title">
					{MAP_HEAD.lines.map((l) => (
						<span key={l} className="hx-line">
							<Marked text={l} mark={MAP_HEAD.mark} />
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
					{['1', '2', '3'].map((p) => (
						<img key={p} className="mx-shot" data-p={p} src={`/img/app/app-${p}.webp`} alt={p === '2' ? 'The map app: the Albufera radar over a satellite map, with the stories, the pass card and the season timeline' : ''} width={1440} height={900} loading="lazy" />
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
