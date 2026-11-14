import type { Metadata } from 'next'
import { FloodApp } from '@/components/flood/flood-app'

export const metadata: Metadata = {
	title: 'DANA Adam flood · Dancing with the SARs',
	description: 'The October 2026 flood at the Pego-Oliva marsh, played pass by pass from real radar water maps over real satellite pictures.',
}

export default function FloodPage() {
	return <FloodApp />
}
