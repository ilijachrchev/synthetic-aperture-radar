import type { Metadata } from 'next'
import { ExploreRoot } from '@/components/guided/explore-root'
import { META } from '@/content/guided'

export const metadata: Metadata = META

export default function ExplorePage() {
	return <ExploreRoot />
}
