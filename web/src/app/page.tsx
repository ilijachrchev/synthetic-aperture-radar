import { Hero } from '@/components/landing'
import { LandingMotion } from '@/components/landing-motion'
import { SiteFooter } from '@/components/site-footer'
import { Smooth } from '@/components/smooth'

export default function Home() {
	return (
		<main>
			<Smooth />
			<LandingMotion />
			<Hero />
			<SiteFooter />
		</main>
	)
}
