# CV benchmark results

Results of the protocol in [CV_PROTOCOL.md](CV_PROTOCOL.md), run on 14 Nov 2026. The final model and its threshold were chosen on validation blocks only and scored once on the two test sites. Everything below comes from the files in `data/metrics/` named in each section; numbers are reported as they came, including the ones that do not favour the final model.

## 1. Data actually used

A labelled scene is a NISAR acquisition with a same-day OPERA DSWx-S1 map at most 2 h from the pass. The label pass is matched by the outline of its tiles, and on some dates the Sentinel-1 swath misses the site entirely: those scenes have no label at all. Only scenes whose map covers at least 10 % of the usable NISAR pixels count here (`cv_data_quality.json`).

| Site | Role | Tracks | Usable labelled scenes | Label pass misses the site |
|---|---|---|---|---|
| Albufera | training | 066 D, 058 A | 14 | 0 |
| Ebro Delta | training | 058 A, 066 D, 167 D | 5 | 14 |
| Camargue | training | 101 A, 173 A | 9 | 0 |
| Pego-Oliva | test | 066 D, 058 A, 167 D | 18 | 0 |
| Donana | test | 023 D, 116 A, 015 A | 17 | 5 |

- Training used 28 usable scenes (14 before this study, at Albufera only). The protocol expected about 44; the Ebro shortfall was found after training, by the data quality check.
- The labels look clean where they exist: they call 97 to 99.8 % of permanent inland water "water" at every site.
- Radar brightness of built-up land differs by up to 5.8 dB between sites and tracks (for example -1.1 to -2.1 dB at Albufera 066 D, -5.1 to -6.9 dB at Camargue 101 A), a real shift between places, and by up to 1.3 dB between dates of one stack (Camargue 101 A, 25 Sep to 7 Oct). Training adds one random offset of up to 1 dB per crop (`--jitter-db 1.0`) for this.

## 2. Model choice, on validation only

Pooled IoU of changing open water in the held-out blocks of the three training sites (`cv_select_*.json`). Every candidate was best at the lowest threshold of the grid fixed in advance (0.3 to 0.6), so the optimum may lie below 0.3.

| Candidate | Models | Pooled IoU at 0.3 |
|---|---|---|
| E2: three sites, 3 seeds | 3 | 0.359 |
| E2 and E4 (no reference channels) | 4 | 0.361 |
| E2 and E5 (labels up to 13.5 h old) | 4 | 0.355 |
| **E2, E4 and E5 (chosen)** | 5 | **0.361** |

The candidates are within 0.006 of each other: the choice between them hardly matters. Single runs, best epoch: E2 seeds 0.251, 0.327 and 0.238; E4 0.295; E5 0.275. The Albufera-only control (E3, 2 seeds) chose threshold 0.3 on its own blocks.

## 3. Test: sites never used for training or choice

Pooled IoU of changing open water against same-day DSWx-S1, with 95 % bootstrap intervals over dates (`cv_benchmark_final.json`). "Previous" is the model of this morning: 6 U-Nets trained on Albufera only, threshold 0.4.

| Site | Dates | Threshold baseline | Previous | Albufera only (E3) | **Final** |
|---|---|---|---|---|---|
| Pego-Oliva | 18 | 0.121 [0.031, 0.234] | 0.374 [0.118, 0.527] | 0.284 [0.083, 0.439] | 0.334 [0.119, 0.485] |
| Donana | 17 | 0.016 [0.010, 0.023] | 0.019 [0.014, 0.027] | 0.023 [0.016, 0.033] | 0.035 [0.022, 0.053] |
| Albufera, validation blocks | 14 | 0.094 | 0.440 | 0.575 | 0.618 |

Paired differences on the same resampled dates:

- Final minus Albufera only: Pego-Oliva +0.050 [0.034, 0.059], Donana +0.012 [0.007, 0.020]. Training on three wetlands helped on both unseen sites. The final ensemble has 5 models and the control 2, so part of the gain may come from the ensemble size.
- Final minus previous: Pego-Oliva -0.040 [-0.067, 0.004] (the previous model is ahead in 95 % of draws), Donana +0.016 [0.008, 0.026].
- Every U-Net beats the threshold baseline on open water at both sites, with intervals clear of zero.

Open water plus flooded vegetation (any water), pooled IoU: Pego-Oliva baseline 0.215, previous 0.176, Albufera only 0.185, final 0.221; Donana baseline 0.089, previous 0.087, Albufera only 0.083, final 0.089. No model beats the baseline on any water: the U-Nets add nothing for flooded vegetation.

### DANA "Adam" flood, Pego-Oliva, track 066 D, 16 to 28 Oct

New water against the Copernicus EMS EMSR935 outline, inside its mapped areas (877 ha of labelled flood in the scored region). The control is water already called inside the outline before the flood: lower is better.

| Model | Water gain IoU | Precision | Recall | New water | Control |
|---|---|---|---|---|---|
| Threshold baseline | 0.203 | 0.87 | 0.21 | 212 ha | 0.249 |
| Previous | 0.258 | 0.75 | 0.28 | 334 ha | 0.028 |
| Albufera only | 0.272 | 0.79 | 0.29 | 328 ha | 0.072 |
| **Final** | **0.305** | 0.82 | **0.33** | 349 ha | 0.074 |

## 4. Hidden water: NISAR L-band against Sentinel-1 C-band

Where NISAR's own signal (5x5 filtered HH below -15 dB) shows water that the same-day DSWx-S1 map does not, outside the sea and permanent water (`cv_hidden_water.json`), and what an independent optical water map (OPERA DSWx-HLS, Landsat and Sentinel-2, within 3 days) says about those pixels (`cv_hidden_water_optical.json`).

| Case | NISAR only, cropland and wetland | Optical says water | Optical on dry land | Reading |
|---|---|---|---|---|
| Ebro rice, 18 Jun (optical 20 Jun) | 14,157 ha | 42 % | 7 % | real in part, 6 times the background |
| Albufera rice, 18 Jun (optical 21 Jun) | 6,331 ha | 36 % | 8 % | real in part, 4.5 times the background |
| Camargue, 25 Sep (optical same day) | 3,697 ha | 14 % | 11 % | not water: salt flats |
| Donana, 7 Sep (optical 6 Sep) | 12,282 ha | 1 % | 2 % | not water: dry, smooth marsh |

- In flooded rice early in the season, NISAR sees water that the Sentinel-1 map misses, and optical images confirm a third to a half of it as partly flooded fields. The gap closes by late July at Albufera, as the rice grows.
- In dry marshes and salt flats, smooth dry ground is dark to radar too: NISAR calls 23,000 to 45,000 ha "water" at Donana on every date from June to November, and optical images say it is dry. A darkness threshold cannot tell the two apart.
- At Donana the optical map also agrees with only 7 % of the water both radars see, so Donana's dry-season DSWx-S1 labels are doubtful. Read the Donana test numbers with that in mind.

## 5. Limits

- The labels are another satellite's water map, not ground truth; the scores measure agreement with DSWx-S1.
- Ebro gave 5 usable scenes, not 20; a label pass should be kept only when its swath covers the site (`pipeline/dswx.py` matches tile outlines today).
- The final and control ensembles differ in size (5 against 2 models).
- The best threshold sits at the edge of the grid fixed in advance.
- Pooling over both test sites is dominated by Donana's large area, so the per-site rows are the ones to read.
- One season (June to November 2026), five wetlands in Spain and France.

## 6. Reproduce

```bash
# data: python -m pipeline.catalog --site ebro (and camargue, donana); python -m pipeline.context --site ebro ...;
#       python -m pipeline.nisar_fetch --site ebro --stack 058_A_022 --min-coverage 0.15; python -m pipeline.stack ...;
#       python -m pipeline.dswx --site ebro --stack 058_A_022 --stack 066_D_068 --stack 167_D_068 --min-coverage 0.15
COMMON="--inputs current+ref --label-mode three --jitter-db 1.0 --epochs 40 --samples 2048 --split-seed 0"
python -m pipeline.cv.train --name cv_e2_aec_s0 --sites albufera ebro camargue $COMMON --seed 0   # seeds 0, 1, 2
python -m pipeline.cv.train --name cv_e4_aec_current_s0 --sites albufera ebro camargue --inputs current --label-mode three --jitter-db 1.0 --epochs 40 --samples 2048 --split-seed 0 --seed 0
python -m pipeline.cv.train --name cv_e5_aec_gap13_s0 --sites albufera ebro camargue $COMMON --seed 0 --max-gap-h 13.5
python -m pipeline.cv.train --name cv_e3_alb_s0 --sites albufera $COMMON --seed 0                  # seeds 0, 1
python -m pipeline.cv.final_eval
python -m pipeline.cv.quality
python -m pipeline.cv.hidden_water
python -m pipeline.cv.hidden_water --optical ebro 066_D_068 2026-06-18
```

Written with SI assistance (Claude Code), reviewed by the team.
