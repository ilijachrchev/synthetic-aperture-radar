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
| `data/labels/pego_oliva_emsr935_flood.geojson` | Copernicus EMS EMSR935 flood outline, DANA "Adam" (imagery 20 to 21 Oct) | CV |
| `data/labels/pego_oliva_emsr935_aoi.geojson` | The two EMSR935 mapped areas: inside them every flooded pixel was outlined, so a flood map is scored only there | CV |
| `data/labels/pego_oliva_generalitat_footprint.geojson` | Official DANA river-flood footprint, 1,022.8 ha | CV |
| `data/labels/espada_effis_burnt_area.geojson` | EFFIS burnt area of the Serra d'Espadà fire | CV, ML |
| `data/catalog/<site>.json` | Every NISAR file over the site | all |
| `data/context/lorca_gnss_LOR1_up.csv` | GNSS station LOR1 daily height | Prediction |

Put an outline on a stack grid with `pipeline.cv.data.rasterize_on(ds, geodataframe)`.

The catalogs in `data/catalog/` stay in git on purpose: the fetchers read them, and they pin exactly which NISAR files the stacks were built from (CMR keeps changing as new and reprocessed files arrive). Rebuild them with `python -m pipeline.catalog --all`.

Not in git, rebuilt by the pipeline: `data/raw/` (NISAR subsets, the same-day Sentinel-1 water maps in `data/raw/dswx/<site>/<stack>/<date>/` with an `index.json`, raw clips) and `data/stack/`.
