'use client'

import { Moon, Sun } from 'lucide-react'
import { useCallback, useSyncExternalStore } from 'react'

type Theme = 'light' | 'dark'

function read(): Theme {
	return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}
function subscribe(onChange: () => void) {
	const mo = new MutationObserver(onChange)
	mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
	return () => mo.disconnect()
}

// Day and night switch. The new light grows as a circle from the switch over 640ms (a View Transition), so the
// hero's dawn photo turns into its dusk twin from the point you pressed.
export function ThemeToggle({ className = '' }: { className?: string }) {
	const theme = useSyncExternalStore(subscribe, read, () => 'light' as Theme)

	const toggle = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
		const next: Theme = read() === 'dark' ? 'light' : 'dark'
		const apply = () => {
			document.documentElement.setAttribute('data-theme', next)
			try {
				localStorage.setItem('theme', next)
			} catch {}
		}
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		if (!document.startViewTransition || reduced) return apply()
		const x = e.clientX || window.innerWidth - 40
		const y = e.clientY || 40
		const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
		const t = document.startViewTransition(apply)
		t.ready.then(() => {
			document.documentElement.animate(
				{ clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
				{ duration: 640, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', pseudoElement: '::view-transition-new(root)' },
			)
		})
	}, [])

	const dark = theme === 'dark'
	return (
		<button
			type="button"
			onClick={toggle}
			aria-label={dark ? 'Switch to day' : 'Switch to night'}
			title={dark ? 'Day' : 'Night'}
			className={`grid size-10 place-items-center rounded-full border border-[var(--glass-line)] bg-[var(--glass)] text-[var(--hero-ink)] backdrop-blur-md transition-colors duration-300 hover:bg-[var(--glass-strong)] ${className}`}
		>
			{dark ? <Sun size={17} strokeWidth={1.8} /> : <Moon size={17} strokeWidth={1.8} />}
		</button>
	)
}
