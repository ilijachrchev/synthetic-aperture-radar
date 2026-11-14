# Web app

The landing page and the map for the NISAR surface change project. Next.js 16, React 19, Tailwind 4, MapLibre 6.

## Run it

```bash
pnpm install
pnpm dev        # http://localhost:3000
pnpm build && pnpm start
```

`pnpm build` runs `check:dashes` first: no en or em dash may appear anywhere in the app's own files.

## The game

`/game` replays the DANA "Adam" storm at the Pego-Oliva marsh as a guessing game: the player sees the last NISAR
pass before the rain and the rain forecast of that evening, marks ten cells of a 476 m grid where they expect new
water, and is scored against the pass after the storm. Every cell then explains itself from the measurements
(height above the sea, water before, the Copernicus map, what Sentinel-1 saw the same evening). The cells are
measured once by `python scripts/bake_game.py` from the baked frames, the terrain tiles and the EMS outline, into
`public/layers/pego_oliva/game.json`. Code: `src/components/game/`, copy: `src/content/game.ts`.

## Radar data

`pnpm radar --raw <folder outside the repo>` asks NASA's public catalogue (CMR) for every NISAR GCOV and GUNW
granule over each site, downloads only the small browse preview of each (about 3 MB, never the 1 to 7 GB granule),
cuts it to the site box and writes `public/radar/<site>/*.webp` plus `src/data/passes.json`. No login needed.

## Images made with SI

The hero photographs (`public/img/hero-*`) and the story icons (`public/img/icons/*`) were generated with Gemini.
Space Apps 2026 asks for a visible watermark on every SI-generated image, so `scripts/make_hero.py` and
`scripts/make_icons.py` bake one into each file. Radar images are real NISAR data and carry none.
