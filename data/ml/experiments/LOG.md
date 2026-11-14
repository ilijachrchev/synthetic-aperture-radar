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
