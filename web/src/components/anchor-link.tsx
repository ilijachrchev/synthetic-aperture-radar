'use client'

// A link to a section of this page that glides there with the page's smooth scroll (Lenis), or jumps without it.

import { lenisRef } from './smooth'

export function AnchorLink({ to, className, children }: { to: string; className?: string; children: React.ReactNode }) {
	return (
		<a
			href={`#${to}`}
			className={className}
			onClick={(e) => {
				const el = document.getElementById(to)
				if (!el || !lenisRef.current) return
				e.preventDefault()
				lenisRef.current.scrollTo(el, { duration: 1.4, offset: -80 })
			}}
		>
			{children}
		</a>
	)
}
