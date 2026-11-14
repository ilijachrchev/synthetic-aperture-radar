import type { Metadata } from 'next'
import { preloadStory } from '@/components/flood/preload-story'
import { StoryApp } from '@/components/flood/story-app'
import { DANA } from '@/content/stories'

export const metadata: Metadata = DANA.meta

export default function FloodPage() {
	preloadStory(DANA)
	return <StoryApp story={DANA} />
}
