'use client'

import { Moon, Sun } from 'lucide-react'
import { useCallback, useSyncExternalStore } from 'react'

type Theme = 'light' | 'dark'

const read = (): Theme => (document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light')
const subscribe = (on: () => void) => {
	const mo = new MutationObserver(on)
	mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
	return () => mo.disconnect()
}

/** Day and night: two buttons and a thumb that slides between them. The page cross-fades to the other theme. */
export function ThemeSwitch({ className = '' }: { className?: string }) {
	const current = useSyncExternalStore(subscribe, read, (): Theme => 'light')
	const pick = useCallback((id: Theme) => {
		const apply = () => {
			document.documentElement.setAttribute('data-theme', id)
			try {
				localStorage.setItem('theme', id)
			} catch {}
		}
		if (!document.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return apply()
		document.startViewTransition(apply)
	}, [])
	return (
		<div className={`theme ${className}`} role="group" aria-label="Theme">
			<button type="button" aria-pressed={current === 'light'} aria-label="Day" title="Day" onClick={() => pick('light')}>
				<Sun size={16} strokeWidth={2.2} />
			</button>
			<button type="button" aria-pressed={current === 'dark'} aria-label="Night" title="Night" onClick={() => pick('dark')}>
				<Moon size={15} strokeWidth={2.2} />
			</button>
		</div>
	)
}
