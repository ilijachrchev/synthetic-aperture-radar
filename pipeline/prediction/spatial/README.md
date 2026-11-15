# Where will the water go (spatial water likelihood)

A small LightGBM model that scores every 20 m land pixel of Albufera and Pego-Oliva for water at a
target Sentinel-1 pass, from terrain, land cover, past water, rain and the last water map before the
issue time. It gives a relative likelihood. It does not give depth, speed or arrival time.

    python -m pipeline.prediction.spatial prepare   # terrain tiles + label stack, about 6 min, 1.5 GB in data/interim
    python -m pipeline.prediction.spatial train     # about 1 min
    python -m pipeline.prediction.spatial predict   # held-out scores, replays, rain scenarios, about 2 min

    python -m pipeline.prediction.spatial nisar     # 28 Oct replays scored against the NISAR water maps
    python -m pipeline.prediction.spatial train --variant soil      # also: nisar, nisar_soil; then predict --variant ...
    python -m pipeline.prediction.spatial compare   # held-out scores of every trained variant, comparison.json

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

## Variants and the forecast replay

- `base` is the model behind every exported map: Sentinel-1 labels, no soil moisture.
- `soil` adds the newest NISAR SME2 map before the issue day as an input. `nisar` adds the team's NISAR water labels
  (`data/labels_nisar`, open water wet, water under plants unknown) as extra passes. `nisar_soil` does both.
- `nisar_flag` is `nisar` plus two columns saying which radar the target and the previous water map come from.
  Without them the model cannot tell NISAR's extra water in the rice fields from Sentinel-1's view and blames it on
  the rain of those weeks, which wrecked four Albufera passes in November. With them the Sentinel-1 scores equal
  `base`, and `nisar --variant nisar_flag` predicts what NISAR will see.
  They write scores only, to `variants/<name>/`. All are scored on the same held-out Sentinel-1 passes.
- `forecast_2026-10-22` is the storm replay with the rain the ECMWF IFS run of the issue day forecast
  (Open-Meteo Single Runs, cached in `ifs_runs.json`), not the rain that fell. It is the only forecast-mode output.
- The past wet share of a sample counts only passes up to its issue pass.

## Improvement round of 15 Nov 2026 (`docs/MODEL_IMPROVE.md`)

    python -m pipeline.prediction.spatial.improve train base mono storm neigh nisar_flag mono_storm mono_neigh mono_storm_neigh
    python -m pipeline.prediction.spatial.improve select              # the plan's rule, development data only
    python -m pipeline.prediction.spatial.improve holdout base mono ...  # the held-out window, once, 20 m and 250 m
    python -m pipeline.prediction.spatial.improve table               # improve/results.json and results.md
    python -m pipeline.prediction.spatial.improve export mono_neigh+blend   # the chosen maps, in this folder's layout
    python -m pipeline.prediction.spatial.improve nisar mono_neigh+blend    # NISAR 28 Oct check, chosen candidate only

    # amendment (docs/MODEL_IMPROVE.md): minimum mapping unit, fit then test, two more exports
    python -m pipeline.prediction.spatial.improve mmu_dev mono_neigh+blend:albufera   # and :pego_oliva, development maps
    python -m pipeline.prediction.spatial.improve mmu_select mono_neigh+blend          # chose no filter
    python -m pipeline.prediction.spatial.improve fit_train mono_neigh                  # + Albufera's held-out passes
    python -m pipeline.prediction.spatial.improve fit_test mono_neigh+blend             # (a) fitted, (b) test, (c) forecast
    python -m pipeline.prediction.spatial.improve mmu_holdout mono_neigh+blend
    python -m pipeline.prediction.spatial.improve export_extra nisar                    # improve/exports/nisar_labels
    python -m pipeline.prediction.spatial.improve export_extra fit                      # improve/exports/fit_albufera_oct
    python -m pipeline.prediction.spatial.improve amend_table

- `mono`: the rain amounts only push the likelihood up (LightGBM monotone constraints). `neigh`: two more inputs,
  the share of water around each pixel (100 m and 500 m squares) in the issue-time water map. `storm`: passes after
  more rain count more in the fit. `+blend`: the rank of the model averaged with the terrain-only rank (0.5 each),
  read back on the model's own likelihood scale.
- The maps in this folder now come from `mono_neigh+blend`, chosen on development data only
  (`improve/selection.json`). Their `forecast.json` names the candidate (`variant`) and the exported score;
  `development_metrics.json` keeps PR #33's layout, with `thresholds.rain_and_state` = the thresholds of the
  exported score. `comparison.json` and `variants/` are PR #33's own runs and are not refreshed.
- Every step writes to `data/prediction/spatial/improve/` except `export`, which replaces the maps, `index.json`,
  `model.txt`, `development_metrics.json`, `holdout_s1_metrics.json`, `training_manifest.json`, `feature_schema.json`
  and (with `nisar`) `nisar_check.json` here.

## Known limits

- Sentinel-1 water maps are noisy and miss water under crops; they are labels, not truth.
- Rain is site-wide, so the model learns "how much", and terrain and history decide "where".
- Not yet scored against Copernicus EMSR935 (Luka's independent test).
- Soil moisture did not improve the held-out scores. The NISAR labels do not change the Sentinel-1 scores, but they
  improve the prediction of NISAR's own 28 Oct map, see `comparison.json` and `variants/nisar_flag/nisar_check.json`.

Written with SI assistance (Claude Code).
