import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { Brand } from './brand'
import { ThemeSwitch } from './theme-switch'
import './site-nav.css'

export function SiteNav() {
	return (
		<header className="snav">
			<Brand />
			<nav className="snav-links" aria-label="Sections">
				<Link href="/#stories">Stories</Link>
				<Link href="/#map">The map</Link>
			</nav>
			<div className="snav-end">
				<ThemeSwitch />
				<Link href="/map" className="btn snav-cta">
					<span className="btn-dot">
						<ArrowUpRight size={15} strokeWidth={2.4} />
					</span>
					Open the map
				</Link>
			</div>
		</header>
	)
}
