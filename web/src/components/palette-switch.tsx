'use client'

import { useCallback, useSyncExternalStore } from 'react'

const PALETTES = [
	{ id: '1', name: 'Mint sorbet, deep ocean, hot coral', cone: 'conic-gradient(#ddf5ea 0 60%, #0b3d57 0 90%, #ff6b57 0)' },
	{ id: '2', name: 'Midnight navy, powder blue, fresh mint', cone: 'conic-gradient(#0c1633 0 60%, #b9d6f2 0 90%, #3ddba4 0)' },
	{ id: '3', name: 'Blush pink, charcoal ink, fresh mint', cone: 'conic-gradient(#f6d7d7 0 40%, #24262b 0 70%, #3ddba4 0)' },
]

const read = () => document.documentElement.getAttribute('data-palette') ?? '2'
const subscribe = (on: () => void) => {
	const mo = new MutationObserver(on)
	mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-palette'] })
	return () => mo.disconnect()
}

/** The three palettes to try, side by side; each swatch shows its own split. The page cross-fades between them. */
export function PaletteSwitch({ className = '' }: { className?: string }) {
	const current = useSyncExternalStore(subscribe, read, () => '2')
	const pick = useCallback((id: string) => {
		const apply = () => {
			document.documentElement.setAttribute('data-palette', id)
			try {
				localStorage.setItem('palette', id)
			} catch {}
		}
		if (!document.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return apply()
		document.startViewTransition(apply)
	}, [])
	return (
		<div className={`pal ${className}`} role="radiogroup" aria-label="Palette">
			{PALETTES.map((p) => (
				<button key={p.id} type="button" role="radio" aria-checked={current === p.id} title={`Palette ${p.id}: ${p.name}`} onClick={() => pick(p.id)} style={{ background: p.cone }}>
					<span className="sr-only">
						Palette {p.id}: {p.name}
					</span>
				</button>
			))}
		</div>
	)
}
