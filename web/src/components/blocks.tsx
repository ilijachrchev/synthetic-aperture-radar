import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { CTA, DATA, MODELS } from '@/content/landing'
import { SITE } from '@/content/site'
import { Title } from './title'
import './blocks.css'

/** 8x.business's "Run it yourself. Or let us." cards, three of them: one per model, its question as the title. */
export function Models() {
	return (
		<section id="models" className="blk">
			<div className="blk-head">
				<Title lines={MODELS.lines} accent={MODELS.accent} className="blk-title" />
				<p className="lead blk-line" data-rise>
					{MODELS.line}
				</p>
			</div>
			<div className="mdl">
				{MODELS.cards.map((c, i) => (
					<article key={c.tag} className="mdl-card" data-rise style={{ ['--d' as string]: `${i * 90}ms` }}>
						<p className="mono mdl-tag">
							<span>{String(i + 1).padStart(2, '0')}</span> {c.tag}
						</p>
						<h3 className="display">{c.short}</h3>
						<p className="mdl-q">{c.q}</p>
						<ul className="mdl-chips">
							{c.chips.map((ch) => (
								<li key={ch}>{ch}</li>
							))}
						</ul>
						<p className="mdl-out">
							<span>Delivers</span>
							{c.delivers}
						</p>
					</article>
				))}
			</div>
		</section>
	)
}

/** 8x.social's logo row under "Real people. Real reach.", with the data sources set as wordmarks. */
export function DataSources() {
	return (
		<section id="data" className="blk">
			<div className="blk-head">
				<Title lines={DATA.lines} className="blk-title blk-title-xl" />
			</div>
			<ul className="src">
				{DATA.sources.map((s, i) => (
					<li key={s.name} data-rise style={{ ['--d' as string]: `${i * 60}ms` }}>
						<a href={s.href} target="_blank" rel="noopener noreferrer">
							<b className="display">{s.name}</b>
							<span className="mono">{s.from}</span>
						</a>
					</li>
				))}
			</ul>
			<p className="blk-line blk-line-c" data-rise>
				{DATA.line}
			</p>
		</section>
	)
}

/** 8x.social's "Your category is about to break out." close. */
export function Closing() {
	return (
		<section className="blk cta">
			<Title lines={CTA.lines} accent={CTA.accent} className="cta-title" />
			<p className="lead cta-line" data-rise>
				{CTA.line}
			</p>
			<div className="cta-pills" data-rise style={{ ['--d' as string]: '120ms' }}>
				<Link href="/map" className="pill">
					<span className="pill-dot">
						<ArrowUpRight size={18} strokeWidth={2.2} />
					</span>
					Open the map
				</Link>
				<a href={SITE.repo} className="pill-ghost" target="_blank" rel="noopener noreferrer">
					Source on GitHub <span className="mono">open</span>
				</a>
			</div>
		</section>
	)
}
