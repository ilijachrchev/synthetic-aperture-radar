# CV benchmark against an independent answer key (pre-registered)

Written on 14 Nov 2026 at about 20:45 Valencia time, before any score of this benchmark was computed. It follows the first, one-time test in [CV_RESULTS.md](CV_RESULTS.md), whose results stay as they were reported. Anything changed after the first score of this benchmark is listed at the end, with its reason.

## 1. Why a second benchmark

The first test scored every model against Sentinel-1's own water map (OPERA DSWx-S1). That map is not ground truth:

- At Donana an optical water map confirms only 5 to 7 % of the water both radars agree on (`cv_hidden_water_optical.json`).
- In flooded rice in June it misses water that optical images confirm.

Scoring against it rewards copying its errors. This benchmark uses an answer key from a different kind of sensor, and makes Sentinel-1 one of the competitors.

## 2. What was looked at before this protocol (disclosed)

On 14 Nov, after the first test and before this protocol, four diagnostic dates were examined (Donana 7 Sep, Camargue 25 Sep, Albufera 18 Jun, Ebro 18 Jun), each against a same-period optical map:

- At L-band, dry smooth ground is as dark as water. At Donana: water HH median -18.2 dB, dark but dry ground -16.4 dB, and HV of both at the noise floor near -24 dB. No darkness threshold separates them.
- The 12-day coherence of NISAR's GUNW pairs does separate them: water 0.25, dark dry ground 0.69, other dry land 0.81 (Donana); in rice the gap is smaller.

Donana is a test site. The coherence channel was designed because the model failed at Donana in the first test, so the Donana results of the new model are "after seeing that test site once". Pego-Oliva was not used in these diagnostics. Its per-date results from the first test were looked at (too much water on quiet dates), which motivated the spot filter below.

## 3. The question

Judged by an independent optical answer key, how well does each method map changing open water: the Sentinel-1 map (C-band), simple NISAR rules, and the NISAR U-Nets, per land type?

## 4. Answer key

- OPERA DSWx-HLS v1 (Landsat 8 and 9, Sentinel-2; 30 m), layer B01_WTR, within 1 day of the NISAR date. Per pixel, the first clear value in this order: same day, the day before, the day after (`pipeline/cv/optical.py`, `data/optical`).
- Open water = class 1, no water = class 0. Partial surface water (class 2), cloud, snow, ocean mask and fill are not scored.
- A date counts when its clear answer key covers at least 10 % of the scored NISAR pixels.
- Also scored: the DANA flood against the Copernicus EMS EMSR935 outline, drawn by people from imagery of 20 to 21 Oct (as in CV_RESULTS.md).
- Limit: optical cannot see water under plants (rice canopy, reeds). The benchmark therefore covers open water only. Flooded vegetation is not scored, because there is no trustworthy reference for it. In cropland and wetland, a pixel the answer key calls dry may still hold water under plants, so results are reported per land type.
- Limit: DSWx-HLS often flags sediment-rich water as snow or ice (class 252), which is not scored, so muddy flood water can drop out of the answer key.
- Coverage (built before any scoring): 130 of the 136 NISAR dates have an optical image within 1 day; 103 have at least 10 % of the NISAR-valid pixels clear, 90 at least 50 %. Albufera 18 Jun is cloudy on both tracks within the window and is not scored; the DANA dates 16 and 28 Oct on track 066 D are 99.8 % and 88 % clear.

## 5. Pixels and dates

- NISAR usable on the date (HH and HV finite, valid mask), answer key clear, neither sea nor permanent water (WorldCover water, or JRC occurrence of 90 % or more): the same changing water as before.
- Training sites (Albufera, Ebro, Camargue): only inside the held-out validation blocks, the same blocks for every model. Test sites (Pego-Oliva with its 167 D stack, Donana): everywhere.
- Dates with HV only, since the U-Nets need HV.
- Two pixel sets: "all dates" (every NISAR method); "with Sentinel-1" (dates with a DSWx-S1 map at most 2 h from the pass, only its valid pixels; every method plus Sentinel-1).
- Within a set, every method is scored on exactly the same pixels.
- Land types (ESA WorldCover 2021): cropland (40); grass, shrub and herbaceous wetland (20, 30, 90); bare (60); other.

## 6. Methods

1. **Sentinel-1 map**: DSWx-S1 open water (class 1).
2. **NISAR threshold**: 5x5 filtered HH below -15 dB (the threshold fixed earlier in the threshold check of discussion #9).
3. **NISAR Otsu**: one Otsu threshold per scene (the baseline of CV_RESULTS.md).
4. **NISAR dark and low coherence**: dark as in 2, and coherence below c. Where no pair covers a pixel, the darkness rule alone decides.
5. **U-Net v1**: the final ensemble of CV_RESULTS.md (5 models), at its pre-registered threshold 0.3, and at a threshold chosen on this answer key (section 7) so that it competes on the same terms as the methods tuned here.
6. **U-Net v2**: the same recipe as v1 (3 seeds with `current+ref` inputs, one with `current` inputs, one with labels up to 13.5 h old), with two changes:
   - the 12-day coherence as an extra input channel (`current+ref+coh`, `current+coh`);
   - the optical label cleanup: training labels that a clear same-date answer key contradicts are dropped, in training and in validation scoring. Contradicts means Sentinel-1 open water where optical sees no water, or Sentinel-1 no water where optical sees open water. Inundated vegetation is kept.
7. **U-Net v2 with spot filter**: v2, keeping only connected water regions that hold at least one pixel with probability of at least s.

Coherence of a date: the pair that ends on that date, with the latest reference date; only the past is used, as in real use. That pair is normally 12 days long, but 24 or 36 days after a missing acquisition (14 dates, around the 27 Jul to 10 Aug gap; 6 of them at the test sites), and dry land loses more coherence over a longer pair. Only for the first date of a stack's pairs: the pair that starts on it, with the earliest secondary date. Otherwise none (the U-Net sees the channel mean).

Found before training: 14 of the 132 dates with HV have no pair, all of them the newest dates (23 Oct to 6 Nov), after NISAR's switch to validated processing on 21 Oct, for which no GUNW pairs are published yet. They include 28 Oct, the DANA after-flood date. So that v2 does not break where coherence is missing, 15 % of its training crops have the coherence channel blanked (`--coh-dropout 0.15`), and its results are also reported split by whether the date has coherence.

Ablation, single seed 0 (what each change does on its own): v1's seed 0 model; coherence only; cleanup only; both.

Training of v2: `--sites albufera ebro camargue --label-mode three --jitter-db 1.0 --epochs 40 --samples 2048 --split-seed 0`, as v1. The dB jitter shifts HH, HV and the reference channels, never coherence. The validation blocks come from the uncleaned labels, so they are the same as v1's.

## 7. Free parameters

Each is chosen on the training sites' validation blocks only ("all dates" set), by the highest pooled IoU of changing open water against the answer key, on the exact counts. Ties go to the lowest value. Nothing is chosen on a test site.

| Parameter | Grid |
|---|---|
| c, method 4 | 0.25, 0.3, 0.35, 0.4, 0.45, 0.5 (extended with 0.15 and 0.2, section 11) |
| threshold, U-Nets (v1 re-tuned, v2, ablations) | 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5 (extended with 0.05 and 0.1, section 11) |
| s, spot filter (at v2's threshold) | 0.5, 0.6, 0.7 |

The checkpoint epoch of each v2 model is chosen as for v1: pooled IoU of changing open water on the validation blocks against the (here cleaned) Sentinel-1 labels.

## 8. Metrics

- Per test site, and for the training sites' validation blocks: pooled IoU, precision and recall of changing open water, and false water as a share of the answer key's dry ground. Each for all land types together and per land type.
- 95 % intervals for IoU, precision, recall and false-water share: 2000 bootstrap draws of dates, resampled within each stack, seed 0. Paired differences on the same draws: v2 minus v1; v2 minus Sentinel-1; v1 minus Sentinel-1; method 4 minus method 2; v2 with spot filter minus v2; each ablation minus v1's seed 0 model. A stack with a single scored date adds no spread. Where no stack of a group has two dates, no interval is given and no "better" claim is made.
- The test sites again, split into dates with and without a coherence pair. Each test stack has at most one scored date without coherence, so that split is descriptive only.
- The DANA flood: water gain IoU, precision, recall and the before-flood control, for every method on the same pixels (inside the mapped areas, usable for every method on both dates). 16 Oct has a coherence pair and 28 Oct has none, so a coherence method would build its before and after maps differently. The coherence methods are therefore also run with coherence withheld on both dates, and only those rows are compared. For method 4 that is the NISAR threshold itself.
- "Better" means the 95 % interval of the paired difference lies above zero. Otherwise: no clear difference.
- Results are reported as they come, including those that favour Sentinel-1 or v1.

## 9. Order of work

1. Build the answer key and the coherence for every date and pair.
2. Cache v1's probabilities; train v2 and the ablations.
3. Count every method on the training sites, and choose the free parameters there.
4. Only then count the test sites, once, and build the tables.

```bash
python -m pipeline.cv.optical
python -m pipeline.cv.coherence
python -m pipeline.cv.benchmark_optical --cache v1 abl_v1_s0
BASE="--sites albufera ebro camargue --label-mode three --jitter-db 1.0 --epochs 40 --samples 2048 --split-seed 0"
python -m pipeline.cv.train --name cv_v2_e2_s0 --inputs current+ref+coh $BASE --clean-labels --coh-dropout 0.15 --seed 0   # seeds 0, 1, 2
python -m pipeline.cv.train --name cv_v2_e4_s0 --inputs current+coh $BASE --clean-labels --coh-dropout 0.15 --seed 0
python -m pipeline.cv.train --name cv_v2_e5_s0 --inputs current+ref+coh $BASE --clean-labels --coh-dropout 0.15 --seed 0 --max-gap-h 13.5
python -m pipeline.cv.train --name cv_v2a_coh_s0 --inputs current+ref+coh $BASE --coh-dropout 0.15 --seed 0   # coherence only
python -m pipeline.cv.train --name cv_v2b_clean_s0 --inputs current+ref $BASE --clean-labels --seed 0          # cleanup only
python -m pipeline.cv.benchmark_optical --cache v2 abl_coh_s0 abl_clean_s0 abl_both_s0
python -m pipeline.cv.benchmark_optical --count --sites albufera ebro camargue
python -m pipeline.cv.benchmark_optical --select
python -m pipeline.cv.benchmark_optical --count
python -m pipeline.cv.benchmark_optical --score
```

Results: `data/metrics/cv_optical_select.json`, `data/metrics/cv_optical_benchmark.json`, written up in section 10 once they exist.

## 10. Results

Run on 14 and 15 Nov 2026; the test sites were counted once, at 23:59, after every parameter was chosen. Files: `data/metrics/cv_optical_select.json` (the parameters, chosen on the training sites) and `data/metrics/cv_optical_benchmark.json` (every table below, also per land type, with intervals). Scores are pooled IoU of changing open water against the optical answer key; brackets are 95 % intervals.

### Parameters chosen on the training sites

Coherence cut c = 0.25 (IoU 0.391). U-Net thresholds: v1 0.05 (0.313), v2 0.05 (0.350), the ablations 0.05. Spot filter s = 0.5 (0.308, below v2 without it). Every U-Net threshold is the lowest value tried (section 11).

### Test sites, all dates

| Method | Pego-Oliva (19 dates) | Donana (26 dates) |
|---|---|---|
| NISAR -15 dB threshold | **0.340** [0.196, 0.416] | 0.042 [0.023, 0.064] |
| NISAR dark and low coherence | 0.306 [0.128, 0.389] | **0.109** [0.079, 0.194] |
| NISAR Otsu | 0.075 [0.029, 0.138] | 0.029 [0.016, 0.046] |
| v1, pre-registered threshold 0.3 | 0.190 [0.069, 0.286] | 0.052 [0.025, 0.083] |
| v1, threshold 0.05 | 0.129 [0.052, 0.200] | 0.036 [0.019, 0.056] |
| v2 | 0.138 [0.056, 0.209] | 0.059 [0.034, 0.089] |
| v2 with spot filter | 0.149 [0.058, 0.226] | 0.067 [0.038, 0.100] |

False water as a share of the answer key's dry ground, Donana: threshold 31.7 %, v1 at 0.05 37.9 %, v2 22.2 %, dark and low coherence 5.4 %. Pego-Oliva: 0.02 to 0.8 % for every method.

Paired differences: v2 minus v1 (both at their chosen 0.05) is +0.010 [0.004, 0.013] at Pego-Oliva and +0.024 [0.014, 0.035] at Donana. Dark and low coherence minus the threshold is -0.034 [-0.130, 0.033] at Pego-Oliva (no clear difference) and +0.067 [0.040, 0.160] at Donana. The spot filter adds +0.011 [0.001, 0.019] and +0.007 [0.003, 0.013].

### Against Sentinel-1 (dates with a same-pass map)

| Method | Pego-Oliva (11 dates) | Donana (17 dates) | Training blocks (25 dates) |
|---|---|---|---|
| Sentinel-1 map (DSWx-S1) | 0.289 [0.063, 0.444] | **0.291** [0.187, 0.441] | 0.464 [0.285, 0.590] |
| NISAR -15 dB threshold | **0.382** [0.167, 0.463] | 0.056 [0.023, 0.086] | 0.375 [0.145, 0.548] |
| NISAR dark and low coherence | 0.355 [0.101, 0.442] | 0.121 [0.081, 0.236] | 0.542 [0.182, 0.676] |
| v1, threshold 0.3 | 0.272 [0.088, 0.383] | 0.083 [0.030, 0.124] | 0.469 [0.194, 0.643] |
| v2 | 0.199 [0.063, 0.291] | 0.090 [0.046, 0.130] | **0.623** [0.338, 0.795] |

v2 minus Sentinel-1: -0.090 [-0.201, 0.047] at Pego-Oliva (no clear difference), -0.201 [-0.375, -0.078] at Donana (Sentinel-1 better), +0.159 [-0.002, 0.287] on the training blocks (no clear difference, by a hair). The threshold against Sentinel-1 at Pego-Oliva was not a pre-registered pair and is not tested.

### Ablation, single seed 0, all dates

| Change against v1's seed 0 model | Training blocks | Pego-Oliva | Donana |
|---|---|---|---|
| Coherence only | +0.055 [0.035, 0.071] | -0.014 [-0.030, -0.004] | +0.023 [0.008, 0.044] |
| Coherence and label cleanup | +0.044 [0.023, 0.062] | +0.012 [-0.007, 0.024] | +0.040 [0.018, 0.069] |

The cleanup-only run was not trained (section 11).

### Per land type

- Pego-Oliva cropland: v2 0.784, threshold 0.721, v1 0.689, dark and low coherence 0.638.
- Pego-Oliva bare ground: v1 and v2 call 26 to 27 % of the dry ground water (threshold 3.4 %). That is where the U-Nets lose most at Pego-Oliva.
- Donana: dark and low coherence is the best NISAR method in every land type; on grass, shrub and wetland its false water is 5.8 % against 36 % for the threshold.

### The DANA flood (EMSR935, 877 ha labelled, every method on the same pixels)

| Method | Water gain IoU | Precision | Recall | New water | Before-flood control IoU |
|---|---|---|---|---|---|
| v1, threshold 0.3 | **0.305** | 0.82 | 0.33 | 349 ha | 0.074 |
| v2, coherence withheld on both dates | 0.303 | 0.79 | 0.33 | 364 ha | 0.117 |
| v2 with spot filter, coherence withheld | **0.309** | 0.78 | 0.34 | 383 ha | 0.101 |
| v1, threshold 0.05 | 0.269 | 0.80 | 0.29 | 316 ha | 0.211 |
| Sentinel-1 map | 0.230 | 0.66 | 0.26 | 343 ha | 0.185 |
| NISAR -15 dB threshold | 0.230 | 0.93 | 0.23 | 220 ha | 0.137 |
| NISAR Otsu | 0.203 | 0.87 | 0.21 | 211 ha | 0.249 |

Not comparable (coherence on 16 Oct only): dark and low coherence 0.291, v2 0.292, v2 with spot filter 0.304.

### Dates without coherence (descriptive only)

Pego-Oliva, 28 Oct on two tracks: threshold 0.471, v1 0.361, v2 0.347. Donana, three dates: every NISAR method below 0.11.

### Reading

1. **No method wins everywhere.** On new flood water the U-Nets lead (about 0.30 against 0.23 for the Sentinel-1 map and for the threshold). On everyday water at Pego-Oliva the plain threshold leads. On Donana's dry marsh the Sentinel-1 map leads, and among NISAR methods the coherence rule.
2. **Coherence works where smooth dry ground is the error.** At Donana it cuts false water from 32 % to 5 % of the dry ground, and it costs recall where marsh water keeps some coherence (Pego-Oliva).
3. **v2 beats v1 at both test sites, by 0.01 and 0.02 IoU:** a real gain, but small. On the flood the two are level.
4. **Thresholds chosen on the training sites do not carry over.** At 0.05 the U-Nets call too much water on bare ground at Pego-Oliva; v1's pre-registered 0.3 scores higher there (0.190 against 0.129).
5. **Limits.** One season, two test sites, one flood; the answer key cannot see water under plants and drops muddy water; the Pego-Oliva intervals are wide.

## 11. Changes after the first score

1. **Grids extended once, downwards (14 Nov, 21:05, training sites only, before any test site was scored).** On the training sites' validation blocks the best coherence cut and the best v1 threshold were both the lowest value of the first grid (c 0.25 with IoU 0.391, v1 0.15 with 0.267), so a better value could lie below. Each grid got two lower values: c 0.15 and 0.2, thresholds 0.05 and 0.1. Result: c stays at 0.25, now inside the grid (0.15: 0.376, 0.2: 0.385, 0.25: 0.391, 0.3: 0.384). v1 is still best at the lowest threshold tried, 0.05 (IoU 0.313); its score keeps rising as the threshold drops, so its probabilities run far below the optical water. The grids are not extended again.
2. **Fixes from an independent code review (14 Nov, 21:30, before any test site was scored against the answer key).** The review found no leak of test data. It found five problems in how results would be reported, all fixed:
   - intervals that collapse to their point when no stack has two dates (the split by coherence);
   - a DANA check that built before and after differently for coherence methods, and scored methods on slightly different pixels (Sentinel-1's masked pixels; 29 U-Net pixels);
   - "the 12-day pair" stated in this protocol where 14 dates use a longer pair (now stated in section 6);
   - a future pair that could be borrowed by any date without an ending pair, not only the first date (it never happened; now impossible);
   - caches that were not tied to the exact checkpoints (now a manifest with the checksum of each model, checked before counting).

   The remaining fixes: ties are judged on exact counts, intervals are given for every metric, and dates without an optical image are listed as skipped.
3. **One check run dropped (14 Nov, 23:39, before any test site was scored).** The cleanup-only check run (`cv_v2b_clean_s0`) was stopped after 5 minutes so the results come sooner. Its half-trained checkpoint was deleted and it is not reported. The coherence-only check run and every v2 model finished as planned. To measure the DANA problems, the reviewer ran the DANA check at Pego-Oliva for methods 1 to 4 and v1 with the parameters already chosen. No parameter was changed after that, and no test-site score against the answer key was computed.

Written with SI assistance (Claude Code), reviewed by the team.
