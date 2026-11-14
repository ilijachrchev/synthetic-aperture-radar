import type { Metadata } from 'next'
import { preloadStory } from '@/components/flood/preload-story'
import { StoryApp } from '@/components/flood/story-app'
import { FIRE } from '@/content/stories'

export const metadata: Metadata = FIRE.meta

export default function FirePage() {
	preloadStory(FIRE)
	return <StoryApp story={FIRE} />
}
