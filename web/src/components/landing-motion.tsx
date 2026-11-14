'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP)

/**
 * The landing's motion outside the pinned stories (story-scroll.tsx), on GSAP. The hero's line rises word by word, its
 * two buttons follow, and the monitor with the dashboard rises in below them, its top half in view; scrolling tips it
 * up flat and brings all of it into view. Section heads rise the same way. Transform and opacity only; the scroll is
 * Lenis (smooth.tsx).
 */
export function LandingMotion() {
	useGSAP(() => {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
			gsap.set('[data-a], .hx-title, .sx-title, .hx-mon', { opacity: 1, clearProps: 'transform' })
			return
		}

		const titles = (sel: string, opts: (h: HTMLElement) => gsap.TimelineVars) =>
			gsap.utils.toArray<HTMLElement>(sel).forEach((h) => {
				const split = SplitText.create(h, { type: 'words', mask: 'words' })
				gsap.set(h, { opacity: 1 })
				gsap.timeline(opts(h)).from(split.words, { yPercent: 115, duration: 1.15, ease: 'expo.out', stagger: 0.06 })
			})

		// the hero arrives: the line, then the two buttons, then the monitor rising into its place under them
		titles('.hx-title', () => ({ delay: 0.1 }))
		gsap.fromTo('.hx [data-a]', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 1.1, ease: 'expo.out', stagger: 0.1, delay: 0.4 })
		gsap.fromTo('.hx-mon', { opacity: 0, y: 120 }, { opacity: 1, y: 0, duration: 1.6, ease: 'expo.out', delay: 0.3 })

		// as the page scrolls the monitor tips up from a slight lean, grows a touch and comes fully into view
		gsap.fromTo('.mon', { rotateX: 16, scale: 0.92 }, { rotateX: 0, scale: 1, ease: 'none', scrollTrigger: { trigger: '.hx-mon', start: 'top 85%', end: 'top 12%', scrub: true } })

		// section heads and their lines
		titles('.sx-title', (h) => ({ scrollTrigger: { trigger: h, start: 'top 86%', once: true } }))
		gsap.utils.toArray<HTMLElement>('.sx-head [data-a]').forEach((el) => {
			gsap.fromTo(el, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 1.1, ease: 'expo.out', delay: 0.25, scrollTrigger: { trigger: el, start: 'top 90%', once: true } })
		})
	})
	return null
}
