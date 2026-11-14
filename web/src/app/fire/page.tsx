import type { Metadata } from 'next'
import { StoryApp } from '@/components/flood/story-app'
import { FIRE } from '@/content/stories'

export const metadata: Metadata = FIRE.meta

export default function FirePage() {
	return <StoryApp story={FIRE} />
}
