'use client'

// Marks its box once it is a quarter on screen (data-in), so CSS can play a section's entrance once. The page without
// scripts shows everything: the hidden starting state only applies under .js.

import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from 'react'

export function InView({ className, style, children }: { className?: string; style?: CSSProperties; children: ReactNode }) {
	const ref = useRef<HTMLDivElement>(null)
	const [on, setOn] = useState(false)
	useEffect(() => {
		const el = ref.current
		if (!el) return
		const io = new IntersectionObserver(
			([e]) => {
				if (!e.isIntersecting) return
				setOn(true)
				io.disconnect()
			},
			{ threshold: 0.25 },
		)
		io.observe(el)
		return () => io.disconnect()
	}, [])
	return (
		<div ref={ref} className={className} style={style} data-in={on || undefined}>
			{children}
		</div>
	)
}
