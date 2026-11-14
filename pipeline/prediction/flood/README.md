# Rain-threshold flood alerts (option C)

A traffic light per site for "new flood water on the next Sentinel-1 pass", from the largest 3-day rain total. Option C from discussion #9. The Oct 2026 DANA ("Adam", 18–19 Oct) is held out at both sites and used only as the test.

## Run

```bash
pip install -e ".[dev,prediction]"
python -m pipeline.prediction.flood history --site albufera --download     # Earthdata login (~/.netrc)
python -m pipeline.prediction.flood history --site pego_oliva --download
python -m pipeline.prediction.flood all --as-of 2026-11-14
```

Rain comes from Open-Meteo with no key.

## How

1. **Water** (`water.py`): flooded hectares (DSWx-S1 open water + inundated vegetation) per pass in each site's zone. The zone is land the radar sees in ≥ 80 % of passes: not sea, not permanent water, not towns, and at Albufera not the rice mask (flooded on purpose). Albufera 26,819 ha, Pego-Oliva 37,165 ha, 413 passes each since 21 Aug 2024.
2. **Label** (`model.py`): a date is flooded when its water exceeds the median of the previous 30 days by at least max(50 ha, 5 × robust spread). It is a *new* flood if the previous date was not flooded. Dates still flooded from before are left out.
3. **Rain** (`rain.py`): ECMWF IFS 9 km via Open-Meteo, the wettest point of a 0.1° lattice over the site. Feature: the largest 3-day total between the previous pass and the day before this one.
4. **Threshold**: **100 mm in 3 days**, the published anchor for flash floods in Valencian ephemeral streams (Camarasa-Belmonte 2016, 142 events). It was proposed in #9 before our data was looked at.
5. **Live alert**: share of the 51 ECMWF ensemble members whose largest 3-day total in the next 3 days reaches the threshold. Red ≥ 50 %, amber ≥ 10 %.

All numbers in steps 2 to 5 were fixed before the results were seen, except the one change below.

## Why not a threshold fitted on our data

The plan was to fit the threshold with the best Peirce skill on training passes. Training (both sites, Aug 2024 to Oct 2026 minus the DANA) holds only **4 new-flood labels**, and 3 of them followed 7–29 mm of rain, so they are water management or radar noise, not rain floods. The fitted threshold came out at 7 mm and alarms on almost any rain (218 false alarms in training). Meanwhile real storms, such as the Oct 2024 DANA (157 mm) and Mar 2025 (142 mm at Pego), raised water by about 200 ha but stayed under the label's noise cut. The 2024 DANA mostly flooded towns and drained into the rice fields, both outside the zone.

So two years of DSWx-S1 passes are **not enough to learn a rain threshold here**. The alert uses the published one, and the fitted one is reported next to it (`metrics.json → scores.fitted_threshold`).

## Results

| | Hits | Misses | False alarms |
|---|---:|---:|---:|
| **Held-out DANA window** (17 passes, both sites) | **2** | 0 | **0** |
| Training (504 passes) | 1 | 3 | 16 |
| Fitted 7 mm threshold, test | 2 | 0 | 5 |

Two held-out events is far too few for a skill claim. Read it as "the rule fired for the DANA and stayed quiet in the weeks around it".

**DANA replay at Pego-Oliva** (deterministic IFS runs, largest 3-day total in the next 5 days):

| Run | Forecast | Alert |
|---|---:|---|
| 15 Oct 00 UTC | 129 mm | 🔴 red |
| 16 Oct 00 UTC | 211 mm | 🔴 red |
| 17 Oct 00 UTC | 65 mm | 🟠 amber |
| 18 Oct 00 UTC | 70 mm | 🟠 amber |

The alert was red 3–4 days ahead, then dropped as the runs disagreed. That is why the live alert uses the ensemble, not one run.

**Label check against the official outlines** (`metrics.json → dana_passes_pego_oliva`): DSWx-S1 water in the zone went from about 400 ha (16–17 Oct) to about 700 ha (22–23 Oct), and inside the EMSR935 flood outline from about 200 to about 450 ha. Inside the Generalitat's 1,023 ha river-flood footprint it saw only about 8 ha: that water had drained before the first pass, 3 days after the peak.

## Caveats

- The IFS grid misses extremes: about 160 mm over 3 days at the wettest Pego point vs 634 mm at AEMET Pego. The 100 mm anchor comes from stations, so on this product the alert is conservative.
- Only local rain is used. River water from upstream (2024) and sea surge (0.5 m at Gandia in 2026) are not inputs.
- The label is new water on the next radar pass, so floods that drain between passes are missed.
- The logistic probability in `forecast.json` has almost no skill (Brier skill 0.01 in training). It is kept for transparency, not for the alert.

Outputs in `data/prediction/flood/`: `forecast.json` (live alert, replay, rules), `metrics.json`, `events.csv` (every sample), `water_<site>.csv`, `rain_<site>.csv`, plus a `data/manifest.json` entry per site (`stack: open-meteo-ifs`, `layer: flood_alert`).

Credits: rain © Open-Meteo (CC BY 4.0), ECMWF IFS. Water: OPERA DSWx-S1 (NASA JPL). Outlines: Copernicus EMS EMSR935, Generalitat Valenciana.
