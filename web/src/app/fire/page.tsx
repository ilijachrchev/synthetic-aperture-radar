import type { Metadata } from 'next'
import { WaterApp } from '@/components/flood/water-app'
import { FIRE } from '@/content/stories'

export const metadata: Metadata = FIRE.meta

export default function FirePage() {
	return <WaterApp story={FIRE} />
}
