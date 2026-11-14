import type { Metadata } from 'next'
import { WaterApp } from '@/components/flood/water-app'
import { DANA } from '@/content/stories'

export const metadata: Metadata = DANA.meta

export default function FloodPage() {
	return <WaterApp story={DANA} />
}
