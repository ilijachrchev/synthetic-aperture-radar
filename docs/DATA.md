# Data

The shared data for the CV and ML models: how it lines up, where the stacks are, and what is in git.

## One grid per site

Every layer of a site sits on one grid: the UTM zone of the site (**EPSG:32630**, UTM 30N, for the Valencian sites; 32631 for Ebro and Camargue; 32629 for Donana), **20 m** pixels, snapped to the 20 m lattice. Take it from the code, never rebuild it by hand:

```python
from pipeline.config import get_site
from pipeline.stack import site_grid

grid = site_grid(get_site("albufera"))   # crs, transform, width, height
```

| Site | Box W, S, E, N (WGS84) | Grid top-left x, y (m) | Size (cols x rows) | Used by |
|---|---|---|---|---|
| albufera | -0.45, 39.15, -0.22, 39.45 | 719400, 4370420 | 1042 x 1696 | CV, ML, Prediction |
| pego_oliva | -0.25, 38.78, 0.06, 39.02 | 738060, 4323460 | 1388 x 1376 | CV |
| espada | -0.50, 39.78, -0.10, 40.02 | 713340, 4434020 | 1751 x 1385 | CV, ML |
| lorca | -1.80, 37.55, -1.45, 37.85 | 605560, 4190320 | 1568 x 1688 | Prediction |
| ebro | 0.56, 40.54, 0.90, 40.82 | 293360, 4521660 (31N) | 1478 x 1593 | CV training |
| camargue | 4.35, 43.40, 4.75, 43.65 | 608860, 4834500 (31N) | 1643 x 1419 | CV training |
| donana | -6.42, 36.88, -6.08, 37.20 | 728960, 4121060 (29N) | 1565 x 1820 | CV test |

The box is the area of interest; the grid is that box snapped outward in UTM, so it reaches slightly past it.

## Stacks

One NetCDF file per site and track: `data/stack/<site>_<stack>.nc`. Each track sees the ground from its own angle, so tracks are never mixed.

| Site | Stacks (track_direction_frame) | Dates |
|---|---|---|
| albufera | 066_D_069 · 058_A_021 | 11 · 11, 18 Jun to 28 Oct 2026 |
| pego_oliva | 066_D_069 · 058_A_021 | 11 · 11 |
| espada | 058_A_022 · 167_D_068 | 11 · 9 |

These shared stacks cover the whole site box. One extra stack is for CV testing only: `pego_oliva_167_D_069` (9 dates, 25 Jun to 23 Oct). Its frame covers about 63 % of the box, and only 34 ha of the EMSR935 flood outline is seen on both 11 and 23 Oct. Build it with `--min-coverage 0.6` on `pipeline.nisar_fetch` and `pipeline.dswx`. For `pipeline.dswx`, list all three Pego-Oliva stacks with `--stack`, because the index is rewritten.

### Extra stacks for the CV model only

`config.CV_STACKS` adds three wetlands that only the CV model uses: two for training and a second unseen test site. They are not in `STACKS`, so `pipeline.run` and the ML model never download them. Frames may cover only part of the box; the rest stays invalid. Results: [CV_RESULTS.md](CV_RESULTS.md).

| Site | Stacks | Dates | Usable labelled scenes |
|---|---|---|---|
| ebro (training) | 058_A_022 · 066_D_068 · 167_D_068 | 11 · 11 · 9 | 0 · 1 · 4 |
| camargue (training) | 101_A_023 · 173_A_024 | 10 · 11 | 3 · 6 |
| donana (test) | 023_D_070 · 116_A_020 · 015_A_020 | 11 · 10 · 10 | 11 · 5 · 1 |

"Usable" means a same-day DSWx-S1 map within 2 h that covers at least 10 % of the usable pixels. Many matched passes miss the site: their tiles touch the box but the swath does not (`python -m pipeline.cv.quality` lists them).

Build one site (the raw NISAR subsets can be deleted once its stacks are built):

```bash
python -m pipeline.catalog --site ebro
python -m pipeline.context --site ebro
python -m pipeline.nisar_fetch --site ebro --stack 058_A_022 --min-coverage 0.15   # each stack of the site
python -m pipeline.stack --site ebro --stack 058_A_022                              # each stack of the site
python -m pipeline.dswx --site ebro --stack 058_A_022 --stack 066_D_068 --stack 167_D_068 --min-coverage 0.15
```

List every stack of the site in the `pipeline.dswx` call: it rewrites the site's label index with only the stacks given.

Inside each file, dims `time x y x`:

- `HH`, `HV`: gamma0 backscatter in **linear power**, NaN where the pixel is not valid. For dB use `to_db` (10·log10).
- `valid`: 1 where the pixel is usable (GCOV mask 1 to 5, HH finite and positive, clean resampling), else 0. It is defined on HH: on dual-pol dates every valid pixel also has a positive HV (checked on all six stacks); on HH-only dates HV is NaN.
- `looks`: number of looks (NaN unless fetched with `--with-looks`).
- Per date: `granule_ur`, `crid`, `maturity`, `pols`. The 058 A stacks have one HH-only date (2026-09-22): HV is all NaN there.
- Processing versions: the newest date of four stacks is VALIDATED (CRID P05036), the other dates PROVISIONAL (P05023). On stable urban pixels the jump into that date is -0.10 to -0.34 dB in HH, inside the normal 12-day changes (up to 0.63 dB), so all dates can be compared. Filter on `crid` if you prefer to keep them apart.

```python
from pipeline.cv.data import open_stack, to_db

ds = open_stack("data/stack/albufera_066_D_069.nc")
hh_db = to_db(ds["HH"].values)    # (time, y, x)
dates = ds["time"].values
```

## Where the stack files are

Not in git: they are large (an estimated 100 to 200 MB each) and can be rebuilt. Two ways to get them:

1. **Download** from the GitHub release `data-v1` of this repo (team only while the repo is private):
   ```bash
   gh release download data-v1 --pattern "*.nc" --dir data/stack
   ```
2. **Rebuild** with your own free Earthdata login (setup in the README). It skips what is already on disk:
   ```bash
   .venv\Scripts\python -m pipeline.run
   ```

## Labels and helper layers (in git)

| File | What | Model |
|---|---|---|
| `data/context/<site>_worldcover_2021_20m.tif` | ESA WorldCover 2021 on the site grid: 10 tree, 20 shrub, 30 grass, 40 crop, 50 built, 60 bare, 80 water, 90 herbaceous wetland, 0 no data | CV, ML |
| `data/context/<site>_jrc_occurrence_20m.tif` | JRC Global Surface Water v1.5, share of time a pixel was water 1984 to 2024 (0 to 100 %, 255 no data), on the site grid | ML |
| `data/context/<site>_sea_20m.tif` | Sea mask on the site grid (1 sea, 0 not sea): permanent water connected to the east edge, with thin canals cut so the Albufera lagoon stays separate. Albufera 28 % sea, Pego-Oliva 34 %, Espadà 2 % | ML, map |
| `data/context/<site>_sme2_<YYYY-MM-DD>_200m.tif` | NISAR L3 SME2 soil moisture (PROVISIONAL), m3/m3 stored as uint16 x 10000, on a 200 m grid aligned with the site grid; 18 dates from 18 Jun to 16 Oct 2026 at Albufera and Pego-Oliva, passes of the same date averaged; index in `<site>_sme2_index.json`. Load at 20 m with `pipeline.soil_moisture.load(site)`, or the newest map before a date with `latest_before(site, day)`. Rebuild: `python -m pipeline.soil_moisture` | Prediction, map |
| `data/labels/pego_oliva_emsr935_flood.geojson` | Copernicus EMS EMSR935 flood outline, DANA "Adam" (imagery 20 to 21 Oct) | CV |
| `data/labels/pego_oliva_emsr935_aoi.geojson` | The two EMSR935 mapped areas: inside them every flooded pixel was outlined, so a flood map is scored only there | CV |
| `data/labels/pego_oliva_generalitat_footprint.geojson` | Official DANA river-flood footprint, 1,022.8 ha | CV |
| `data/labels/espada_effis_burnt_area.geojson` | EFFIS burnt area of the Serra d'Espadà fire | CV, ML |
| `data/labels/<site>_municipalities_osm.geojson` | Municipal boundaries with INE codes (OpenStreetMap admin level 8, (c) OpenStreetMap contributors, ODbL), Albufera 31, Pego-Oliva 46 | NISAR labels |
| `data/labels_nisar/<site>_<stack>/` | NISAR water labels per pass (next section) | Prediction, app |
| `data/catalog/<site>.json` | Every NISAR file over the site | all |
| `data/context/lorca_gnss_LOR1_up.csv` | GNSS station LOR1 daily height | Prediction |
| `data/streets/results.json`, `data/streets/*.geojson` | Terrain flow (HAND, no training) against the official flood zones in the 10 towns of the 2024 DANA: every number with its inputs, the flow paths, the terrain map at the zones' area, the SIMULATED maximum depth; rules, results and limits in `docs/STREETS.md`. Rebuild: `python -m pipeline.streets` steps | App, pitch |

Put an outline on a stack grid with `pipeline.cv.data.rasterize_on(ds, geodataframe)`.

The catalogs in `data/catalog/` stay in git on purpose: the fetchers read them, and they pin exactly which NISAR files the stacks were built from (CMR keeps changing as new and reprocessed files arrive). Rebuild them with `python -m pipeline.catalog --all`.

Not in git, rebuilt by the pipeline: `data/raw/` (NISAR subsets, the same-day Sentinel-1 water maps in `data/raw/dswx/<site>/<stack>/<date>/` with an `index.json`, raw clips) and `data/stack/`.

## NISAR water labels per pass

The NISAR labels for the "where will the water go" model (PR #33) and layers for the app (discussion #29): `python -m pipeline.cv.labels`, run from the repository root (code and rules in `pipeline/cv/labels.py`). Every NISAR pass with HV, on the 20 m site grid: Albufera 066_D_069 (11 passes) and 058_A_021 (10, the HH-only 22 Sep is left out); Pego-Oliva the same two plus 167_D_069 (9 passes, about 64 % of the land in the box). In `data/labels_nisar/<site>_<stack>/` (in git, 8.0 MB in all):

| File | Values |
|---|---|
| `<date>_class.tif` | 0 not water, 1 open water, 2 water under plants (possible, not validated), 3 not assessed (built-up), 255 no data or sea |
| `<date>_confidence.tif` | 0 to 100 on classes 0 to 2, in steps of 5; 255 elsewhere |
| `dana_<before>_<after>.tif` | Still flooded after the DANA, open water on the stack's own track (16 to 28 Oct on 066 D and 058 A, 11 to 23 Oct on 167 D): 0 dry on both dates, 1 water on both, 2 new water, 3 water gone, 4 permanent water, 255 not compared (no data or sea on either date, or built-up) |

`data/labels_nisar/<site>_passes.json` lists the passes in time order: `pass_id`, `date`, `begin_utc`, `platform`, `track`, `direction`, `stack`, `granules` and the two file paths.

- **Open water**: the v1 U-Net ensemble at its pre-registered threshold, p(open water) of at least 0.3, read from the cached probabilities in `data/interim/cv_prob/v1` (no model runs).
- **Water under plants**: a candidate rule, not validated, because no source we have can see water under plants. On vegetated WorldCover land (tree, shrub, grass, crop, herbaceous wetland): 5x5 filtered HH at least 3 dB above its median over the stack while HV stays within 1.5 dB of its median.
- **Not assessed**: WorldCover built-up. The radar cannot see water between buildings at 20 m, so there a model should rely on terrain and rain.
- **Confidence**: the share of the available checks that agree with the class, with equal weights: the model's margin to 0.3 (always), HH below -15 dB, coherence below 0.25 where a GUNW pair exists (none after 21 Oct, so not on 23 and 28 Oct), and the optical DSWx-HLS map within 1 day where it is clear. Class 2 has only the model's p(any water) as a check and is capped at 50. A vote, not a probability.

`data/metrics/nisar_labels_summary.json` holds the hectares per class per pass, how much of the labelled ground an optical or a coherence check covers and how often it agrees, and the DANA change per site and per municipality.

For the model, `load(site)` gives the classes in the shape of PR #33's `pipeline.prediction.spatial.labels.load(site)`: a (pass, y, x) uint8 stack in time order with its water codes (0 dry, 1 wet = open water, 255 unknown; water under plants counts as wet only with `under_plants_as_wet=True`) and the pass list. `merge` puts NISAR next to the Sentinel-1 passes, in time order. In `_site()` of `pipeline/prediction/spatial/__main__.py`:

```python
from pipeline.cv.labels import load as nisar_load, merge
stack, passes = merge(labels.load(name), nisar_load(name))   # or nisar_load(name) alone, instead of DSWx-S1
```

Then delete `data/interim/spatial/<site>/counts.npz`, the cached wet counts of the old labels. NISAR alone: with PR #33's timing (an issue pass 3 to 12 days before the target), 17 of the 21 Albufera passes and 26 of the 30 Pego-Oliva passes get one; 18 Jun (the first date) and 17 Aug (after the 24-day gap from 24 Jul) do not.

Read before use:

- Class 2 is unchecked: its confidence is near 0 almost everywhere, because the model, trained on Sentinel-1 maps, gives these bright pixels almost no water probability.
- Open water at Pego-Oliva in summer (about 40 to 75 ha per pass) is mostly not confirmed by optical (0 to 6 % of it on the clear dates of Jul and Aug); its mean confidence is 26 to 39.
- Albufera's open water on 28 Oct outside permanent water is confirmed by optical where clear (99 %), but these data cannot tell DANA rain from the planned winter flooding of the harvested rice fields.
- The two Albufera tracks disagree on 18 Jun (open water 2,776 ha on 066 D at 18:53 UTC, 8,497 ha on 058 A at 05:06 UTC), with no clear optical image that day to settle it.
- The v1 model was trained with Sentinel-1 labels at Albufera, so there these labels are not independent of DSWx-S1; Pego-Oliva was one of its test sites.
