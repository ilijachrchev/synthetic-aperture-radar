# CV benchmark protocol

Fixed on 14 Nov 2026, before any multi-site model was trained or scored. Results are reported as they come, including the ones that do not help.

## Question

Does training the water U-Net on more wetlands make it better at finding changing water on sites it has never seen, compared with the single-site model and a classic threshold?

## Data

| Role | Site | NISAR tracks (stacks) | Labelled scenes |
|---|---|---|---|
| Training | Albufera | 066_D_069, 058_A_021 | 14 |
| Training | Ebro Delta | 058_A_022, 066_D_068, 167_D_068 | 20 expected |
| Training | Camargue | 101_A_023, 173_A_024 | 10 expected |
| Test | Pego-Oliva | 066_D_069, 058_A_021, 167_D_069 | 18 |
| Test | Donana | 023_D_070, 116_A_020, 015_A_020 | 22 expected |

- Input: NISAR L2 GCOV HH and HV (20 m, gamma0), one stack per site and track on a fixed UTM grid.
- Labels: OPERA DSWx-S1 same-day water maps at most 2 h from the NISAR pass (`MAX_GAP_H`). Open water and inundated vegetation are water; classes 250, 251 and 255 are ignored.
- Scored class: changing water. The sea and permanent water (WorldCover water, or JRC occurrence of 90 % or more) are left out, because they are easy and would inflate every score.
- Expected counts come from the DSWx-S1 dry run; the real ones are in `data/metrics/cv_data_quality.json`.

## Rules

1. Test sites are never loaded for training, for choosing a checkpoint, a threshold or a model variant.
2. Validation: 20 % of the 5.12 km blocks of each training site, stratified so they hold a fair share of that site's changing water, the same blocks for every run (`split_seed` 0). All tracks of a site share its blocks, so the same ground is never in training and validation at once.
3. Checkpoint: the epoch with the best pooled IoU on changing open water in the validation blocks.
4. Model and threshold choice: pooled IoU on the validation blocks only (`pipeline.cv.evaluate --val-only` and `--sweep`).
5. The chosen ensemble and threshold are scored once on the test sites.

## Metrics

- Primary: pooled IoU of changing open water against DSWx-S1, per test site and for both test sites together. Pooled means the sum of true positives over the sum of TP + FP + FN over all dates, so each date weighs by its water.
- Secondary: the same for any water (open water plus inundated vegetation), median IoU per date, pooled precision and recall, and on the DANA flood the EMSR935 water gain IoU and the false alarm area in the control check.
- Uncertainty: 95 % bootstrap intervals, dates resampled within each stack (2000 draws, seed 0), and paired differences on the same draws (`pipeline.cv.benchmark`).

## Runs

Common settings: U-Net with a ResNet50 encoder pretrained on Sentinel-1 (SSL4EO-S12 MoCo), 40 epochs of 2048 crops of 256 px, batch 16, AdamW at 3e-4 with a one-cycle schedule, random 1 dB calibration offset per crop, bf16.

| Run | Training sites | Inputs | Labels | Seeds | Purpose |
|---|---|---|---|---|---|
| E0 | none | Otsu threshold on filtered HH | | | baseline |
| E1 | Albufera | ensemble of 6 (the model before this study) | | | reference |
| E2 | Albufera, Ebro, Camargue | HH, HV and the stack reference | three classes | 0, 1, 2 | main model |
| E3 | Albufera | same as E2 | same as E2 | 0, 1 | control: same settings, one site |
| E4 | Albufera, Ebro, Camargue | HH and HV only | three classes | 0 | ablation: no reference channels |
| E5 | Albufera, Ebro, Camargue | same as E2 | labels up to 13.5 h old | 0 | ablation: more but older labels |

Final model: the ensemble of the E2 seeds, plus an E4 or E5 run only if it beats E2 on the validation blocks; threshold from a sweep on the validation blocks.

## Known limits, stated up front

- The labels are another satellite's water map (C-band Sentinel-1), not ground truth: the scores measure agreement with DSWx-S1, which has its own errors (wind on open water, flooded vegetation).
- Changing water is a small class; dates with little of it give noisy IoU, which is why the primary metric is pooled.
- A label up to 2 h from the NISAR pass can still differ from it (tide, irrigation, wind).
- One season of NISAR data, June to November 2026, and five Mediterranean and Atlantic wetlands in Spain and France.
