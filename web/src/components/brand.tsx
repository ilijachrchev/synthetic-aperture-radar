import Link from 'next/link'
import { SITE } from '@/content/site'

// The mark: a dot sending two arcs out, a radar pulse leaving its source. Drawn in the text colour.
export function Mark({ size = 22 }: { size?: number }) {
	return (
		<svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
			<circle cx="6" cy="12" r="2.6" fill="currentColor" />
			<path d="M11 6.5a8 8 0 0 1 0 11" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
			<path d="M15.5 3.5a12.5 12.5 0 0 1 0 17" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" opacity=".55" />
		</svg>
	)
}

export function Brand({ className = '' }: { className?: string }) {
	return (
		<Link href="/" className={`inline-flex items-center gap-2.5 text-[15px] font-semibold tracking-[-0.01em] ${className}`}>
			<Mark />
			<span>{SITE.name}</span>
		</Link>
	)
}
