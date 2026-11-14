import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { CLOSE, DATA_HEAD, HOW_HEAD, HOW_LINE, MODELS, SOURCES, STEPS, STORIES, STORIES_HEAD, STORIES_LINE } from '@/content/landing'
import { SITE } from '@/content/site'
import { coverage, findPass, latest } from '@/lib/radar'
import { Brand } from './brand'
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

export function Stories() {
	return (
		<section id="stories" className="sec">
			<Heading a={STORIES_HEAD.a} b={STORIES_HEAD.b} accent={STORIES_HEAD.accent} line={STORIES_LINE} />
			<div className="stories">
				{STORIES.map((st, i) => {
					const pass = findPass(st.site, st.show.date, st.show.track)
					const label = pass ? `${pass.dates.join(' > ')} · track ${pass.track} ${pass.dir}` : ''
					return (
						<Link key={st.key} href={`/map?story=${st.key}`} className="story" data-reveal="rise" style={{ ['--r' as string]: i * 4 }}>
							<div className="story-radar">
								{pass?.img && <img src={pass.img} alt={`NISAR ${st.kind.toLowerCase()} over ${st.where}`} loading="lazy" />}
								<span className="story-pass">{label}</span>
							</div>
							<img className="story-icon" src={`/img/icons/${st.key}.webp`} alt="" width={132} height={132} loading="lazy" />
							<div className="story-body">
								<h3>{st.title}</h3>
								<p>{st.what}</p>
								<dl>
									<div>
										<dt>Where</dt>
										<dd>{st.where}</dd>
									</div>
									<div>
										<dt>NISAR</dt>
										<dd>{coverage(st.site)}</dd>
									</div>
								</dl>
							</div>
						</Link>
					)
				})}
			</div>
		</section>
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
		<section className="close" data-reveal="open">
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

export function Footer() {
	return (
		<footer className="foot">
			<div className="foot-row">
				<Brand />
				<nav aria-label="Footer">
					<a href={SITE.challenge} target="_blank" rel="noopener noreferrer">
						The challenge
					</a>
					<a href={SITE.repo} target="_blank" rel="noopener noreferrer">
						GitHub
					</a>
					<Link href="/map">Map</Link>
				</nav>
			</div>
			<div className="foot-notes">
				<p>NASA Space Apps Challenge 2026 · Valencia, Spain. NISAR is a joint mission of NASA and ISRO; data courtesy of NASA&apos;s Alaska Satellite Facility DAAC. This project is not endorsed by NASA.</p>
				<p>Images marked &ldquo;SI-generated&rdquo; were made with Gemini. Radar images are real NISAR previews. Research and code were drafted with an SI assistant; the idea and the decisions are the team&apos;s.</p>
			</div>
		</footer>
	)
}
