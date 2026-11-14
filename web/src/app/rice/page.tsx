import type { Metadata } from 'next'
import { WaterApp } from '@/components/flood/water-app'
import { RICE } from '@/content/stories'

export const metadata: Metadata = RICE.meta

export default function RicePage() {
	return <WaterApp story={RICE} />
}
