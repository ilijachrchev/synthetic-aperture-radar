# Prediction plan

Owner: **Zhivko Stoimchev** (`@zstoimchev`) · Written 14 Nov 2026, hackathon day 2 of 3 (13 to 15 Nov).

Sources: PRs #1 to #5 on `ilijachrchev/synthetic-aperture-radar` and their discussion, [MODELS.md](MODELS.md), [RESEARCH.md](RESEARCH.md), [DATA.md](DATA.md), and the local prediction code. New to radar? Read [SAR_PRIMER.md](SAR_PRIMER.md) first.

---

> **Status, 14 Nov 2026 14:00:** steps 0, 1 and 3 below are done and merged (#8, #14, #15, #17), and the flood alert (option C from #9) was added. Step 1 found that the antenna is not the cause (see the Lorca README). The NISAR check of step 4's idea is done for Albufera and the DANA (`nisar_check.py`, see MODELS.md). Still open: step 2 (EGMS, needs an EU Login download) and the GUNW part of step 4. Current summary: [MODELS.md → Prediction model](MODELS.md#prediction-model).

## 1. What the team decided, and why

| Decision | Where | Why |
|---|---|---|
| **One chain, not three separate models: DATA → STACK → DETECT → PREDICT** | Ilija's answer to your question in PR #4; you and Luka agreed | About 11 NISAR images per track and a handful of events: too little for one big model. Each step feeds the next |
| **Prediction forecasts only slow or repeating things**: (A) Lorca ground sinking, (B) Albufera rice-field flooded area | PR #4 comment, RESEARCH.md §6, MODELS.md | Those can be forecast honestly and checked |
| **No earthquake prediction, no flood prediction from radar, no soil moisture, no flood recession** | PR #4, RESEARCH.md §6 and §8 | Quakes can't be predicted; floods come from rain (needs weather forecasts); soil moisture fades in about 4 days but the revisit is 12; judges know all this |
| **Long history comes from other sensors**: EGMS (2020 to 2025) for Lorca, Sentinel-1 DSWx (since Aug 2024) for Albufera | PR #4, MODELS.md | NISAR over Spain only starts Jun 2026 |
| **Lorca: trend + yearly cycle, backtested (train 2020 to 2023, test 2024 to 2025), then checked against NISAR GUNW** | MODELS.md, RESEARCH.md §6 | NISAR is an independent sensor, so the comparison is a real out-of-sample test: the headline result |
| **Albufera: day-of-year baseline + current anomaly, leave one season out, skill vs persistence; forecast committed to git *before* the data arrives** | MODELS.md, RESEARCH.md §6 | A timestamped forecast made before the data is published can't have been tuned to it |
| **Prediction uses DSWx-S1, not the CV masks** | MODELS.md | So prediction never waits on CV |
| **Every forecast shows a range, a skill score against a naive baseline, and "forecast made on [date]"** | RESEARCH.md §6 | Honesty is what the judges reward; "AI predicts disasters" is a listed trap |
| **Shared output**: forecast JSON + an entry in `data/manifest.json`; analysis grid EPSG:32630, 20 m | MODELS.md "Shared between the models" | One format so the web app reads all three models the same way |
| **Harmony for NISAR subsets** (no HDF5 code), one stack per site and track, never mix tracks | PR #2, PR #5, RESEARCH.md §9 | Simpler, and tracks have different geometry |
| **PR #3 (your codex plan) closed; its good parts are in RESEARCH.md §9** (Harmony, linear power, mask ≠ water). Dropped: "no models", catalog dumps, React + Vite | PR #3, RESEARCH.md §9 | |
| **ML land-cover classifier is optional** | Ilija, PR #4 | Not on the critical path |

## 2. Who does what

| Person | Role | Status |
|---|---|---|
| **Ilija Chrchev** (`ilijachrchev`) | Data pipeline + stacks (PR #5, open) · **CV**: water, flood and burn masks | Pipeline built; CV baseline in `pipeline/cv/`; U-Net later |
| **Luka** (`georgieskiluka`) | **ML** land-cover / change classes (`pipeline/ml`, not pushed yet) · reviewed PR #5 | Adapting to the new stack format |
| **You** | **Prediction**: Lorca (A) and Albufera (B) | Lorca GNSS baseline built locally, uncommitted |
| *Unassigned* | Web app (Next.js) · Panama ground-motion display · Lorca GUNW processing | **Ask the team** (see §6) |

## 3. What is already done

**By Ilija (PR #5, now merged into your local `feat/predictions`, not yet into `main`):**

- `pipeline.config`: site boxes including **`lorca`** (−1.80, 37.55, −1.45, 37.85) and the site grid (`pipeline.stack.site_grid`).
- `data/catalog/lorca.json`: every NISAR file over Lorca, including **GUNW on 3 tracks: 159 A (19), 66 D (16), 167 D (15)**. Ascending + descending means vertical motion can be separated out.
- `data/context/lorca_gnss_LOR1_up.csv`: LOR1 daily height **2009-09-12 to 2026-10-31**, with antenna height. Ilija flags an **antenna change on 2023-08-03** (0 → 0.0771 m) that may put a step in the series.
- `pipeline.dswx`: downloads DSWx-S1 water maps, but **only for days that have a NISAR pass** (since Jun 2026): the CV label use case. No history mode yet.
- `data/context/albufera_worldcover_2021_20m.tif` and `albufera_jrc_occurrence_20m.tif` on the Albufera grid. Luka found that **JRC 1 to 89 % covers about 16 % of the box ≈ the seasonally flooded rice fields**, and **≈ 30 % of the box is sea**. Both matter directly for forecast B.

**By you (local, uncommitted):** `pipeline/prediction/` + `tests/test_prediction.py` (18 tests pass)

- Loads NGL LOR1 (`fetch`) and EGMS Ortho vertical CSV (tested, but no real EGMS file imported yet).
- Three models: persistence, linear trend, trend + annual sine/cosine (NumPy least squares).
- Rolling-origin backtest with a 2023 selection / 2024 calibration / 2025 test split, empirical error ranges (80 % and 95 %), skill vs persistence, handling of stale data ("effective lead").
- Exports `forecast.json`, `metrics.json`, `backtest.csv`, `observations.csv`, chart PNG/SVG, and a `forecasts` entry in `data/manifest.json`.
- **Result: persistence was selected at every lead**, so the forecast says "no further change". Trend models were close (held-out MAE 3.3 to 5.0 mm vs persistence 2.6 to 5.1 mm). Honest, but a weak demo, and it contradicts about 4 cm/yr of known sinking. Likely causes: the 599-day data gap (Dec 2021 to Aug 2023), the **2023-08-03 antenna step right at the end of that gap**, and short test windows.

**Not started:** real EGMS import, NISAR GUNW comparison, the whole Albufera forecast (B).

## 4. What to build next, in order

Time is short (the hackathon ends 15 Nov), so the list is ordered by **value per hour**. Each step is a natural commit.

### Step 0: Land your work on top of Ilija's (≈ 30 min)

Ilija's pipeline is already in your working tree (fast-forwarded to `upstream/feat/data-pipeline`; your README, MODELS and `.gitignore` edits merged cleanly).

- Add a `prediction` extra to `pyproject.toml` (`matplotlib`) and drop `pipeline/prediction/requirements.txt`, so there is one install: `pip install -e ".[dev,prediction]"`.
- Read site and paths from `pipeline.config` (`get_site("lorca")`, `DATA_DIR`) instead of hard-coding them.
- Add a loader for Ilija's committed `data/context/lorca_gnss_LOR1_up.csv`. It is newer (to 31 Oct) and avoids a second copy of the same data. Keep `fetch` as an optional refresh.
- Commit and open a PR into `main` **after PR #5 merges** (or target `feat/data-pipeline` now and retarget later).

### Step 1: Fix the LOR1 antenna step (≈ 1 h, high value)

- Check whether NGL's `up` is already reduced to the ground marker. If it is, the antenna change cancels out; if not, there is a ~7.7 cm jump. Also check NGL's step file for LOR1 (it lists equipment and earthquake steps).
- Add an optional **step term** at known step dates to the linear and trend + annual models (one extra column in the least-squares design matrix).
- Re-run with the frozen split. If trend now beats persistence on the 2023 *selection* period, that is a legitimate change because it fixes a known data problem. Do not choose based on the 2025 test results.

### Step 2: Real EGMS for Lorca (≈ 1 to 2 h; needs your EU Login)

- Download EGMS **Ortho vertical** (2020 to 2025) for the Lorca box from EGMS Explorer.
- Pick a few points: the one **nearest LOR1** (cross-check EGMS against GNSS: they should agree, which validates both), a point at the **centre of the subsidence bowl** (largest rate), and a **stable reference** point outside the basin.
- Run the existing pipeline per point (`--format egms --target-tolerance-days 3`). EGMS has no 2021 to 2023 gap, so the trend models should finally have clean history.
- Stretch goal: run every point in the box and export a **rate + forecast map** (one value per point) for the web app.

### Step 3: Albufera flooded-area forecast, B (≈ 3 to 4 h; time-critical)

**Why now:** the rice fields are flooded again around November to January. A forecast for the next passes, committed today, can be checked against new data during or right after the hackathon. That check is the honest, timestamped result the team asked for.

1. **History fetch**: add a date-range mode to `pipeline.dswx` (reuse `search_day`, `wtr_url`, `group_passes`): every DSWx-S1 pass over Albufera since Aug 2024, `B01_WTR` only.
2. **Rice area mask** on the Albufera site grid: WorldCover 40 (cropland) **and** JRC occurrence 1 to 89 %, **minus** Ilija's `data/context/albufera_sea_20m.tif` (added after Luka's review: 28 % sea, lagoon kept separate). This excludes the sea, the lagoon and towns. Commit it to `data/context/`.
3. **Series**: per pass, hectares of open water + inundated vegetation inside the mask (DSWx classes 1 and 3), plus the observed fraction (skip passes where classes 250, 251 and 255 cover too much). Resample DSWx (30 m) onto the 20 m grid by nearest neighbour.
4. **Models**: persistence · day-of-year climatology (from the other season) · climatology + current anomaly (decaying toward climatology).
5. **Check**: leave one season out (train on 2024–25, test 2025–26, and the reverse), MAE and skill vs persistence, ranges from the held-out errors (reuse `evaluation.interval_radius`).
6. **Forecast**: hectares for the next DSWx/NISAR pass dates, with ranges → `data/prediction/albufera/forecast.json` + manifest entry. **Commit it with a timestamp before those dates.**
7. Optional cross-check: hectares from Ilija's CV masks on NISAR dates against DSWx hectares on the same day (L-band vs C-band).

### Step 4: NISAR GUNW check for Lorca, A (≈ half a day; the headline, but the riskiest)

Do this after steps 1 to 3 are safe. A smaller honest version beats an unfinished full one.

- **Minimal version**: the LOR1 pixel only. Take GUNW 167 D (15 pairs), read unwrapped phase, coherence and connected components; apply the shipped **ionosphere and troposphere corrections**; convert phase to LOS mm (`d = -λ/4π · φ`); reference to a stable pixel; chain the pairs into a series. Project the GNSS east/north/up (all three are in `LOR1.tenv3`) into the 167 D line of sight and compare. You need the per-pixel LOS vector from the GUNW metadata.
- **Then**: compare the **EGMS-trained forecast for Jun to Oct 2026** with NISAR (projected to LOS, or combine 159 A + 66 D/167 D into vertical). This fills in the `nisar_validation` block that is currently `not_performed`.
- **Open technical question**: MintPy wants the GUNW **HDF5 with metadata**, not Harmony COGs. Either stream the HDF5 subset directly, or ask Harmony for the needed layers plus geometry. Decide after testing one file.

### Step 5: Hand-off to the web app

- Agree the forecast JSON contract with whoever builds the web app: a fan chart of the median, 80 % and 95 % ranges; "forecast made on" from `forecast_origin` / `issued_at_utc`; skill vs baseline shown next to it.
- Keep `forecast.json` small and stable; document fields in `pipeline/prediction/README.md` (already mostly done).

## 5. Done when

From MODELS.md: **both forecasts have ranges, backtest scores and a committed, timestamped forecast file.** Plus, as stretch goals: the Lorca forecast compared with NISAR, and a map of EGMS rates.

## 6. Open questions for the team

1. **Who builds the web app?** Nobody is assigned, and every model's output ends there.
2. **Who processes GUNW ground motion?** Ilija's PR #4 split put "ground motion for Lorca and Panama" with the data role, while MODELS.md puts it under Prediction. Lorca GUNW is assumed to be yours; Panama (display only) needs an owner.
3. **Merge order**: PR #5 first, then prediction. OK?
4. Luka's PR #5 points 1 (PROVISIONAL → VALIDATED brightness jump) and 2 (sea in the Albufera box) also affect forecast B. Step 3 handles the sea with the rice mask; DSWx is Sentinel-1, so point 1 doesn't apply to the history.
5. SI disclosure: your prediction README credits OpenAI Codex; the rest of the repo credits Claude Code. Both are fine as long as the README lists both (it does).

<sub>Drafted with SI assistance (Claude Code) from the PR discussions and repository docs; the decisions are the team's.</sub>
