import { ArrowUpRight } from 'lucide-react'
import { getImageProps } from 'next/image'
import Link from 'next/link'
import { HERO, NAV } from '@/content/site'
import { coords, datesWithCounts, day, imaged, latest, RADAR } from '@/lib/radar'
import { Brand } from './brand'
import { PulseChart } from './pulse-chart'
import { ThemeToggle } from './theme-toggle'
import './hero.css'

const ALT = 'Flooded rice paddies of the Albufera with a thatched barraca, an SI-generated photo illustration'

// One photograph, two lights: dawn for the day theme, dusk for the night theme, each with a 9:16 cut for phones.
function Photo({ light, className }: { light: 'day' | 'dusk'; className?: string }) {
	const common = { alt: light === 'day' ? ALT : '', sizes: '100vw', quality: 85 }
	const {
		props: { srcSet: wide },
	} = getImageProps({ ...common, src: `/img/hero-${light}-v2.webp`, width: 2560, height: 1429 })
	const {
		props: { srcSet: tall, ...rest },
	} = getImageProps({ ...common, src: `/img/hero-${light}-tall-v2.webp`, width: 864, height: 1536, fetchPriority: light === 'day' ? 'high' : 'auto' })
	return (
		<picture className={className}>
			<source media="(max-aspect-ratio: 4/5)" srcSet={tall} />
			<source srcSet={wide} />
			<img {...rest} src={rest.src} alt={common.alt} />
		</picture>
	)
}

export function Figures() {
	const all = RADAR.sites.albufera.passes
	const dates = datesWithCounts('albufera')
	return (
		<div className="hero-figures">
			<p className="hero-fig-label">Every NISAR pass over the Albufera</p>
			<PulseChart site="albufera" className="hero-chart" />
			<p className="hero-small" style={{ marginTop: 14 }}>
				Wavelength
			</p>
			<p className="hero-big">
				24 <i>cm</i>
			</p>
			<p className="hero-small" style={{ marginTop: 6 }}>
				L-band radar: it sees through cloud, day or night
			</p>
			<div className="hero-stats">
				<div>
					<p className="hero-small">Repeat</p>
					<b>
						12<i>days</i>
					</b>
				</div>
				<div>
					<p className="hero-small">Pixel</p>
					<b>
						20<i>m</i>
					</b>
				</div>
				<div>
					<p className="hero-small">
						Passes since {day(dates[0].date)}
					</p>
					<b>{all.length}</b>
				</div>
			</div>
		</div>
	)
}

export function Hero() {
	const site = RADAR.sites.albufera
	const last = latest('albufera', '066')
	const trio = imaged('albufera', '066').filter((_, i, a) => i === 0 || i === Math.floor(a.length / 2) || i === a.length - 1)
	return (
		<>
			<section className="hero" aria-label="Introduction">
				<div className="hero-media" aria-hidden={false}>
					<Photo light="day" />
					<Photo light="dusk" className="hero-dusk" />
					<div className="hero-scrim" />
					<div className="hero-scrim-night" />
				</div>

				<header className="hero-nav">
					<Brand />
					<nav className="hero-links" aria-label="Sections">
						{NAV.map((n) => (
							<Link key={n.href} href={n.href}>
								{n.label}
							</Link>
						))}
					</nav>
					<div className="hero-actions">
						<ThemeToggle />
						<Link href={HERO.primary.href} className="hero-pill">
							{HERO.primary.label}
							<span className="hero-dot">
								<ArrowUpRight size={16} strokeWidth={2} />
							</span>
						</Link>
					</div>
				</header>

				<h1 className="hero-title">
					<span className="hero-kicker anim-rise">{HERO.kicker}</span>
					<span className="hero-place anim-rise" style={{ ['--d' as string]: '90ms' }}>
						{HERO.place}
					</span>
					<span className="hero-sub anim-rise" style={{ ['--d' as string]: '200ms' }}>
						{HERO.sub}
					</span>
				</h1>

				<div className="hero-place-card">
					{last?.img && <img src={last.img} alt={`NISAR radar view of the Albufera, ${day(last.dates[0])}`} width={66} height={66} />}
					<div>
						<b>Albufera</b>
						<span>Valencia, Spain</span>
						<span>{coords(site.point)}</span>
					</div>
				</div>

				<div className="hero-lead">
					<div className="hero-seen">
						<span className="hero-thumbs">
							{trio.map((p) => (
								<img key={p.img} src={p.img!} alt="" width={30} height={30} />
							))}
						</span>
						<span>
							{HERO.seenBy[0]}
							<br />
							{HERO.seenBy[1]}
						</span>
					</div>
					<p className="hero-lead-text">
						{HERO.lead} <em>{HERO.leadAccent}</em>
					</p>
					<div className="hero-buttons">
						<Link href={HERO.primary.href} className="hero-pill">
							{HERO.primary.label}
							<span className="hero-dot">
								<ArrowUpRight size={16} strokeWidth={2} />
							</span>
						</Link>
						<Link href={HERO.secondary.href} className="hero-ghost">
							{HERO.secondary.label}
						</Link>
					</div>
				</div>

				<Figures />
			</section>
			<div className="hero-strip">
				<Figures />
			</div>
		</>
	)
}
