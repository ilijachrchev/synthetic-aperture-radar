# Where will the water go (spatial water likelihood)

A small LightGBM model that scores every 20 m land pixel of Albufera and Pego-Oliva for water at a
target Sentinel-1 pass, from terrain, land cover, past water, rain and the last water map before the
issue time. It gives a relative likelihood. It does not give depth, speed or arrival time.

    python -m pipeline.prediction.spatial prepare   # terrain tiles + label stack, about 6 min, 1.5 GB in data/interim
    python -m pipeline.prediction.spatial train     # about 1 min
    python -m pipeline.prediction.spatial predict   # held-out scores, replays, rain scenarios, about 2 min

Needs the `ml` extra and the Sentinel-1 history in `data/raw/dswx_history`
(`python -m pipeline.prediction.flood history`).

## Inputs

| Input | Source | Note |
|---|---|---|
| Water per pass (label and previous state) | OPERA DSWx-S1, 413 passes per site, Aug 2024 to Nov 2026 | classes 1 and 3 wet, 0 dry, everything else unknown |
| Rain | `data/prediction/flood/rain_<site>.csv` (Open-Meteo, ECMWF IFS 9 km) | one value per site and day: no variation inside a site |
| Height above drainage | ASF GLO-30 HAND, 30 m | fetched by `prepare` |
| Elevation, slope | Copernicus DEM GLO-30, 30 m | fetched by `prepare` |
| Past water | JRC occurrence, and the share of earlier Sentinel-1 passes that saw water | the Sentinel-1 share uses no held-out pass |
| Land cover | WorldCover 2021, Albufera rice mask | |

## Rules

- **Held-out window:** 15 Oct to 15 Nov 2026 at both sites, as in the flood alert. No pass in it enters a fit,
  the past-water share, the number of trees or the thresholds.
- **Times:** the issue pass is the latest pass at least 3 days before the target. Only water maps up to it are used.
  Rain is split into rain before the issue day and rain from the issue day to the day before the target.
- **Reconstruction, not forecast:** in fits and replays the rain after the issue day is the rain that fell.
  A score from a replay is not a forecast score.
- **Learning domain:** land, not permanent water, not built-up, mapped by Sentinel-1 in at least half of the passes.
  Towns and hills are still predicted but flagged in `evidence_utm.tif`.
- **Development check:** fit on targets before 1 Sep 2025 on training blocks, check on later targets on held-back
  1 km blocks. Trees and thresholds come from that check and are then frozen.

## Outputs (`data/prediction/spatial/`)

`model.txt`, `model_terrain_only.txt`, `feature_schema.json`, `training_manifest.json`, `development_metrics.json`,
`holdout_s1_metrics.json`, `index.json`, and per site and scenario a folder with `water_likelihood_utm.tif`,
`new_water_likelihood_utm.tif`, `evidence_utm.tif`, two web copies and `forecast.json`.

Scenarios: `replay_2026-10-22`, `replay_2026-10-28` (DANA, reconstruction) and `scenario_000mm` to `scenario_200mm`
(a chosen rain total over the 4 days after the latest water map).

## Known limits

- Sentinel-1 water maps are noisy and miss water under crops; they are labels, not truth.
- Rain is site-wide, so the model learns "how much", and terrain and history decide "where".
- Not yet scored against Copernicus EMSR935, not yet using the NISAR water maps in `data/cv`.
- Not registered in `data/manifest.json`; `index.json` lists the scenarios.

Written with SI assistance (Claude Code).
