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

Coherence of a date: the pair that ends on that date, with the latest reference date (the 12-day pair; only the past is used, as in real use). For the first date of a stack, the pair that starts on it, with the earliest secondary date. Otherwise none (the U-Net sees the channel mean).

Found before training: 14 of the 132 dates with HV have no pair, all of them the newest dates (23 Oct to 6 Nov), after NISAR's switch to validated processing on 21 Oct, for which no GUNW pairs are published yet. They include 28 Oct, the DANA after-flood date. So that v2 does not break where coherence is missing, 15 % of its training crops have the coherence channel blanked (`--coh-dropout 0.15`), and its results are also reported split by whether the date has coherence.

Ablation, single seed 0 (what each change does on its own): v1's seed 0 model; coherence only; cleanup only; both.

Training of v2: `--sites albufera ebro camargue --label-mode three --jitter-db 1.0 --epochs 40 --samples 2048 --split-seed 0`, as v1. The dB jitter shifts HH, HV and the reference channels, never coherence. The validation blocks come from the uncleaned labels, so they are the same as v1's.

## 7. Free parameters

Each is chosen on the training sites' validation blocks only ("all dates" set), by the highest pooled IoU of changing open water against the answer key. Ties go to the value listed first. Nothing is chosen on a test site.

| Parameter | Grid |
|---|---|
| c, method 4 | 0.25, 0.3, 0.35, 0.4, 0.45, 0.5 |
| threshold, U-Nets (v1 re-tuned, v2, ablations) | 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5 |
| s, spot filter (at v2's threshold) | 0.5, 0.6, 0.7 |

The checkpoint epoch of each v2 model is chosen as for v1: pooled IoU of changing open water on the validation blocks against the (here cleaned) Sentinel-1 labels.

## 8. Metrics

- Per test site, and for the training sites' validation blocks: pooled IoU, precision and recall of changing open water, and false water as a share of the answer key's dry ground. Each for all land types together and per land type.
- 95 % intervals: 2000 bootstrap draws of dates, resampled within each stack, seed 0. Paired differences on the same draws: v2 minus v1; v2 minus Sentinel-1; v1 minus Sentinel-1; method 4 minus method 2; v2 with spot filter minus v2; each ablation minus v1's seed 0 model.
- The test sites again, split into dates with and without a coherence pair.
- The DANA flood: water gain IoU, precision, recall and the before-flood control, for methods 1 to 7.
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

Not yet run.

## 11. Changes after the first score

None yet.

Written with SI assistance (Claude Code), reviewed by the team.
