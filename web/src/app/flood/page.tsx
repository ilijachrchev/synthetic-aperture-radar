import type { Metadata } from 'next'
import { StoryApp } from '@/components/flood/story-app'
import { DANA } from '@/content/stories'

export const metadata: Metadata = DANA.meta

export default function FloodPage() {
	return <StoryApp story={DANA} />
}
