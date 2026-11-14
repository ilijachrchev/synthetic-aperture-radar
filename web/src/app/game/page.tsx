import type { Metadata } from 'next'
import { preload } from 'react-dom'
import { GameApp } from '@/components/game/game-app'
import { GAME } from '@/content/game'

export const metadata: Metadata = GAME.meta

export default function GamePage() {
	for (const file of ['meta.json', 'game.json', 'rain.json']) preload(`${GAME.root}/${file}`, { as: 'fetch', crossOrigin: 'anonymous' })
	return <GameApp />
}
