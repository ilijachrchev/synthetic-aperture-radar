'use client'

import Link from 'next/link'
import { storyNav } from '@/lib/story-nav'

/** A link to one of the stories on the monitor: it scrolls straight to that story playing (the anchor is the fallback). */
export function StoryLink({ to = 0, className, children }: { to?: number; className?: string; children: React.ReactNode }) {
	return (
		<Link
			href="/#stories"
			className={className}
			onClick={(e) => {
				e.preventDefault()
				e.stopPropagation()
				storyNav.go(to)
			}}
		>
			{children}
		</Link>
	)
}
