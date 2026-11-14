import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { CLOSE, DATA_HEAD, HOW_HEAD, HOW_LINE, MODELS, SOURCES, STEPS } from '@/content/landing'
import { SITE } from '@/content/site'
import { latest } from '@/lib/radar'
import './sections.css'

/** A centred two-line heading with one accent word, the 8x.business rhythm, then one short line. */
export function Heading({ a, b, accent, line, as: Tag = 'h2' }: { a: string; b?: string; accent: string; line?: string; as?: 'h2' | 'h1' }) {
	return (
		<div className="sec-head" data-reveal="rise">
			<Tag className="sec-title">
				{a}
				<br />
				{b ? `${b} ` : ''}
				<em>{accent}</em>
			</Tag>
			{line && <p className="sec-line">{line}</p>}
		</div>
	)
}

export function How() {
	return (
		<section id="how" className="sec">
			<Heading a={HOW_HEAD.a} accent={HOW_HEAD.accent} line={HOW_LINE} />
			<ol className="steps">
				{STEPS.map((s, i) => (
					<li key={s.title} data-reveal="rise" style={{ ['--r' as string]: i * 3 }}>
						<span className="step-n">{String(i + 1).padStart(2, '0')}</span>
						<span className="step-rule" data-reveal="line" />
						<h3>{s.title}</h3>
						<p>{s.line}</p>
					</li>
				))}
			</ol>
			<div className="models" data-reveal="rise">
				<p className="models-lead">Three models do the work</p>
				<ul>
					{MODELS.map((m) => (
						<li key={m.name}>
							<b>{m.name}</b> {m.line}
						</li>
					))}
				</ul>
			</div>
		</section>
	)
}

export function Data() {
	return (
		<section id="data" className="sec">
			<Heading a={DATA_HEAD.a} accent={DATA_HEAD.accent} line="NASA's free and open data first, with partner data to check it." />
			<ul className="sources">
				{SOURCES.map((s, i) => (
					<li key={s.name} data-reveal="rise" style={{ ['--r' as string]: i * 2 }}>
						<a href={s.href} target="_blank" rel="noopener noreferrer">
							<b>{s.name}</b>
							<span>{s.what}</span>
							<i>{s.from}</i>
							<ArrowUpRight size={18} strokeWidth={1.6} aria-hidden />
						</a>
					</li>
				))}
			</ul>
		</section>
	)
}

/** The close is the radar itself, so it never repeats the hero's photograph. */
export function Closing() {
	const frame = latest('valencia', '066')
	return (
		<section className="close">
			{frame?.img && <img className="close-radar" src={frame.img} alt="NISAR radar view of the Valencia coast, latest pass" loading="lazy" />}
			<div className="close-copy">
				<h2>
					{CLOSE.a}
					<br />
					<em>{CLOSE.accent}</em>
				</h2>
				<p>{CLOSE.line}</p>
				<div className="close-buttons">
					<Link href="/map" className="close-pill">
						Open the map
						<span>
							<ArrowUpRight size={16} strokeWidth={2} />
						</span>
					</Link>
					<a href={SITE.repo} className="close-ghost" target="_blank" rel="noopener noreferrer">
						Source on GitHub
					</a>
				</div>
			</div>
		</section>
	)
}
