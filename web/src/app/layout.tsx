import type { Metadata, Viewport } from 'next'
import { DM_Mono, Instrument_Serif, Inter_Tight } from 'next/font/google'
import { SITE } from '@/content/site'
import './globals.css'

const interTight = Inter_Tight({ subsets: ['latin'], variable: '--font-inter-tight', display: 'swap' })
const instrumentSerif = Instrument_Serif({ subsets: ['latin'], weight: '400', style: ['normal', 'italic'], variable: '--font-instrument-serif', display: 'swap' })
const dmMono = DM_Mono({ subsets: ['latin'], weight: ['400', '500'], variable: '--font-dm-mono', display: 'swap' })

export const metadata: Metadata = {
	title: SITE.title,
	description: SITE.description,
}

export const viewport: Viewport = {
	themeColor: [
		{ media: '(prefers-color-scheme: light)', color: '#efedf7' },
		{ media: '(prefers-color-scheme: dark)', color: '#061235' },
	],
}

// Light is the default; a saved choice from the switch wins. Runs before first paint, so no flash.
const THEME_BOOT = `(function(){try{var t=localStorage.getItem("theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`

export default function RootLayout({ children }: LayoutProps<'/'>) {
	return (
		<html lang="en" data-theme="light" suppressHydrationWarning className={`${interTight.variable} ${instrumentSerif.variable} ${dmMono.variable}`}>
			<head>
				<script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
			</head>
			<body>{children}</body>
		</html>
	)
}
