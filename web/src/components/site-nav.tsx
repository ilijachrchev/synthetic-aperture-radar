import { Activity, ArrowUpRight, Database, Layers, Workflow } from 'lucide-react'
import Link from 'next/link'
import { Brand } from './brand'
import { ThemeToggle } from './theme-toggle'
import './site-nav.css'

const LINKS = [
	{ label: 'Passes', href: '/#passes', Icon: Activity },
	{ label: 'Stories', href: '/#stories', Icon: Layers },
	{ label: 'How it works', href: '/#how', Icon: Workflow },
	{ label: 'Data', href: '/#data', Icon: Database },
]

// 8x.social's bar: the lockup left, the links in one glass pill in the middle, the action on the right.
export function SiteNav() {
	return (
		<header className="snav">
			<Brand />
			<nav className="snav-links" aria-label="Sections">
				{LINKS.map(({ label, href, Icon }) => (
					<Link key={href} href={href}>
						<Icon size={15} strokeWidth={1.9} aria-hidden />
						{label}
					</Link>
				))}
			</nav>
			<div className="snav-end">
				<ThemeToggle />
				<Link href="/map" className="snav-cta">
					<span className="snav-cta-dot">
						<ArrowUpRight size={15} strokeWidth={2.2} />
					</span>
					Open the map
				</Link>
			</div>
		</header>
	)
}
