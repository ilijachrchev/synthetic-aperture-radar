'use client'

// /explore: the guided map of five steps by default; "All layers" opens the free explorer with today's layer panel,
// and a button there brings the guide back. The choice sits in the address (?all), so it can be shared. The address
// is read after hydration (the server sends an empty map frame), so the first paint never disagrees with it.

import { useEffect, useSyncExternalStore } from 'react'
import { META, TITLE_ALL } from '@/content/guided'
import { ExploreApp } from '../explore/explore-app'
import { GuidedApp } from './guided-app'

const URL_EVENT = 'explore-url'
const subscribe = (cb: () => void) => {
	window.addEventListener('popstate', cb)
	window.addEventListener(URL_EVENT, cb)
	return () => {
		window.removeEventListener('popstate', cb)
		window.removeEventListener(URL_EVENT, cb)
	}
}
const allLayers = () => new URLSearchParams(window.location.search).has('all')
const onServer = () => null

function open(on: boolean, screen?: 'exam' | 'rain') {
	const url = new URL(window.location.href)
	url.searchParams.delete('all')
	url.searchParams.delete('step')
	url.searchParams.delete('screen')
	if (screen) url.searchParams.set('screen', screen)
	const q = url.searchParams.toString()
	const search = on ? `?all${q ? `&${q}` : ''}` : q ? `?${q}` : ''
	window.history.pushState(null, '', `${url.pathname}${search}${url.hash}`)
	window.dispatchEvent(new Event(URL_EVENT))
}

export function ExploreRoot() {
	const all = useSyncExternalStore(subscribe, allLayers, onServer)
	// the tab's title follows the page on screen: the guide, or every layer
	useEffect(() => {
		if (all !== null) document.title = all ? TITLE_ALL : META.title
	}, [all])
	if (all === null) return <div className="gd gd-boot" />
	return all ? <ExploreApp onGuide={() => open(false)} onScreen={(k) => open(false, k)} /> : <GuidedApp onAllLayers={() => open(true)} />
}
