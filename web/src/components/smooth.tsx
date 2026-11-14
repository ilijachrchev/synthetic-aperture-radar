'use client'

import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import Lenis from 'lenis'
import { useEffect } from 'react'

/** The page's Lenis, for parts that scroll the page themselves (the stories' chapter buttons). */
export const lenisRef: { current: Lenis | null } = { current: null }

/**
 * Smooth scrolling for the landing: Lenis eases the wheel, and it runs on GSAP's own ticker so every ScrollTrigger
 * reads the same eased position on the same frame. Off under reduced motion.
 */
export function Smooth() {
	useEffect(() => {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
		gsap.registerPlugin(ScrollTrigger)
		const lenis = new Lenis({ lerp: 0.085, wheelMultiplier: 0.9, smoothWheel: true })
		lenisRef.current = lenis
		lenis.on('scroll', ScrollTrigger.update)
		const tick = (t: number) => lenis.raf(t * 1000)
		gsap.ticker.add(tick)
		gsap.ticker.lagSmoothing(0)
		// anchor links glide too
		const onClick = (e: MouseEvent) => {
			// a link that handled its own click (the stories' links scroll to a story) is left alone; React listens on
			// the document too, so stopping propagation would not reach this listener
			if (e.defaultPrevented) return
			const a = (e.target as HTMLElement).closest('a[href^="/#"], a[href^="#"]') as HTMLAnchorElement | null
			if (!a || a.pathname !== window.location.pathname) return
			const id = a.hash
			const el = id && document.querySelector(id)
			if (!el) return
			e.preventDefault()
			lenis.scrollTo(el as HTMLElement, { offset: -20, duration: 1.4 })
		}
		document.addEventListener('click', onClick)
		return () => {
			document.removeEventListener('click', onClick)
			gsap.ticker.remove(tick)
			lenisRef.current = null
			lenis.destroy()
		}
	}, [])
	return null
}
