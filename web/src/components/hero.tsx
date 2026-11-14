import { ArrowUpRight, Radio } from 'lucide-react'
import { getImageProps } from 'next/image'
import Link from 'next/link'
import { HERO } from '@/content/landing'
import { datesWithCounts, day, imaged, latest, RADAR } from '@/lib/radar'
import { SiteNav } from './site-nav'
import { Title } from './title'
import './hero.css'

const ALT = 'Flooded rice paddies of the Albufera with a thatched barraca, an SI-generated photo illustration'

// One photograph, two lights: dawn by day, dusk by night, each with a 9:16 cut for phones. The SI mark is baked into
// the bottom centre of every file, which no crop and no text here ever covers.
function Photo({ light }: { light: 'day' | 'dusk' }) {
	const common = { alt: light === 'day' ? ALT : '', sizes: '(max-width: 1000px) 100vw, 50vw', quality: 85 }
	const {
		props: { srcSet: wide },
	} = getImageProps({ ...common, src: `/img/hero-${light}-v2.webp`, width: 2560, height: 1429 })
	const {
		props: { srcSet: tall, ...rest },
	} = getImageProps({ ...common, src: `/img/hero-${light}-tall-v2.webp`, width: 864, height: 1536, fetchPriority: light === 'day' ? 'high' : 'auto' })
	return (
		<picture className={`hero-pic hero-pic-${light}`}>
			<source media="(max-width: 1000px)" srcSet={tall} />
			<source srcSet={wide} />
			<img {...rest} src={rest.src} alt={common.alt} />
		</picture>
	)
}

export function Hero() {
	const passes = RADAR.sites.albufera.passes
	const first = datesWithCounts('albufera')[0].date
	const last = latest('coast', '066')
	const thumbs = imaged('coast', '066').filter((_, i, a) => i === 0 || i === Math.floor(a.length / 2) || i === a.length - 1)

	return (
		<section className="hero" aria-label="Introduction">
			<SiteNav />
			<div className="hero-stage">
				<div className="hero-photo">
					<Photo light="day" />
					<Photo light="dusk" />
				</div>

				<div className="hero-stat" data-rise style={{ ['--d' as string]: '200ms' }}>
					<p className="display hero-stat-n">{passes.length}</p>
					<p className="hero-stat-l">
						NISAR passes over the
						<br />
						Albufera since {day(first)}
					</p>
					<span className="hero-thumbs" aria-hidden>
						{thumbs.map((p) => (
							<img key={p.img} src={p.img!} alt="" width={34} height={34} />
						))}
					</span>
				</div>

				{last?.img && (
					<div className="hero-pass" data-rise style={{ ['--d' as string]: '520ms' }}>
						<img src={last.img} alt="" width={44} height={44} />
						<div>
							<p>
								<Radio size={13} strokeWidth={2.2} aria-hidden /> Latest NISAR pass
							</p>
							<p className="mono">
								{day(last.dates[0])} 2026 · track {last.track} {last.dir}
							</p>
						</div>
					</div>
				)}

				<div className="hero-side" data-rise style={{ ['--d' as string]: '320ms' }}>
					<p className="lead">{HERO.lead}</p>
					<a className="hero-src" href={HERO.source.href} target="_blank" rel="noopener noreferrer">
						Data: <span>{HERO.source.label}</span>
					</a>
				</div>

				<Title as="h1" lines={HERO.lines} accent={HERO.accent} className="hero-title" />

				<div className="hero-cta" data-rise style={{ ['--d' as string]: '420ms' }}>
					<Link href="/map" className="pill">
						<span className="pill-dot">
							<ArrowUpRight size={18} strokeWidth={2.2} />
						</span>
						Open the map
					</Link>
					<Link href="/#how" className="pill-ghost">
						How it works <span className="mono">4 steps</span>
					</Link>
				</div>
			</div>
		</section>
	)
}
