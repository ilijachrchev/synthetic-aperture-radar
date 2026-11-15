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

## Held-out results (scored once, after the choice)

Every candidate was scored once on the 18 held-out Sentinel-1 passes per site (16 Oct to 10 Nov 2026), with the
thresholds frozen on development data, after `selection.json` was committed and pushed (`e9a49d2`). Nothing was
changed after that. The tables below are written by `python -m pipeline.prediction.spatial.improve table`
(`data/prediction/spatial/improve/results.md` and `results.json`); every number is in
`improve/<variant>/holdout_s1_metrics.json`, pass by pass.

How to read them. New water = pixels dry at the issue pass. 20 m: the PR #33 sample (the same 200,000 domain pixels
in every pass), pooled over the 18 passes; hit = share of the new water the map marks at the frozen threshold, false
alarms = share of the marked area that stayed dry. 250 m: all candidate pixels, every pixel at its cell's mean score;
cells are mixed, so no ranking can reach 1 and the 250 m numbers compare candidates with each other, not with the
20 m ones. The `base` rows reproduce PR #33's held-out numbers exactly (0.4663 and 0.3763, terrain only 0.4100 and
0.3077, past wet share 0.3256 and 0.3154).

**Held-out new water, 20 m pixels** (AP = average precision; hit and false alarms at the frozen threshold)

| candidate | development score | Albufera AP | hit | false alarms | Pego-Oliva AP | hit | false alarms |
|---|---|---|---|---|---|---|---|
| base | 0.379 | 0.466 | 62 % | 58 % | 0.376 | 58 % | 70 % |
| base+blend | 0.378 | 0.469 | 61 % | 56 % | 0.345 | 58 % | 71 % |
| terrain only (baseline) |  | 0.410 | 61 % | 63 % | 0.308 | 57 % | 72 % |
| past wet share (baseline) |  | 0.326 | 8 % | 66 % | 0.315 | 41 % | 69 % |
| mono | 0.384 | 0.489 | 57 % | 54 % | 0.374 | 56 % | 69 % |
| mono+blend | 0.380 | 0.476 | 61 % | 55 % | 0.344 | 57 % | 71 % |
| storm | 0.359 | 0.416 | 72 % | 65 % | 0.357 | 60 % | 73 % |
| storm+blend | 0.367 | 0.472 | 64 % | 60 % | 0.334 | 58 % | 72 % |
| neigh | 0.380 | 0.487 | 55 % | 53 % | 0.365 | 57 % | 69 % |
| neigh+blend | 0.385 | 0.476 | 67 % | 59 % | 0.341 | 62 % | 72 % |
| nisar_flag | 0.380 | 0.472 | 51 % | 51 % | 0.380 | 58 % | 69 % |
| nisar_flag+blend | 0.382 | 0.464 | 60 % | 57 % | 0.348 | 60 % | 71 % |
| mono_storm | 0.370 | 0.410 | 72 % | 65 % | 0.377 | 61 % | 72 % |
| mono_storm+blend | 0.373 | 0.472 | 64 % | 60 % | 0.343 | 58 % | 72 % |
| mono_neigh | 0.386 | 0.493 | 65 % | 59 % | 0.369 | 59 % | 70 % |
| **mono_neigh+blend** (chosen) | 0.387 | 0.483 | 68 % | 60 % | 0.343 | 62 % | 72 % |
| mono_storm_neigh | 0.377 | 0.476 | 68 % | 61 % | 0.377 | 58 % | 70 % |
| mono_storm_neigh+blend | 0.382 | 0.486 | 64 % | 57 % | 0.346 | 58 % | 72 % |

**Held-out new water, 250 m cells** (AP = average precision; hit and false alarms at the frozen threshold)

| candidate | development score | Albufera AP | hit | false alarms | Pego-Oliva AP | hit | false alarms |
|---|---|---|---|---|---|---|---|
| base | 0.379 | 0.410 | 69 % | 54 % | 0.278 | 64 % | 67 % |
| base+blend | 0.378 | 0.398 | 68 % | 52 % | 0.255 | 63 % | 68 % |
| terrain only (baseline) |  | 0.331 | 67 % | 59 % | 0.228 | 61 % | 70 % |
| past wet share (baseline) |  | 0.260 | 11 % | 50 % | 0.232 | 47 % | 63 % |
| mono | 0.384 | 0.425 | 64 % | 49 % | 0.275 | 61 % | 65 % |
| mono+blend | 0.380 | 0.405 | 68 % | 51 % | 0.253 | 62 % | 68 % |
| storm | 0.359 | 0.376 | 78 % | 62 % | 0.262 | 65 % | 69 % |
| storm+blend | 0.367 | 0.404 | 71 % | 56 % | 0.245 | 62 % | 69 % |
| neigh | 0.380 | 0.424 | 62 % | 48 % | 0.267 | 63 % | 65 % |
| neigh+blend | 0.385 | 0.405 | 74 % | 55 % | 0.250 | 67 % | 69 % |
| nisar_flag | 0.380 | 0.409 | 57 % | 45 % | 0.282 | 64 % | 65 % |
| nisar_flag+blend | 0.382 | 0.390 | 67 % | 53 % | 0.255 | 65 % | 68 % |
| mono_storm | 0.370 | 0.367 | 78 % | 63 % | 0.279 | 67 % | 69 % |
| mono_storm+blend | 0.373 | 0.400 | 70 % | 56 % | 0.254 | 63 % | 69 % |
| mono_neigh | 0.386 | 0.427 | 73 % | 54 % | 0.269 | 65 % | 67 % |
| **mono_neigh+blend** (chosen) | 0.387 | 0.411 | 76 % | 56 % | 0.252 | 68 % | 69 % |
| mono_storm_neigh | 0.377 | 0.423 | 75 % | 57 % | 0.276 | 63 % | 67 % |
| mono_storm_neigh+blend | 0.382 | 0.414 | 71 % | 53 % | 0.255 | 63 % | 68 % |

**The storm, 20 m** (22 Oct = first Sentinel-1 pass after the DANA rain; forecast = the same pass with the rain the IFS run of the issue day forecast; scenarios = likely new water in ha at 0, 50, 100 and 200 mm)

| candidate | Albufera 22 Oct | Albufera forecast | Albufera scenarios | Pego-Oliva 22 Oct | Pego-Oliva forecast | Pego-Oliva scenarios |
|---|---|---|---|---|---|---|
| base | 0.639 | 0.460 | 1,010 / 1,657 / 1,660 / 3,557 | 0.396 | 0.358 | 405 / 471 / 430 / 513 |
| base+blend | 0.702 | 0.630 | 1,333 / 1,706 / 1,713 / 1,976 | 0.371 | 0.354 | 449 / 478 / 460 / 487 |
| terrain only (baseline) | 0.677 | 0.677 |  | 0.351 | 0.351 |  |
| past wet share (baseline) | 0.574 | 0.574 |  | 0.326 | 0.326 |  |
| mono | 0.687 | 0.580 | 1,149 / 1,804 / 1,824 / 4,448 | 0.390 | 0.363 | 376 / 482 / 483 / 604 |
| mono+blend | 0.705 | 0.653 | 1,458 / 1,796 / 1,811 / 2,119 | 0.370 | 0.358 | 445 / 486 / 486 / 514 |
| storm | 0.508 | 0.440 | 1,696 / 2,439 / 2,412 / 5,719 | 0.401 | 0.365 | 513 / 585 / 560 / 762 |
| storm+blend | 0.694 | 0.662 | 1,697 / 1,968 / 1,924 / 2,515 | 0.373 | 0.357 | 490 / 515 / 496 / 554 |
| neigh | 0.688 | 0.649 | 1,030 / 1,493 / 1,588 / 3,927 | 0.355 | 0.346 | 362 / 436 / 438 / 534 |
| neigh+blend | 0.696 | 0.672 | 1,674 / 1,925 / 1,981 / 2,386 | 0.352 | 0.348 | 483 / 514 / 516 / 564 |
| nisar_flag | 0.689 | 0.673 | 1,878 / 2,781 / 2,902 / 5,835 | 0.447 | 0.366 | 513 / 587 / 616 / 701 |
| nisar_flag+blend | 0.696 | 0.685 | 1,889 / 2,173 / 2,224 / 2,379 | 0.399 | 0.363 | 510 / 531 / 547 / 566 |
| mono_storm | 0.467 | 0.400 | 1,756 / 2,617 / 2,692 / 6,104 | 0.420 | 0.379 | 505 / 590 / 624 / 980 |
| mono_storm+blend | 0.695 | 0.664 | 1,687 / 1,980 / 2,005 / 2,643 | 0.380 | 0.364 | 475 / 506 / 512 / 594 |
| mono_neigh | 0.688 | 0.652 | 1,531 / 2,104 / 2,149 / 5,075 | 0.352 | 0.335 | 455 / 542 / 544 / 802 |
| **mono_neigh+blend** (chosen) | 0.707 | 0.677 | 1,838 / 2,136 / 2,157 / 2,578 | 0.352 | 0.343 | 508 / 544 / 545 / 620 |
| mono_storm_neigh | 0.568 | 0.575 | 1,396 / 1,959 / 2,016 / 5,726 | 0.384 | 0.361 | 416 / 456 / 458 / 724 |
| mono_storm_neigh+blend | 0.709 | 0.675 | 1,582 / 1,856 / 1,870 / 2,457 | 0.365 | 0.356 | 454 / 469 / 469 / 565 |

**Pass by pass, chosen against PR #33 (`base`), new-water AP:** at Albufera `mono_neigh+blend` is better on 18 of 18
passes at 20 m (mean +0.050) and on 18 of 18 at 250 m (mean +0.040); at Pego-Oliva it is better on 10 of 18 at 20 m
(mean -0.004) and 12 of 18 at 250 m (mean -0.002), and worse on the three storm passes (22 Oct 0.352 against 0.396,
23 Oct 0.449 and 0.445 against 0.484 and 0.476). The pooled score at Pego-Oliva falls more than the passes do
because pooling also asks whether the storm passes rank above the dry ones, and the blend halves the rain response.

**The rain slider.** PR #33's likely new water at Pego-Oliva went down from 50 to 100 mm (471 to 430 ha). With the
monotone constraint it never goes down: 508, 544, 545 and 620 ha for 0, 50, 100 and 200 mm (Albufera 1,838, 2,136,
2,157 and 2,578 ha). 50 and 100 mm are still almost the same map: few training passes had that much rain. With no
rain the chosen map marks more new water than PR #33's (Pego-Oliva 508 against 405 ha, Albufera 1,838 against
1,010 ha), because its terrain half marks low ground whatever the rain.

## The NISAR 28 Oct check (chosen candidate and PR #33 only)

Run once, after the held-out scores, on the pre-storm replay (issued from the last Sentinel-1 map before the rain of
18 and 19 Oct, with the rain that fell, for the NISAR pass of 28 Oct). Never used to choose or tune.

Against the team's NISAR change layer of PR #35 (`data/labels_nisar/<site>_066_D_069/dana_2026-10-16_2026-10-28.tif`,
code 2 = new open water), at the frozen new-water threshold, on every pixel NISAR compared except permanent water
(the protocol of the first check, which gave PR #33 26 % and 15 % at Pego-Oliva):

| site | map | catches (hit rate) | right on (precision) | marked | ranking AP |
|---|---|---|---|---|---|
| Pego-Oliva | PR #33 `b4c69d9` | 26 % | 15 % | 383 ha | 0.157 |
| Pego-Oliva | chosen `mono_neigh+blend` | 34 % | 16 % | 457 ha | 0.145 |
| Albufera | PR #33 `b4c69d9` | 78 % | 62 % | 3,286 ha | 0.650 |
| Albufera | chosen `mono_neigh+blend` | 80 % | 63 % | 3,278 ha | 0.732 |

NISAR saw 217 ha of new open water at Pego-Oliva and 2,597 ha at Albufera on these pixels. Counting only pixels NISAR
also saw dry on 16 Oct, Pego-Oliva is 34 % and 20 % for the chosen map against 26 % and 19 % for PR #33. At
Pego-Oliva the chosen map catches more new water by marking more ground, and it ranks slightly worse (AP 0.145 against
0.157). Albufera is not an independent check: the NISAR water model was trained with Sentinel-1 labels there. Files:
`improve/nisar_check_mono_neigh_blend.json`, `improve/nisar_check_b4c69d9.json`.

PR #33's own check against the data/cv NISAR maps (`nisar_check.json`, now for the exported model) shows the same
pattern in ranking: new-water AP at Albufera 0.759 against 0.719 (066 D, issued before the storm) and better on all
four runs; at Pego-Oliva 0.250 against 0.265 (066 D, before the storm) and worse on all four runs.

## What helped and what did not

The rule picked `mono_neigh+blend` on development data (0.387 against 0.379 for PR #33), and on the held-out month it
is better at Albufera and worse at Pego-Oliva. At Albufera it beats PR #33 on every one of the 18 passes (pooled
new-water AP 0.483 against 0.466, 250 m 0.411 against 0.410), it now beats terrain only on the DANA day (0.707
against 0.677; PR #33 0.639) and, run on the forecast rain of 17 Oct, it ties terrain only (0.677 against 0.677;
PR #33 0.460). At Pego-Oliva it is about level pass by pass but loses on the storm passes and pooled (0.343 against
0.376; 250 m 0.252 against 0.278). The blend with terrain is the reason for both: it costs 0.02 to 0.03 of pooled AP at
Pego-Oliva in every variant, because its terrain half has no rain, and it is what lifts the Albufera DANA day. The
cleanest single change is the monotone rain constraint: it fixes the rain slider, lifts Albufera (0.489) and keeps
Pego-Oliva level (0.374). The neighbourhood of the issue-time water map adds a little at Albufera (0.487 alone) and
slightly lowers Pego-Oliva (0.365). Weighting storm passes did not work: it lowered the development score and the held-out
score at both sites. Zhivko's NISAR labels with sensor flags are neutral on Sentinel-1 (0.472 and 0.380). Against
NISAR's own 28 Oct map at Pego-Oliva, the chosen map catches 34 % of the new water (PR #33 26 %) and is right on 16 %
of what it marks (15 %), by marking more ground. The model alone (`mono_neigh`, without the blend) would have scored
0.493 and 0.369 on the held-out month; it was not chosen, because the choice was made on development data and the
held-out month is not used to change it. All of this is one storm at two sites, against Sentinel-1 maps that are
labels, not truth.

## The exported maps

`data/prediction/spatial/<site>/<scenario>/` now holds `mono_neigh+blend` (PR #33 layout: `forecast.json`,
`water_likelihood_utm.tif`, `new_water_likelihood_utm.tif`, `evidence_utm.tif` and the two web copies; `index.json`
lists them). Each `forecast.json` names the candidate (`variant`, `exported_score`) and holds its frozen thresholds;
`development_metrics.json` keeps PR #33's layout with `thresholds.rain_and_state` = the thresholds of the exported
score (the model alone is under `thresholds.model_alone`). For the EMSR935 test: score evidence 0 pixels with the
thresholds of each map's `forecast.json`. `comparison.json` and `variants/` are PR #33's own runs.

To reproduce (main venv, the DSWx-S1 history in `data/raw/dswx_history`, about 1 hour on 16 threads):

    python -m pipeline.prediction.spatial prepare
    python -m pipeline.prediction.spatial.improve train base mono storm neigh nisar_flag mono_storm mono_neigh mono_storm_neigh
    python -m pipeline.prediction.spatial.improve select
    python -m pipeline.prediction.spatial.improve holdout base mono storm neigh nisar_flag mono_storm mono_neigh mono_storm_neigh
    python -m pipeline.prediction.spatial.improve table
    python -m pipeline.prediction.spatial.improve export mono_neigh+blend
    python -m pipeline.prediction.spatial.improve nisar mono_neigh+blend

Written with SI assistance (Claude Code), reviewed by the team.
