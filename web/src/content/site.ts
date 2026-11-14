// Site copy. Wording comes from the repository README (the team's own words), shaped into lines, never extended
// with new claims. The working title is the challenge's name until the team picks a product name.
export const SITE = {
	name: 'Dancing with the SARs',
	title: 'Dancing with the SARs · Valencia seen by NISAR radar',
	description: "Watching Earth's surface flood, grow, burn and sink, seen by NASA-ISRO NISAR radar. One web app for the land around Valencia.",
	repo: 'https://github.com/ilijachrchev/synthetic-aperture-radar',
	challenge: 'https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/',
} as const

export const NAV = [
	{ label: 'Stories', href: '/#stories' },
	{ label: 'Every pass', href: '/#passes' },
	{ label: 'How it works', href: '/#how' },
	{ label: 'Data', href: '/#data' },
] as const

export const HERO = {
	kicker: 'Watching the land around',
	place: 'Valencia',
	sub: 'flood, grow, burn and sink, seen by NASA-ISRO NISAR radar.',
	lead: 'One web app that shows how the land around Valencia changes, and',
	leadAccent: 'what is likely to come next.',
	seenBy: ['Seen by NASA-ISRO NISAR,', 'one pass every 12 days'],
	primary: { label: 'Open the map', href: '/map' },
	secondary: { label: 'How it works', href: '/#how' },
} as const
