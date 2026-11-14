import { createElement, type CSSProperties } from 'react'

const D = (ms: number) => ({ '--d': `${ms}ms` }) as CSSProperties

/**
 * A display heading in the 8x grammar: one or more short lines, each a statement ending in a full stop, the last
 * line (or the words in `accent`) in the gradient. Every word lifts out of its own mask in turn when the heading
 * comes into view (reveal.tsx sets data-in).
 */
export function Title({
	lines,
	accent,
	as = 'h2',
	className = '',
	style,
	delay = 0,
}: {
	lines: string[]
	/** words (exact, case sensitive) drawn in the accent gradient; defaults to the whole last line */
	accent?: string[]
	as?: 'h1' | 'h2' | 'h3'
	className?: string
	style?: CSSProperties
	delay?: number
}) {
	let k = 0
	const last = lines.length - 1
	return createElement(
		as,
		{ className: `display ${className}`, style, 'data-words': '' },
		lines.map((line, li) => (
			<span key={li} className="title-line" style={{ display: 'block' }}>
				{line.split(' ').map((w, wi, all) => {
					const lit = accent ? accent.includes(w) : li === last && lines.length > 1
					const node = (
						<span key={wi} className="wd">
							<span style={D(delay + k++ * 45)} className={lit ? 'accent' : undefined}>
								{w}
							</span>
						</span>
					)
					return wi < all.length - 1 ? [node, ' '] : node
				})}
			</span>
		)),
	)
}
