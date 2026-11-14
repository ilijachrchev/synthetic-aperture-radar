import type { Metadata } from 'next'
import { preloadStory } from '@/components/flood/preload-story'
import { StoryApp } from '@/components/flood/story-app'
import { RICE } from '@/content/stories'

export const metadata: Metadata = RICE.meta

export default function RicePage() {
	preloadStory(RICE)
	return <StoryApp story={RICE} />
}
