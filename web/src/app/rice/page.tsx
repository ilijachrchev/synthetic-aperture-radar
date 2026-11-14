import type { Metadata } from 'next'
import { StoryApp } from '@/components/flood/story-app'
import { RICE } from '@/content/stories'

export const metadata: Metadata = RICE.meta

export default function RicePage() {
	return <StoryApp story={RICE} />
}
