import type { Metadata, Viewport } from 'next'
import { Archivo, Geist_Mono, Hanken_Grotesk } from 'next/font/google'
import { SITE } from '@/content/site'
import './globals.css'

// Archivo 900 at its narrowest width (wdth 62) in capitals for display, Hanken Grotesk for text, Geist Mono for
// figures.
const archivo = Archivo({ subsets: ['latin'], axes: ['wdth'], variable: '--font-archivo', display: 'swap' })
const hanken = Hanken_Grotesk({ subsets: ['latin'], variable: '--font-hanken', display: 'swap' })
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono', display: 'swap' })

export const metadata: Metadata = {
	title: SITE.title,
	description: SITE.description,
}

export const viewport: Viewport = {
	themeColor: [
		{ media: '(prefers-color-scheme: light)', color: '#0c1633' },
		{ media: '(prefers-color-scheme: dark)', color: '#0c1633' },
	],
}

// Palette 2 is the default; a saved choice from the palette switch wins. The js class lets reveals hide content only
// when a script is there to show it again. Runs before first paint, so no flash.
const BOOT = `(function(){var d=document.documentElement;d.classList.add("js");try{var p=localStorage.getItem("palette");if(p==="1"||p==="2"||p==="3")d.setAttribute("data-palette",p)}catch(e){}})()`

export default function RootLayout({ children }: LayoutProps<'/'>) {
	return (
		<html lang="en" data-palette="2" suppressHydrationWarning className={`${archivo.variable} ${hanken.variable} ${geistMono.variable}`}>
			<head>
				<script dangerouslySetInnerHTML={{ __html: BOOT }} />
			</head>
			<body>{children}</body>
		</html>
	)
}
