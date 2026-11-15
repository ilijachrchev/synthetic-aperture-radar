# Spatial flood model: what we try and how we choose

Written and committed on 15 Nov 2026, before any variant below was scored on the held-out window. The start point
is Zhivko's PR #33 at `b4c69d9` (`pipeline/prediction/spatial`). The results are added below in later commits; the
git history shows that this plan and the selection rule came first.

## Fixed in advance

- **Held-out window:** target passes from 15 Oct to 15 Nov 2026 at Albufera and Pego-Oliva, as in PR #33 (18
  Sentinel-1 passes per site, 16 Oct to 10 Nov). No pass in it enters a fit, the past wet share, the number of
  trees, a threshold, the blend reference or the choice of variant.
- **Development data:** everything before 15 Oct 2026. The development check is the one of PR #33: fit on targets
  before 1 Sep 2025 on the training 1 km blocks, check on targets from 1 Sep 2025 to 14 Oct 2026 on the held-back
  1 km blocks. The number of trees and the thresholds come from this check; the final model is then refitted on all
  development passes with both kept.
- **Labels and samples:** OPERA DSWx-S1 (classes 1 and 3 wet, 0 dry), the same 413 passes per site, domain, pixel
  pool, seed and LightGBM settings as PR #33. Only the change named in a variant differs.
- **Thresholds:** every candidate gets its own, from its own development check (the F1-best threshold, as in PR #33),
  frozen before the held-out window is scored.
- **Not used to choose or tune anything:** the Copernicus EMSR935 outline (Luka's independent test) and the NISAR map
  of 28 Oct. The NISAR 28 Oct check is reported once at the end, for the chosen variant (and for `b4c69d9`, to compare).

## Variants

Each one is a full retrain on the PR #33 code path with only the stated change.

| id | change |
|---|---|
| `base` | PR #33 as it is, re-run on this machine (it must reproduce PR #33's scores, 0.47 and 0.38) |
| `mono` | LightGBM monotone constraint +1 on the four rain amounts (`rain_prior_7d_mm`, `rain_prior_30d_mm`, `rain_between_mm`, `rain_between_max1d_mm`), method `intermediate`: more rain never lowers a pixel's likelihood. `days_since_rain_peak` and `lead_days` stay free. |
| `storm` | Each target pass counts 1 + `rain_between_mm` / 25 times in the fit, at most 10 times (a dry pass once, 100 mm five times, 200 mm nine times). Nine in ten training passes had at most 60 mm. The check that picks the number of trees uses the same weights; scores and thresholds use the usual ones. |
| `neigh` | Two more inputs from the issue-time water map (the same map `prev_water` comes from): the share of water among the observed pixels in the 100 m square (5 x 5 pixels) and in the 500 m square (25 x 25 pixels) centred on each pixel. New water tends to spread from water that is already there. |
| `mono_storm` | `mono` and `storm` together |
| `mono_neigh` | `mono` and `neigh` together |
| `mono_storm_neigh` | all three |
| `nisar_flag` | Zhivko's variant: the team's NISAR water labels (`data/labels_nisar`) as extra passes plus the two sensor columns. Its development check and thresholds use the Sentinel-1 targets only, so it is checked on the same samples as the others. |

**Blend with terrain (brief item 2), for every variant above:** `<id>+blend` is the average of the variant's rank and
the terrain-only model's rank, weight 0.5, fixed, not tuned. A score's rank is the weighted share of reference samples
with a lower score; the reference is the table the model was fitted on (development data only). The average is mapped
back onto the variant's own likelihood scale through its reference quantiles, so the colours of a map keep their
meaning; that mapping keeps the order, so it changes no average precision. The terrain-only model is PR #33's
(Sentinel-1 labels, terrain, land cover, past water and season) for every blend.

**Order of work:** `base`, `mono`, `storm`, `neigh`, `nisar_flag`, `mono_storm`, `mono_neigh`, `mono_storm_neigh`. If
time runs out, the variants not trained are reported as not done and the rule applies to the ones trained.

## Scores

- **20 m pixels:** average precision of new water (pixels dry at the issue pass) over the held-out passes, pooled as in
  PR #33 (the same 200,000 domain pixels in every pass), per site. At the frozen new-water threshold: hit rate (share
  of the new water that the map marks) and false alarms (share of the marked pixels that stayed dry).
- **250 m cells:** squares of 250 m on the site grid, each 20 m pixel in the square that holds its centre. Per cell
  and pass, the candidates are the scored pixels that were dry at the issue pass, the observed value is the share of
  them under water at the target and the score is their mean new-water likelihood. Average precision weights every
  cell by its candidates (as if every pixel took its cell's mean score). Hit rate and false alarms compare the marked
  share (candidates at or above the frozen threshold) with the observed share, counting min(marked, observed) per
  cell as found.
- **Baselines:** terrain only and past wet share, as in PR #33. Persistence cannot rank new water.
- **Reported, not used to choose:** scores per pass, the DANA passes of 22 and 23 Oct, the forecast replay of 22 Oct
  (rain of the ECMWF IFS run of the issue day), and the likely new water of the rain scenarios (0, 50, 100, 200 mm),
  with whether it grows with the rain.

## Selection rule (development data only)

1. Development score = the mean over the two sites of the development-check new-water average precision at 20 m
   (weighted to the domain, as in `development_metrics.json`).
2. Candidates: every trained variant, alone and with the blend.
3. Let best be the highest development score. If a candidate with the monotone constraint (an id with `mono`, alone or
   blended) scores within 0.01 of best, the highest such candidate is chosen, because the app's rain slider must never
   show less water for more rain. Otherwise best is chosen. A tie goes to the candidate with fewer changes.
4. The development scores and the choice are written to `data/prediction/spatial/improve/selection.json` and committed
   before any held-out score is computed. Then every candidate is scored once on the held-out window and all results
   are reported as they are, wins and losses. Nothing is retuned after that.
5. The chosen candidate's maps replace the exported maps in `data/prediction/spatial` (PR #33 folder format, so
   `web/scripts/bake_prediction.py --ref <commit>` reads them).

## Development scores and the choice

Computed on development data only and committed, with `data/prediction/spatial/improve/selection.json`, before the
held-out window was scored. Development check new-water average precision at 20 m (weighted to the domain); the
development score is the mean of the two sites. The two storm columns are the development targets after at least
60 mm of rain (19 at Albufera, 33 at Pego-Oliva); they are reported, not used to choose.

| candidate | development score | Albufera | Pego-Oliva | Albufera, 60 mm or more | Pego-Oliva, 60 mm or more | monotone rain |
|---|---|---|---|---|---|---|
| `mono_neigh+blend` (chosen) | 0.3873 | 0.3251 | 0.4496 | 0.2377 | 0.5238 | yes |
| `mono_neigh` | 0.3862 | 0.3176 | 0.4548 | 0.2445 | 0.5292 | yes |
| `neigh+blend` | 0.3846 | 0.3218 | 0.4474 | 0.2343 | 0.5225 | no |
| `mono` | 0.3842 | 0.3179 | 0.4506 | 0.2055 | 0.5399 | yes |
| `mono_storm_neigh+blend` | 0.3819 | 0.3146 | 0.4491 | 0.2145 | 0.5243 | yes |
| `nisar_flag+blend` | 0.3815 | 0.3165 | 0.4464 | 0.2058 | 0.5195 | no |
| `nisar_flag` | 0.3804 | 0.3096 | 0.4513 | 0.1934 | 0.5354 | no |
| `neigh` | 0.3803 | 0.3108 | 0.4498 | 0.2336 | 0.5254 | no |
| `mono+blend` | 0.3800 | 0.3189 | 0.4411 | 0.2176 | 0.5253 | yes |
| `base` | 0.3794 | 0.3119 | 0.4469 | 0.1942 | 0.5450 | no |
| `base+blend` | 0.3784 | 0.3167 | 0.4402 | 0.2118 | 0.5296 | no |
| `mono_storm_neigh` | 0.3774 | 0.3038 | 0.4509 | 0.1973 | 0.5268 | yes |
| `mono_storm+blend` | 0.3727 | 0.3088 | 0.4365 | 0.2218 | 0.5255 | yes |
| `mono_storm` | 0.3705 | 0.2995 | 0.4414 | 0.2146 | 0.5363 | yes |
| `storm+blend` | 0.3668 | 0.3045 | 0.4291 | 0.2234 | 0.5163 | no |
| `storm` | 0.3592 | 0.2934 | 0.4251 | 0.2154 | 0.5196 | no |
| terrain only (baseline) | 0.3495 | 0.2887 | 0.4102 | 0.2221 | 0.4986 | |
| past wet share (baseline) | 0.2701 | 0.1844 | 0.3557 | 0.1441 | 0.4843 | |

**Choice:** `mono_neigh+blend`, the highest development score of all candidates (so the monotone rule did not have
to step in). The `base` re-run reproduces PR #33 exactly: the same label granules (hash), samples (2,182,850 and
2,891,109), trees (379 and 208), development scores and thresholds.

`nisar_flag` is checked on the same Sentinel-1 targets, but its pixel pool differs from the others (the pool is drawn
from wet counts that include the NISAR passes), so its development numbers are not on exactly the same pixels: the
terrain-only model scores 0.3550 on its check, 0.3495 on everyone else's.

Written with SI assistance (Claude Code), reviewed by the team.
