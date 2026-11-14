import { preload } from 'react-dom'
import type { Story } from '@/content/stories'

/** The files a story page reads first, named in the head of the page, so the browser fetches them while it is still
 *  loading the code that will ask for them (story-app.tsx). */
export function preloadStory(story: Story) {
	for (const file of ['meta.json', 'optical.json', 'story.json', ...(story.storm ? ['rain.json'] : [])]) {
		preload(`${story.root}/${file}`, { as: 'fetch', crossOrigin: 'anonymous' })
	}
}
