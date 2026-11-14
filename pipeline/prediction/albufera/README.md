# Albufera rice-field flooded area

Forecasts how many hectares of the Albufera rice fields are under water on the next passes, from the Sentinel-1 water history (OPERA DSWx-S1, every pass since 21 Aug 2024). This is the deliberate, seasonal flooding of the rice fields (the *perellonà* in winter, sowing in May), not a disaster flood forecast.

## Run

```bash
pip install -e ".[dev,prediction]"
python -m pipeline.prediction.albufera history --download   # 413 passes, ~2 min, needs the Earthdata login (~/.netrc)
python -m pipeline.prediction.albufera all --as-of 2026-11-14
```

`history` without `--download` only lists the passes and needs no login.

## How

1. **Rice mask** (`mask.py`, 14,791 ha): CORINE 2018 rice (class 213) where a pixel is at least 60 m inside a rice polygon (the ML rule from #13) or JRC saw it as seasonal water, minus towns, permanent water and sea. The first version (JRC seasonal water only, 10,876 ha) missed about a third of the rice (Luka's review on #8). The new one holds 49 of Luka's 50 hand-drawn fields completely, and the last at 97 %.
2. **Flooded hectares per pass** (`area.py`): DSWx-S1 open water (1) + inundated vegetation (3) inside the mask, on the 20 m site grid. Passes that see less than 90 % of the mask are not used (396 of 413 usable).
3. **Models** (`forecast.py`): persistence, day-of-year climatology (median within ±10 days in other seasons), and climatology + today's anomaly fading with a 30-day e-folding time (fixed in advance).
4. **Scoring**: each past season (Aug–Jul) is predicted from the other one; this picks the model per lead and sets the 80/95 % ranges. The current season (Aug 2026 on) is the test, predicted only from earlier seasons. It is never used to choose anything.

## First real run (forecast made 14 Nov 2026, data to 10 Nov)

| Target | From 14 Nov | Real lead (from last data, 10 Nov) | Forecast | 80 % range | Model |
|---|---:|---:|---:|---:|---|
| 26 Nov 2026 | +12 d | 16 d | 4,351 ha | 3,194–5,507 | climatology |
| 8 Dec 2026 | +24 d | 28 d | 4,183 ha | 2,983–5,383 | climatology |
| 20 Dec 2026 | +36 d | 40 d | 4,707 ha | 3,475–5,939 | climatology |

The model and the ranges are chosen at the real leads (16, 28, 40 days; `effective_lead_days` in `forecast.json`), not the nominal 12, 24, 36.

Held-out test season, mean absolute error in hectares (skill = error reduction vs persistence), at the backtest leads and at the real leads of this forecast:

| Lead | Persistence | Climatology | Climatology + anomaly | 80 % range hit |
|---:|---:|---:|---:|---:|
| 12 d | 776 | 565 (+27 %) | 498 (+36 %) | 80 % |
| **16 d** | 996 | 583 (+42 %) | 580 (+42 %) | 80 % |
| 24 d | 1,386 | 651 (+53 %) | 600 (+57 %) | 77 % |
| **28 d** | 1,690 | 671 (+60 %) | 638 (+62 %) | 77 % |
| 36 d | 1,828 | 768 (+58 %) | 759 (+59 %) | 73 % |
| **40 d** | 2,187 | 791 (+64 %) | 784 (+64 %) | 73 % |

The test season holds 11 to 15 forecasts per lead, so these numbers are rough. Selection preferred plain climatology at every lead; the anomaly model did slightly better on the test season. That is reported, not acted on: switching now would be choosing on the test.

Outputs: `data/prediction/albufera/` (`forecast.json`, `metrics.json`, `backtest.csv`, `water_area.csv`, `chart.png`/`.svg`, `rice_mask.tif`/`.json`) and a `data/manifest.json` entry (`stack: dswx-s1`, `layer: flooded_area`).

## NISAR check

`python -m pipeline.prediction.nisar_check` (needs the `albufera_066_D_069` stack from `pipeline.nisar_fetch` + `pipeline.stack`). Share of the rice mask darker than −15 dB on NISAR (5×5 filtered HH) vs the share DSWx-S1 maps as flooded on the Sentinel-1 pass within 2 h (the 18 UTC pass, as in `pipeline.cv.evaluate`; 5 of the 11 dates have one):

| Date | NISAR dark | DSWx-S1 flooded | Non-rice cropland (NISAR) |
|---|---:|---:|---:|
| 18 Jun | 43.7 % | 1.7 % | 1.2 % |
| 30 Jun | 13.4 % | – | 0.3 % |
| 12 Jul | 5.4 % | – | 0.2 % |
| 24 Jul – 22 Sep (5 dates) | 0.1–0.3 % | 0.2 % (22 Sep only) | 0.0–0.1 % |
| 4 Oct | 5.8 % | 2.5 % | 0.0 % |
| 16 Oct | 13.7 % | 9.8 % | 0.1 % |
| 28 Oct | 31.0 % | 21.7 % | 0.3 % |

In the autumn flooding this forecast predicts, the L-band and C-band series rise together. In June, NISAR sees much more water. The rice calendar has the paddies flooded from May sowing to the August drainage, so this is most likely water among young rice that DSWx-S1 misses, but it is not confirmed on the ground. A fixed threshold is used because the per-scene Otsu threshold follows the whole scene (sea, towns) and called about 90 % of the rice "water" in June and 64 % and 39 % on the two September dates. Correlation over the 5 paired dates: 0.34 at −15 dB (18 Jun pulls it down), 0.65 at −18 dB, 0.14 with Otsu; with five points, read the series rather than r.

## Caveats

- Radar misses some water: wind roughens it, and dense stubble hides it. The peak (≈ 4,000–5,000 ha) is below the ≈ 8,000 ha of flooded fields the Generalitat cites for the perellonà, so read the numbers as "what Sentinel-1 sees", consistent from year to year.
- Two past seasons only; the ranges are wide on purpose.
- Flood water from storms lands in the fields too (the 7,800 ha spike on 1 Nov 2024 is the 29 Oct 2024 DANA). The flood model in `pipeline/prediction/flood/` handles storms; this one does not.

Sources: OPERA DSWx-S1 (NASA JPL / PO.DAAC), CORINE Land Cover 2018 (© European Union, Copernicus Land Monitoring Service 2018, EEA), ESA WorldCover 2021, JRC Global Surface Water (EC JRC/Google).
