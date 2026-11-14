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
