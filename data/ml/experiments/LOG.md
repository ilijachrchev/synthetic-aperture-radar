# ML experiment log

Plain-language log of every model version. Machine-readable details (config,
dates, per-seed scores, run time, git commit) are in `registry.jsonl`, one line
per run. Runner: `python -m pipeline.ml.experiment`.

**How we score.** All numbers are *agreement with the label maps* (WorldCover,
JRC water, CORINE 2018, EFFIS burnt area, hand-drawn rice fields), not
ground-truth accuracy. Main number: macro F1 (the average of the per-class
F1 scores, so small classes count as much as big ones).

**Three sets, never mixed.**
- *Test blocks*: 1 km blocks, 25 % of each class, seed 42. Looked at once, for
  the final version only.
- *Validation blocks*: a second block split cut from the training area, with 3
  seeds (43, 44, 45). Every choice is made here. "Spread" = best seed minus
  worst seed. A gain smaller than the spread is noise.
- *Training pixels*: the rest, with a 2 px gap around the other blocks.

Validation scores are the raw model on the validation pixels (no specks
clean-up); test scores are the final map (majority filter + sieve), the map
the app shows. Note: the 1-track version (v1) has slightly different blocks than
2-track versions, because a pixel must be seen by both tracks to count.

## v1 — main today (reference)
Single track, 20k pixels per class, 31 leaves, 400 trees, burned rule 1.0 dB.

| site | val macro F1 (3 seeds) |
|---|---|
| Albufera 066_D_069 | 0.745 ± 0.031 |
| Espadà 058_A_022 | 0.667 ± 0.005 |

Matches the numbers from the earlier single-seed run (0.743 / 0.675).

## v2 — both tracks per pixel (this branch) — KEPT
Each pixel gets the features of both viewing tracks (Albufera 066_D + 058_A,
Espadà 058_A + 167_D), 60k pixels per class, 63 leaves, min 30 per leaf,
tree count by early stopping, burned rule: HV drop >= 1.0 dB on either track.

| site | val macro F1 | rice | water | urban | forest | burned | other | orchard |
|---|---|---|---|---|---|---|---|---|
| Albufera | **0.800 ± 0.005** | 0.966 | 0.985 | 0.792 | 0.747 | – | 0.709 | 0.603 |
| Espadà | **0.749 ± 0.002** | – | 0.863 | 0.664 | 0.840 | 0.815 | 0.672 | 0.639 |

+5.5 points (Albufera) and +8.2 points (Espadà) over v1, far above the spread.
Decision: kept, it is the new base.

## v2a / v2b — burned rule off / 0.5 dB — DROPPED
The rule acts after the model, so all thresholds were scored on the same three
v2 models (registry entry `v2-rules`, Espadà only). "Far" = mapped burned more
than 2 km from the EFFIS outline (almost surely wrong), raw map before clean-up.

| rule (HV drop, either track) | val macro F1 | burned F1 | burned precision | burned far from fire |
|---|---|---|---|---|
| off (v2a) | 0.767 ± 0.003 | 0.893 | 0.865 | ≈1,045 ha |
| 0.5 dB (v2b) | 0.762 ± 0.002 | 0.875 | 0.883 | ≈770 ha |
| **1.0 dB (v2)** | 0.748 ± 0.001 | 0.815 | 0.915 | ≈365 ha |
| 1.5 dB | 0.721 ± 0.003 | 0.685 | 0.935 | ≈180 ha |

Without the rule the score goes up (+1.8 points), but the map shows about three
times more fake burn scars far from the fire. Those would be the first thing a
viewer notices, and "burned" is a story class. Decision: keep 1.0 dB. 0.5 dB is a
fair middle ground if Ilija prefers more of the fire area filled in.

## v2c — seasonal means — DROPPED
Mean HH, HV and HV−HH per calendar season (Jun–Jul, Aug–Sep, Oct) for each
track: 76 features instead of 58.

| site | val macro F1 | change vs v2 |
|---|---|---|
| Albufera | 0.800 ± 0.004 | −0.0 |
| Espadà | 0.749 ± 0.004 | +0.0 |

No change in any class. The whole-season stats plus the "when was the biggest
drop / rise" features already tell the model the same story. Decision: dropped
(more features, nothing gained).

## Third viewing track — NOT DONE
Espadà 066_D_068 and Albufera 167_D_068 cover only 31–92 % of the site box,
and a different part on each date, so the fetch tool skips them on purpose. A
third track needs a two-frame mosaic (066_D_068 + 066_D_069 at Espadà,
167_D_068 + 167_D_069 at Albufera) before the stack builder. Too big for this
round; open question for Ilija.

## v2d — texture — KEPT
Local roughness: the 5 × 5 pixel standard deviation of the season-mean HH and
HV image, for each track (+4 features). Fields and water are smooth; towns,
orchards and forest edges are rough. The 2 px split gap covers the 5 × 5 window.

| site | val macro F1 | change vs v2 | biggest class gains |
|---|---|---|---|
| Albufera | **0.807 ± 0.005** | +0.6 | forest +2.0, water +0.6, other +0.5 |
| Espadà | **0.757 ± 0.003** | +0.8 | water +3.1, urban +1.3 |

Gain is above the spread on both sites (small, but real). Decision: kept.

## v2e — CORINE orchard and forest shrunk by 40 m — DROPPED
Training labels only (as rice already is); scores on the usual labels.

| site | val macro F1 | change vs v2 | on the shrunk labels |
|---|---|---|---|
| Albufera | 0.803 ± 0.004 | +0.3 | 0.804 |
| Espadà | 0.747 ± 0.003 | −0.2 | 0.753 |

Inside the noise. Orchard F1 stays 0.60–0.65 even when scored on the shrunk
labels, so the 100 m polygon edges are not what holds orchard back (see the
label-noise note below). Decision: dropped.

## Label-noise check (no training)
Inside CORINE orchard polygons, WorldCover calls only 35 % (Albufera) and 48 %
(Espadà) of the pixels "trees"; the rest is mostly grassland and cropland, which
our rules label `other_crops_shrub`. So **57 % of all Albufera other_crops
labels (44 % at Espadà, 34 % at Pego-Oliva) lie inside CORINE orchards**. The
same orchard gets "orchard" on its tree pixels and "other crops" on the ground
between the trees. That caps orchard and other_crops F1 whatever the model does.

## v2f — drop conflicting orchard labels — DROPPED (but see the finding)
Training labels only: inside CORINE orchard polygons, pixels that WorldCover
calls shrub, grass or crop are left unlabeled instead of `other_crops_shrub`.

| site | val macro F1, usual labels | change vs v2 | val macro F1, cleaned labels | orchard F1 (usual → cleaned) |
|---|---|---|---|---|
| Albufera | 0.777 ± 0.005 | −2.4 | 0.833 ± 0.004 | 0.57 → 0.82 |
| Espadà | 0.704 ± 0.008 | −4.5 | 0.779 ± 0.004 | 0.62 → 0.81 |

On the usual labels it loses: the usual labels still call the ground between
orchard trees "other crops", and the new model calls it orchard. On the cleaned
labels orchard jumps to about 0.8. The two columns use different yardsticks and
cannot be compared directly. They do show that the radar *can* separate
orchards; the labels are what hold the class back. Decision: not the default.
Which orchard definition the app should use is a team decision (open question).

Stop rule reached: v2e and v2f, two versions in a row, gave no real gain.

## FINAL: v2d
Config (`registry.jsonl`, stage `final`): both tracks per pixel, base + texture
features (62), 60k pixels per class, 63 leaves, min 30 per leaf, learning rate
0.05, tree count by early stopping on validation seed 43 (Albufera 284,
Espadà 932), refit on the whole training area; burned only where HV dropped
≥ 1.0 dB on either track; 3 × 3 majority filter and 5 px sieve on the map.

**Scores** (agreement with the label maps; test = the map the app shows):

| | v1 val | v1 test | **v2d val (3 seeds)** | **v2d test** |
|---|---|---|---|---|
| Albufera acc / macro F1 | – / 0.745 | 0.807 / 0.791 | – / 0.807 ± 0.005 | **0.823 / 0.834** |
| Espadà acc / macro F1 | – / 0.667 | 0.756 / 0.723 | – / 0.757 ± 0.003 | **0.793 / 0.815** |
| Pego-Oliva benchmark (trained on Albufera, never seen) | | 0.530 / 0.523 | | **0.611 / 0.596** |

Test is higher than validation because the test score is on the cleaned-up
map (the specks filter helps) and the final model trains on more area.

**Per-class F1 on the test blocks (v2d):**

| class | Albufera | Espadà | Pego-Oliva benchmark |
|---|---|---|---|
| rice_paddy | 0.978 | – | 0.729 |
| permanent_water | 0.997 | 0.878 | – (no labels) |
| urban | 0.843 | 0.733 | 0.619 |
| forest | 0.849 | 0.908 | 0.338 |
| burned | – | 0.913 | – |
| other_crops_shrub | 0.728 | 0.739 | 0.641 |
| orchard | 0.608 | 0.718 | 0.652 |

**Burned at Espadà (final map):** 7,336 ha mapped burned; 7,083 ha of it inside
the EFFIS outline (EFFIS: 9,230 ha, so 77 % of the fire is filled in); 185 ha
more than 2 km from the outline. Burned precision on test blocks 0.98.

**Pego-Oliva**: forest is weak (0.34) because Albufera has very little forest to
learn from (10k labelled pixels against 375k at Espadà). Rice drops from 0.98
to 0.73: Pego has only 2 CORINE rice polygons (12k labelled pixels); why
rice there differs is not checked yet. v2d beats v1 by 7 points macro F1 on a site neither
saw, so the two-track gain is not just learning Albufera by heart.

**Top features**: Albufera — HV variability, HV max (both tracks), HV−HH;
Espadà — darkest HH on track 167_D, the HV lasting drop (the fire). Texture
carries 4 % (Albufera) and 8 % (Espadà) of the model's gain.

Maps: `data/ml/albufera_066_D_069+058_A_021/` and
`data/ml/espada_058_A_022+167_D_068/` (class + confidence COGs, metrics,
feature importance, model.txt locally). The single-track maps from v1 are still
in `data/ml/<site>_<stack>/` and in the manifest.
