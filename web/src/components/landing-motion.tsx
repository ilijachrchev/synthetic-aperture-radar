'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP)

/**
 * All of the landing's motion in one place, on GSAP. Headings rise word by word out of their own masks and their
 * marker swipes in behind the last word; blocks rise in groups as they enter; the radar drifts slower than the page;
 * the app's window tilts up flat as it arrives. Transform and opacity only; scrubbed parts ride Lenis (smooth.tsx).
 */
export function LandingMotion() {
	useGSAP(() => {
		const marks = gsap.utils.toArray<HTMLElement>('.mark')
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
			gsap.set('[data-a], .hx-title, .sx-title, .hx-radar', { opacity: 1, clearProps: 'transform' })
			return
		}

		const titles = (sel: string, opts: (h: HTMLElement) => gsap.TimelineVars) =>
			gsap.utils.toArray<HTMLElement>(sel).forEach((h) => {
				const split = SplitText.create(h, { type: 'words', mask: 'words' })
				gsap.set(h, { opacity: 1 })
				const own = h.querySelectorAll('.mark')
				gsap.set(own, { '--mx': 0 })
				gsap
					.timeline(opts(h))
					.from(split.words, { yPercent: 115, duration: 1.15, ease: 'expo.out', stagger: 0.07 })
					.to(own, { '--mx': 1, duration: 0.7, ease: 'power3.inOut' }, '-=0.55')
			})

		// hero, on load
		titles('.hx-title', () => ({ delay: 0.1 }))
		gsap.fromTo('.hx [data-a]', { opacity: 0, y: 26 }, { opacity: 1, y: 0, duration: 1.1, ease: 'expo.out', stagger: 0.09, delay: 0.45 })
		gsap.fromTo('.hx-radar', { opacity: 0, y: 40, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 1.5, ease: 'expo.out', delay: 0.2 })
		gsap.to('.hx-radar-inner', { yPercent: -7, ease: 'none', scrollTrigger: { trigger: '.hx', start: 'top top', end: 'bottom top', scrub: true } })

		// section headings and their lines
		titles('.sx-title', (h) => ({ scrollTrigger: { trigger: h, start: 'top 86%', once: true } }))
		gsap.utils.toArray<HTMLElement>('.sx-head [data-a]').forEach((el) => {
			gsap.fromTo(el, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 1.1, ease: 'expo.out', delay: 0.25, scrollTrigger: { trigger: el, start: 'top 90%', once: true } })
		})

		// groups rise together, one after another
		gsap.utils.toArray<HTMLElement>('[data-a-group]').forEach((g) => {
			gsap.fromTo(g.querySelectorAll('[data-a]'), { opacity: 0, y: 48 }, { opacity: 1, y: 0, duration: 1.2, ease: 'expo.out', stagger: 0.1, scrollTrigger: { trigger: g, start: 'top 84%', once: true } })
		})

		// the app's window lies back and comes up flat as it arrives
		gsap.fromTo('.mx-frame', { rotateX: 16, scale: 0.9, y: 60 }, { rotateX: 0, scale: 1, y: 0, ease: 'none', scrollTrigger: { trigger: '.mx-stage', start: 'top 92%', end: 'top 25%', scrub: 0.6 } })

		return () => marks.forEach((m) => m.style.removeProperty('--mx'))
	})
	return null
}
