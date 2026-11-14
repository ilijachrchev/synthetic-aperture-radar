// MapLibre 6 finds its web worker next to its own module file, but the bundler moves that file, so the worker never
// loads. Copy the self-contained worker into public/ and point MapLibre at it (setWorkerUrl in map-app.tsx).
// Runs before dev and build and after install; the copy is not committed.
import { copyFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const from = fileURLToPath(new URL('../node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs', import.meta.url))
const dir = fileURLToPath(new URL('../public/maplibre/', import.meta.url))
mkdirSync(dir, { recursive: true })
copyFileSync(from, dir + 'maplibre-gl-worker.mjs')
console.log('maplibre worker copied to public/maplibre/')
