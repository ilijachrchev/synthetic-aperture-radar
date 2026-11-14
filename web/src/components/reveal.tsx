'use client'

import { useEffect } from 'react'

/** One observer for the page: headings with data-words and blocks with data-rise get data-in once they are in view. */
export function Reveal() {
	useEffect(() => {
		const io = new IntersectionObserver(
			(entries) => {
				for (const e of entries) {
					if (e.isIntersecting) {
						e.target.setAttribute('data-in', '')
						io.unobserve(e.target)
					}
				}
			},
			{ rootMargin: '0px 0px -12% 0px' },
		)
		const watch = () => document.querySelectorAll('[data-words]:not([data-in]), [data-rise]:not([data-in])').forEach((n) => io.observe(n))
		watch()
		const mo = new MutationObserver(watch)
		mo.observe(document.body, { childList: true, subtree: true })
		return () => {
			io.disconnect()
			mo.disconnect()
		}
	}, [])
	return null
}
