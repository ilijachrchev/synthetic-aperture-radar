# Research

> Snapshot from 13 Nov 2026, for team planning. Short on purpose.
> ✔ = checked against primary data or two independent sources · ~ = one source · ? = our guess
> Drafted with an SI assistant (see the README). This file is evidence, not the idea: the team picks the concept (Space Apps rule).

## 1. Rules that shape everything

- **SI rule:** SI must not come up with the idea. Describe all SI use, watermark SI images and video, flag SI code and data in text and metadata. ✔
- **Demo:** a video of 30 seconds or less, **or** at most 7 slides, in English (a video may use another language with English subtitles). Going over the limit means no global judging. ✔
- **Links:** public, no login needed. This repo is private today, so it must be made public before we submit. ✔
- **Valencia timing:** hackathon started Fri 20:30. Jury presentations Sun 16:00. Awards 18:30. ✔
- **Judging criteria:** impact, creativity, validity, relevance, presentation. ✔

## 2. NISAR data that exists

| Maturity | Acquisitions | Use it for |
|---|---|---|
| BETA | Oct 2025 to Jan 2026 (subset) | Nothing: not calibrated |
| PROVISIONAL | 17 Jun to 21 Oct 2026, plus 302 frames back to Oct 2025 | Main time series |
| VALIDATED | 21 Oct 2026 onward | Newest scenes; GUNW has barely started (tracks 139 to 141 only) |

- **Products:** GCOV is radar brightness, HH and HV, 20 m, already on a map grid, 1 to 7 GB per file. GUNW is 12-day ground-motion pairs, 80 m, about 2 GB. ✔
- **Revisit:** 12 days per track, 2 to 4 tracks per site. Permanent gap 27 Jul to 10 Aug 2026, bridged by 24 and 36-day pairs. ✔
- **Access:** free Earthdata login. Files are cloud-optimized, so we stream a small area over HTTPS (about 1 min per layer ~). Never download whole files. ✔
- **No login needed:** NASA's CMR search and the preview PNGs, both readable from a browser (CORS). A preview can be placed on the map within 1 to 5 px by fitting its 4 corners to the frame outline. ✔
- **Not available:** soil moisture (SME2) after 21 Oct, glacier offsets (GOFF) over Spain. GIBS NISAR map tiles break at zoom 12 and above (fine at 10 and below). ✔
- **Gotchas:** only compare the same track, frame and mode (2005 vs 4005; some dates are HH only). Valencia straddles UTM zones 30 and 31. GUNW ships ionosphere, troposphere and tide corrections but does not apply them, and ionosphere stripes are not ground motion. ✔

## 3. Candidate sites (NISAR coverage checked)

| Site | Change | NISAR coverage | Ground truth | Caveat |
|---|---|---|---|---|
| Albufera, Valencia | Rice cycle and winter flooding (perellonà) | 20 dates, 18 Jun to 28 Oct, 3 tracks ✔ | Same-day Sentinel-1 water map on every date ✔ | The big October water is the farmers, not the storm ✔ |
| Pego-Oliva marsh | DANA "Adam" flood, 17 to 19 Oct ✔ | Track 066 D: 16 Oct to 28 Oct ✔ | Copernicus EMSR935 ✔ | Small signal, 9.6 days after the peak |
| Serra d'Espadà, Castellón | Wildfire, about 9,200 ha (EFFIS), started 25 Jul ✔ | Track 058 A: 24 Jul (day before) to 17 Aug and 16 Oct ✔ | EFFIS, EMSR905 ✔ | Terrain and rain |
| Lorca, Alto Guadalentín | Ground sinking: over 10 cm/yr in 1992 to 2012, about 4 cm/yr at GNSS station LOR1 since 2025 ✔ | Track 167 D: continuous, 25 Jun to 11 Oct ✔ | EGMS, GNSS station LOR1 ✔ | Only about 1 to 4 cm of motion in the window ? |
| Panama (global) | M7.7 earthquake, 9 Oct ✔ | 4 tracks; one pass 6 h after the quake; fringes visible ✔ | USGS ✔ | Frame edge, ionosphere |

Backups: Monòver sinking bowl (up to about 6.5 cm/yr, more than 42 ha) ✔ · Pacaya-Samiria flooded forest in the El Niño drought (Peru) ~

## 4. Free labels and helper data

- **OPERA DSWx-S1** (Sentinel-1 water, 30 m): 1,194 files over the Albufera since Aug 2024, with one on the same day as every NISAR pass. Free training labels and a fair L-band vs C-band comparison. ✔
- **Copernicus EMS** outlines (EMSR935 flood, EMSR905 fire) and **EFFIS** burnt areas. ✔
- **Valencian regional WFS** (ICV, no login): the EMSR935 flood outline plus the Generalitat's official 1,023 ha river-flood footprint for DANA "Adam". ✔
- **EGMS** ground motion (latest update covers 2020 to 2025, out since 4 Nov 2026; downloads need a free EU Login, the API a CLMS token). ✔
- **USGS** earthquake API. ✔

## 5. What L-band shows

| Change | Layer | What to expect |
|---|---|---|
| Open water | GCOV HH | Very dark. Threshold per scene (Otsu); published thresholds disagree |
| Flooded vegetation | GCOV HH | Brighter (about +3 dB, double bounce), HV stays flat |
| Rice | GCOV HH and HV over time | Dark (flooded), then bright (canopy), then a drop (harvest) |
| Burned forest | GCOV HV | Drops |
| Ground motion | GUNW unwrapped phase | One fringe is about 12 cm toward or away from the satellite |

Confounders: wind on water (looks bright), rain, steep terrain, ionosphere.

## 6. Predictions that stay honest

- **Keep:**
  - Lorca sinking: trend + seasonal fit on EGMS, backtested (train 2020 to 2023, test 2024 to 2025), then checked against NISAR, an independent sensor.
  - Albufera flooded area on the next passes: seasonal baseline from DSWx-S1 (2024 and 2025) plus the current state. Commit the forecast to git before the data arrives.
  - Every forecast gets a skill score against a naive baseline.
- **Drop:** soil moisture (a storm's signal fades in about 4 days, the revisit is 12) ~, flood recession (water drains faster than the revisit) ?, earthquake prediction (not honest).
- **Show:** ranges with numbers (fan chart or dotplot), "forecast made on [date]", skill against the baseline.

## 7. Competition

GitHub sample of 98 projects on this challenge ~
- Crowded: Bangladesh floods (21), "anywhere" globes and dashboards (33).
- Rare: Mexico City (1).
- Empty: Spain (0), wildfire, rice, honest forecasting.

## 8. Traps

- Downloading whole files (our laptop disks are nearly full).
- Mixing tracks, modes or BETA data.
- Live processing during the demo.
- Using C-band dB thresholds on L-band data.
- Calling the rice-field flooding a flood.
- Promising "AI predicts disasters".
- The AGPL licence of `albumentationsx`.

## 9. Key sources

- NISAR data guide: https://nisar-docs.asf.alaska.edu/
- What NISAR data exists: https://nisar-docs.asf.alaska.edu/availability-overview/
- Catalog query example: https://cmr.earthdata.nasa.gov/search/granules.json?short_name=NISAR_L2_GCOV_V1&point=-0.35,39.33
- Streaming notebooks: https://github.com/ASFOpenSARlab/NISAR_Cookbook
- Submission rules (SI, demo limits): https://www.spaceappschallenge.org/resources/project-submission-guide/
- Valencia schedule: https://www.spaceappschallenge.org/2026/local-events/valencia/?tab=schedule
- Panama M7.7 (USGS): https://earthquake.usgs.gov/earthquakes/eventpage/us6000u18k
- DANA "Adam" flood mapping (EMSR935): https://mapping.emergency.copernicus.eu/activations/EMSR935/
- EGMS: https://egms.land.copernicus.eu/
- OPERA products: https://www.jpl.nasa.gov/go/opera/products
