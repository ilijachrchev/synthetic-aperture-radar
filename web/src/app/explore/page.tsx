import type { Metadata } from 'next'
import { ExploreApp } from '@/components/explore/explore-app'
import { META } from '@/content/explore'

export const metadata: Metadata = META

export default function ExplorePage() {
	return <ExploreApp />
}
