import Link from 'next/link'
import { SITE } from '@/content/site'
import { Mark } from './brand'
import { HalftoneLand } from './halftone-land'
import './site-footer.css'

// The footer, ported from 8x.social: a light card rising over the dark close with its top corners rounded, the
// brand and one line on the left, three link columns on the right, a hairline bar, then a halftone land with
// drifting mist and the giant wordmark climbing over it. Colours follow this site's two themes.
const COLUMNS = [
	{
		title: 'Landing',
		links: [
			{ label: 'Overview', href: '/' },
			{ label: 'Stories', href: '/#stories' },
			{ label: 'Open the map', href: '/map' },
		],
	},
	{
		title: 'The map',
		links: [
			{ label: 'Albufera', href: '/map?story=water' },
			{ label: 'Pego-Oliva marsh', href: '/map?story=water' },
			{ label: "Serra d'Espadà", href: '/map?story=fire' },
			{ label: 'Lorca', href: '/map?story=sink' },
			{ label: 'Panama', href: '/map?story=quake' },
		],
	},
	{
		title: 'Project',
		links: [
			{ label: 'GitHub', href: SITE.repo, out: true },
			{ label: 'The challenge', href: SITE.challenge, out: true },
			{ label: 'NISAR data guide', href: 'https://nisar-docs.asf.alaska.edu/', out: true },
			{ label: 'Use of SI', href: `${SITE.repo}#use-of-super-intelligence-si`, out: true },
		],
	},
]

function GitHubIcon() {
	return (
		<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
			<path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.53-1.33-1.28-1.69-1.28-1.69-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.56-.29-5.25-1.28-5.25-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.39-5.27 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
		</svg>
	)
}
function GlobeIcon() {
	return (
		<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
			<circle cx="12" cy="12" r="9.5" />
			<path d="M2.5 12h19M12 2.5c2.6 2.6 3.9 5.8 3.9 9.5s-1.3 6.9-3.9 9.5c-2.6-2.6-3.9-5.8-3.9-9.5S9.4 5.1 12 2.5Z" />
		</svg>
	)
}
function DataIcon() {
	return (
		<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
			<ellipse cx="12" cy="5.5" rx="8" ry="3" />
			<path d="M4 5.5v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6M4 11.5v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
		</svg>
	)
}

export function SiteFooter() {
	return (
		<footer className="foot8">
			<div className="foot8-card">
				<div className="foot8-top">
					<div className="foot8-brand">
						<Link href="/" className="foot8-lockup">
							<Mark size={26} />
							<span className="display">{SITE.name}</span>
						</Link>
						<p className="foot8-line">Watching Earth&apos;s surface flood, grow, burn and sink, seen by NASA-ISRO NISAR radar.</p>
						<ul className="foot8-social">
							<li>
								<a href={SITE.repo} target="_blank" rel="noopener noreferrer" aria-label="Source code on GitHub">
									<GitHubIcon />
								</a>
							</li>
							<li>
								<a href={SITE.challenge} target="_blank" rel="noopener noreferrer" aria-label="The Space Apps challenge">
									<GlobeIcon />
								</a>
							</li>
							<li>
								<a href="https://search.asf.alaska.edu/" target="_blank" rel="noopener noreferrer" aria-label="NISAR data on ASF Vertex">
									<DataIcon />
								</a>
							</li>
						</ul>
					</div>
					<nav className="foot8-links" aria-label="Footer">
						{COLUMNS.map((c) => (
							<div key={c.title} className="foot8-group">
								<p className="foot8-title">{c.title}</p>
								<ul>
									{c.links.map((l) =>
										'out' in l && l.out ? (
											<li key={l.label}>
												<a href={l.href} target="_blank" rel="noopener noreferrer">
													{l.label}
												</a>
											</li>
										) : (
											<li key={l.label}>
												<Link href={l.href}>{l.label}</Link>
											</li>
										),
									)}
								</ul>
							</div>
						))}
					</nav>
				</div>
				<div className="foot8-bar">
					<p>© 2026 {SITE.name} · NASA Space Apps Challenge, Valencia</p>
					<ul>
						<li>NISAR data: NASA-ISRO via ASF DAAC</li>
						<li>Not endorsed by NASA</li>
					</ul>
				</div>
				<div className="foot8-land">
					<HalftoneLand className="foot8-canvas" />
				</div>
				<div className="foot8-mark" aria-hidden>
					<span>{SITE.name}</span>
				</div>
			</div>
		</footer>
	)
}
