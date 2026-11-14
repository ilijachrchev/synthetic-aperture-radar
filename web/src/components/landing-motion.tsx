'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP)

/**
 * The landing's motion around the monitor (the films on its screen run in monitor.tsx), on GSAP. The line rises
 * word by word, its two buttons follow, and the monitor rises in below them, its top half in view; scrolling tips it
 * up flat until it pins in the middle of the screen. Transform and opacity only; the scroll is Lenis (smooth.tsx).
 */
export function LandingMotion() {
	useGSAP(() => {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
			gsap.set('[data-a], .hx-title, .mon-in', { opacity: 1, clearProps: 'transform' })
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
		gsap.fromTo('.mon-in', { opacity: 0, y: 120 }, { opacity: 1, y: 0, duration: 1.6, ease: 'expo.out', delay: 0.3 })

		// as the page scrolls the monitor tips up from a slight lean and grows a touch, until it pins in the middle
		gsap.fromTo('.mon', { rotateX: 16, scale: 0.92 }, { rotateX: 0, scale: 1, ease: 'none', scrollTrigger: { trigger: '.hx-track', start: 'top 55%', end: 'top top', scrub: true } })
	})
	return null
}
