'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP)

/**
 * The landing's motion outside the pinned stories (story-scroll.tsx), on GSAP. The hero's line rises word by word and
 * its buttons follow; the live app waits half in view under it, and scrolling grows it to fill the screen (tilted
 * back a touch at first, flat and edge to edge at the end) while the line and the nav lift away. Section heads rise
 * the same way. Transform and opacity only; the scroll is Lenis (smooth.tsx).
 */
export function LandingMotion() {
	useGSAP(() => {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
			gsap.set('[data-a], .hx-title, .sx-title, .hx-stage', { opacity: 1, clearProps: 'transform' })
			return
		}

		const titles = (sel: string, opts: (h: HTMLElement) => gsap.TimelineVars) =>
			gsap.utils.toArray<HTMLElement>(sel).forEach((h) => {
				const split = SplitText.create(h, { type: 'words', mask: 'words' })
				gsap.set(h, { opacity: 1 })
				gsap.timeline(opts(h)).from(split.words, { yPercent: 115, duration: 1.15, ease: 'expo.out', stagger: 0.06 })
			})

		// the hero arrives: the line, then the ways in, then the app rising into its place under them
		titles('.hx-title', () => ({ delay: 0.1 }))
		gsap.fromTo('.hx [data-a]', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 1.1, ease: 'expo.out', stagger: 0.08, delay: 0.4 })
		gsap.fromTo('.hx-stage', { opacity: 0, y: 90 }, { opacity: 1, y: 0, duration: 1.6, ease: 'expo.out', delay: 0.35 })

		// the reveal: half in view under the line, then edge to edge as the page scrolls
		const app = document.querySelector<HTMLElement>('.hx-app')
		const head = document.querySelector<HTMLElement>('.hx-head')
		if (app && head) {
			const phone = () => window.innerWidth < 640
			const edge = () => (phone() ? 8 : 14)
			// where it rests: just under the buttons, and never lower than three quarters down the screen
			const rest = () => Math.min(window.innerHeight * 0.74, head.offsetTop + head.offsetHeight + (phone() ? 22 : 34))
			gsap
				.timeline({ scrollTrigger: { trigger: '.hx', start: 'top top', end: 'bottom bottom', scrub: true, invalidateOnRefresh: true } })
				.fromTo(app, { y: rest, scale: () => (phone() ? 0.9 : 0.8), rotateX: () => (phone() ? 6 : 12) }, { y: edge, scale: 1, rotateX: 0, ease: 'power1.inOut', duration: 0.78 }, 0)
				.to('.hx-top', { y: -110, autoAlpha: 0, ease: 'power1.in', duration: 0.42 }, 0)
				// the app holds the whole screen for a beat before the page moves on
				.to({}, { duration: 0.22 })
		}

		// section heads and their lines
		titles('.sx-title', (h) => ({ scrollTrigger: { trigger: h, start: 'top 86%', once: true } }))
		gsap.utils.toArray<HTMLElement>('.sx-head [data-a]').forEach((el) => {
			gsap.fromTo(el, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 1.1, ease: 'expo.out', delay: 0.25, scrollTrigger: { trigger: el, start: 'top 90%', once: true } })
		})
	})
	return null
}
