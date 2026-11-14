# Lorca prediction baseline

The first runnable prediction component: **one real displacement series → three baselines → chronological backtests → forecast JSON, metrics, and a chart**.

Owner: **Zhivko Stoimchev (`@zstoimchev`)**. Implementation assisted by OpenAI Codex. The included example uses observed GNSS data from the Nevada Geodetic Laboratory (NGL); it is not a NISAR result. EGMS Vertical CSV ingestion is implemented and tested, but the example has not yet imported an actual EGMS download or validated against NISAR.

## Run from the repository root

Python 3.11+ (the shared `pyproject.toml`); no GPU, Earthdata account, or web server is required for the NGL example.

```bash
python -m pip install -e ".[dev,prediction]"
python -m pipeline.prediction run --as-of 2026-11-14   # reads the committed data/context/lorca_gnss_LOR1_up.csv
python -m pytest -q
```

Use `python3` if that is your Python executable. The same commands work from a checked-out repository in Colab. Without `--as-of`, the forecast origin defaults to today's UTC date. `run` reads the cached input and makes no network requests. `fetch` explicitly refreshes the small public input, records its SHA-256 and retrieval time, and stores it under ignored `data/raw/ngl/`.

The first verified run used Python 3.14.8, NumPy 2.5.4, and Matplotlib 3.10.8. Runtime versions are exported in `metrics.json`; the dependency ranges also allow Colab environments to resolve compatible versions.

## Outputs for the application

The default output directory is `data/prediction/lorca/`:

| File | Purpose |
| --- | --- |
| `forecast.json` | Selected forecast and all three model alternatives, issue time, data cutoff, future target dates, intervals, units, and source |
| `metrics.json` | Development/calibration/test scores, empirical interval coverage, sample counts and actual scored date ranges, fit configuration, input checksum, software versions |
| `observations.csv` | Retained real observations, normalized to the first retained date in millimeters |
| `backtest.csv` | Every rolling prediction, observed target, training dates, model, error, and split |
| `chart.png`, `chart.svg` | Standalone figures for inspection or presentation |

The run also upserts one entry in `data/manifest.json`, the shared list format keyed by `(model, site, stack, layer)` that the CV and ML models use (`stack` is `<source>_<point>`, e.g. `gnss_LOR1`; `layer` is `vertical_motion`; `date` records the forecast origin), preserving every other entry. A re-run replaces its entry; git history keeps earlier forecasts. Prediction entries identify their actual source type and do not invent a NISAR granule ID. Paths are repository-relative when the default output directory is used. Copy the manifest and referenced files into the web app's public assets while retaining their relative paths.

Use a separate `--output` directory for each point/source. The command refuses to overwrite an existing output that belongs to a different point, site, or source type.

The frontend can read `forecast.json` directly:

- `predictions` contains one selected result for each requested horizon.
- `model_predictions` contains all alternatives for comparison.
- `value_mm` is displacement relative to `reference_date`. **Positive is upward; negative is downward.**
- `delta_since_last_observation_mm` is the predicted change from the most recent retained observation.
- `intervals.80` and `intervals.95` contain lower/upper bounds in the same units, calibration counts, and availability status. Missing bounds are `null`, never fabricated.
- `backtest_at_effective_lead` provides historical scores for the lead actually being forecast.
- `nisar_validation.status` explicitly remains `not_performed` for this milestone.

The output is a statistical displacement estimate. It does not establish damage, pumping causation, or the movement of nearby locations.

## Models and date handling

Models are fitted with NumPy least squares, without a trained neural network:

1. **Persistence:** predict the latest observed value.
2. **Linear:** fit an intercept and a linear trend in elapsed years.
3. **Trend + annual cycle:** fit intercept, trend, and both annual sine and cosine terms, so seasonal phase is learned.

Defaults use a rolling 1,096-day window, at least 100 observations, and at least 730 days of observed time span. The same eligibility rules apply to all three models so comparisons use the same targets. No missing dates are interpolated. Forecasts are scored at exact observed target dates by default.

The default split is:

| Split | Origin and target dates | Role |
| --- | --- | --- |
| Development / selection | 2023 | Choose the lowest-MAE model separately for each lead |
| Calibration | 2024 | Estimate absolute-error ranges for each model and lead |
| Held-out test | 2025 | Report MAE, RMSE, skill, and interval coverage; never select the model |

Each backtest origin trains only on observations at or before that origin. Targets must also remain within their split, preventing calibration outcomes from crossing into the test period. Origins advance by at least seven calendar days. Missing dates and insufficient training history reduce the scored sample. Actual first/last origins, targets, and counts are in the metrics, not assumed to cover the whole named year.

The default source has a **599-day missing-observation gap** between December 2021 and August 2023, plus a 74-day gap in early 2025. With the two-year minimum training span, the 2025 test scores start in August. They describe this limited subset, not year-round or general performance. The development period also begins after a long gap, so its selected model may not suit the current regime.

### Forecast issue date versus observation date

The committed station file (`data/context/lorca_gnss_LOR1_up.csv`, from `pipeline.context`) ends on **31 October 2026**. The run has forecast origin **14 November 2026**, making the latest observation 14 days old. Targets are therefore:

| From forecast origin | Target | Lead from the last observation |
| --- | --- | --- |
| +12 days | 26 November 2026 | 26 days |
| +24 days | 8 December 2026 | 38 days |
| +36 days | 20 December 2026 | 50 days |

The pipeline evaluates/calibrates those longer effective leads as well as the standard 12/24/36-day comparisons. It does not apply a 12-day error range to a 40-day extrapolation. `issued_at_utc` is the actual execution timestamp; `forecast_origin` is the requested as-of date, and `data_cutoff` is the latest observation used. An explicit past `--as-of` is a retrospective scenario, not proof that a forecast was published at that historical time.

### Error ranges and scores

Ranges use a held-out calibration set's absolute rolling forecast errors, with order-statistic rank `ceil((n + 1) × coverage)`. If that rank exceeds the available calibration sample, the bound is unavailable. The method resembles split-conformal calibration, but dependent errors and changing ground-motion regimes prevent a general coverage guarantee. These outputs are labeled **historical-error ranges**, and their measured test coverage and width are reported.

`skill_vs_persistence = 1 - MAE_model / MAE_persistence`: positive means smaller error than persistence. If persistence has zero MAE, skill is `null` rather than an infinite value. Weekly origins and multiweek forecasts overlap, so sample counts are not independent replication counts.

These backtests use today's provider data release. They are not a simulation of the provider's historical publication latency or past processing versions.

## First real-data results

The run contains **1,807 retained observations from 1 January 2020 through 31 October 2026**. Held-out MAE in millimeters:

| Horizon | Scored targets | Persistence | Linear | Trend + annual cycle |
| --- | ---: | ---: | ---: | ---: |
| 12 days | 20 | 2.580 | 3.654 | 3.337 |
| 24 days | 19 | 4.543 | 3.915 | 4.175 |
| 36 days | 17 | 5.065 | 4.667 | 5.011 |

The earlier development split selected **persistence** at all required leads. The selected future forecast therefore predicts zero additional change from the last observed position, with ranges; all trend forecasts are still exported. This is a baseline result, not evidence that the ground will stop moving. We do not change the selected model after looking at final test winners. A later model/window/regime comparison needs a newly reserved evaluation period before claiming improvement.

### Why persistence wins, and the antenna change (issue #16)

LOR1 had an antenna-height change on 2023-08-03 (0 → 0.0771 m), the first day after a 600-day data gap (Dec 2021 – Aug 2023). It does **not** explain the result. Trends fitted on either side of the gap meet with the ground about 60 mm *lower* after it, while an uncorrected antenna raised by 7.7 cm would show up as a jump *upward*. NGL heights already refer to the ground marker. What the data shows is a change in the sinking itself:

| Period | Vertical rate |
| --- | ---: |
| 2016–2021 | ≈ −55 to −63 mm/yr |
| Dec 2021 – Aug 2023 (gap) | ≈ −95 mm/yr |
| 2023–2026 | ≈ −33 to −45 mm/yr |

The 2023 selection period sits right after that change, so its 3-year training windows mix two regimes, and the trend models lose to persistence there (MAE 11–14 mm vs 6–8 mm). The trend models now take a **step term at each equipment change** (`models.py`, from the antenna column), which is standard for GNSS. It does not change the selection: the regime change is in the rate, not just the level.

On the held-out 2025 test, linear trend beats persistence by 14 % at 24 days and 8 % at 36 days, trend + annual cycle by 8 % and 1 %. Selection was on 2023, and switching after seeing the test would be choosing on it. The EGMS history (2020–2025, no gap) is the fair way to revisit this.

## Use an actual EGMS Ortho Vertical CSV

Download a vertical product through [EGMS Explorer](https://egms.land.copernicus.eu/) using your EU Login. Select a `pid` from that CSV, then run:

```bash
python -m pipeline.prediction run \
  --format egms \
  --input data/raw/egms/vertical.csv \
  --point-id YOUR_ACTUAL_PID \
  --output data/prediction/lorca-egms \
  --target-tolerance-days 3 \
  --as-of 2026-11-14
```

Only the selected row's `YYYYMMDD` columns become displacement observations. The input must be the **vertical** component, already in mm. No velocity or seasonality summary field is used as a predictor, since these provider summaries may incorporate future dates relative to a historical backtest. The EGMS grid coordinates remain EPSG:3035; scalar displacement does not need reprojection to fit the model.

`--target-tolerance-days 3` accommodates a six-day observation grid. It scores predictions at the actual nearest available target date within that tolerance, records the actual lead, and never interpolates labels. Consequently these are approximately matched, not exact-day scores. If a numeric no-data sentinel is present, specify it with `--nodata-value`. Blank and nonfinite observations are omitted; zero displacement remains valid. Fewer usable targets can make error ranges unavailable or require different split dates.

## What remains after this milestone

- Import and inspect an actual EGMS Vertical point or small group, preserving the product release and reference metadata.
- Equipment changes are modelled as steps (above); earthquake offsets are not. The 2023 rate change means a single trend is not a physical explanation either.
- Build a corrected NISAR GUNW comparison with coherence/connected-component checks and matching motion geometry. Vertical and line-of-sight motion must not be subtracted directly.
- Resolve the GUNW input workflow: MintPy's NISAR loader expects HDF5 products and metadata, not only the Harmony intensity/phase COGs used elsewhere.
- Add Albufera water-area forecasting as a separate series/pipeline with its own units, coverage rules, and validation. It is not implemented in this milestone.

## Source references

- [NGL LOR1 station and data links](https://geodesy.unr.edu/NGLStationPages/stations/LOR1.sta); cite provider processing as Blewitt, Hammond & Kreemer (2018), [Harnessing the GPS Data Explosion](https://doi.org/10.1029/2018EO104623), and credit the station operator identified by NGL.
- [NGL tenv3 format](https://geodesy.unr.edu/gps_timeseries/readmes/README_tenv3.txt): integer plus fractional vertical coordinates are converted from meters to mm; antenna height is retained as provider context, not subtracted again.
- [EGMS product description and format](https://eea.github.io/CLMS_documents/develop/products/European_Ground_Motion_Service_Product_Description_v3.html): Ortho time-series columns, units, grid, and component definitions.
- [ASF NISAR phase guidance](https://nisar-docs.asf.alaska.edu/phase/): line-of-sight deformation and coherence interpretation for the later integration.
