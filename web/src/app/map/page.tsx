import type { Metadata } from 'next'
import { MapApp } from '@/components/map/map-app'
import { mapStories } from '@/lib/stories'

export const metadata: Metadata = { title: 'Map · Dancing with the SARs' }

export default function MapPage() {
	return <MapApp stories={mapStories()} />
}
