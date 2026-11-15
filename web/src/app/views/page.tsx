import type { Metadata } from 'next'
import { ViewsDemo } from '@/components/views/views-demo'

export const metadata: Metadata = {
	title: 'Where is NISAR? Four views · Through the Clouds',
	description:
		'What only NISAR gives: water Sentinel-1 misses, coherence that takes out false water, soil wetness before a storm, and water every 12 days through cloud.',
}

// A demo of the baked views (web/scripts/bake_views.py), not a final screen: every picture and number comes from
// public/layers/<site>/views.json.
export default function ViewsPage() {
	return <ViewsDemo />
}
