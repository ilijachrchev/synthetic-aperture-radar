"""NISAR soil moisture (L3 SME2) on the site grid: fetched once, loaded as 20 m arrays for models and maps.

    python -m pipeline.soil_moisture                          # albufera and pego_oliva
    python -m pipeline.soil_moisture --site pego_oliva --workers 4

NISAR L3 SME2 is surface soil moisture in m3/m3 at about 200 m (EASE-Grid 2.0, EPSG:6933), one map per
pass. Only PROVISIONAL files exist (NISAR_L3_SME2_PROVISIONAL_V1); at Albufera and Pego-Oliva they run
from 18 Jun to 16 Oct 2026, with no file after the switch to validated processing on 21 Oct. For every
granule over a site this reads only the site window of `soilMoisture` and `retrievalQualityFlag` from
the remote HDF5 file (no full download), averages the passes of the same date, and writes the result on
a 200 m grid aligned with the 20 m site grid (same corner, 10 times the pixel):

- data/context/<site>_sme2_<YYYY-MM-DD>_200m.tif: uint16, value x 10000 (m3/m3), 65535 = no data;
- data/context/<site>_sme2_index.json: dates, granules, share of the site with a value, share of
  recommended retrievals (quality flag bit 0 = 0), median.

`load(site)` gives a (dates, H, W) float32 stack on the 20 m site grid (bilinear, NaN where no data) and
the dates; `latest_before(site, day, max_age_days)` gives the newest map at least one day before `day`
and its age, for a model input that only uses the past.

Caveats: provisional data; 200 m, so one value spans many fields; about 40 % of the retrievals at the
sites are flagged "recommended". Before the October 2026 DANA it read the area that later flooded as drier
than the rest of the site (16 Oct, Pego-Oliva: median 0.11 m3/m3 inside the EMSR935 outline on the 20 m
grid, 0.18 over the 200 m cells touching it, 0.21 on the other land), so it does not explain that flood.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from pipeline.config import DATA_DIR, get_site
from pipeline.stack import site_grid

SHORT_NAME = "NISAR_L3_SME2_PROVISIONAL_V1"
SEASON = ("2026-06-01", "2026-11-15")
SITES = ("albufera", "pego_oliva")
CONTEXT_DIR = DATA_DIR / "context"
GROUP = "science/LSAR/SME2/grids/"
SCALE, NODATA = 10000, 65535
COARSE = 10        # the 200 m grid is the 20 m site grid with 10 times the pixel size
MARGIN_M = 1000.0


def coarse_grid(site_name: str) -> tuple[str, Affine, int, int]:
    """(crs, transform, width, height) of the 200 m grid aligned with the 20 m site grid."""
    g = site_grid(get_site(site_name))
    t = g.transform
    return g.crs, Affine(t.a * COARSE, t.b, t.c, t.d, t.e * COARSE, t.f), -(-g.width // COARSE), -(-g.height // COARSE)


def tif_path(site_name: str, day: str) -> Path:
    return CONTEXT_DIR / f"{site_name}_sme2_{day}_200m.tif"


def index_path(site_name: str) -> Path:
    return CONTEXT_DIR / f"{site_name}_sme2_index.json"


def to_uint16(sm: np.ndarray) -> np.ndarray:
    ok = np.isfinite(sm) & (sm >= 0) & (sm <= 1)
    out = np.full(sm.shape, NODATA, dtype="uint16")
    out[ok] = np.rint(sm[ok] * SCALE).astype("uint16")
    return out


def from_uint16(q: np.ndarray) -> np.ndarray:
    out = q.astype("float32") / SCALE
    out[q == NODATA] = np.nan
    return out


def granule_day(ur: str) -> str:
    """YYYY-MM-DD of the acquisition start in a NISAR granule name."""
    stamp = next(p for p in ur.split("_") if len(p) == 15 and p[8] == "T")
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"


def _login() -> None:
    import earthaccess

    earthaccess.login(strategy="netrc")


def read_window(ur: str, sites: tuple[str, ...]) -> dict:
    """Soil moisture of one granule on each site's 200 m grid (float32, NaN outside), plus the recommended mask."""
    import earthaccess
    import h5py

    found = earthaccess.search_data(short_name=SHORT_NAME, granule_name=ur)
    if not found:
        raise RuntimeError(f"{ur}: not found in CMR")
    out = {}
    with h5py.File(earthaccess.open(found[:1])[0], "r") as h:
        epsg = int(h[GROUP + "projection"][()])
        x, y = h[GROUP + "xCoordinates"][:], h[GROUP + "yCoordinates"][:]
        dx, dy = float(h[GROUP + "xCoordinateSpacing"][()]), float(h[GROUP + "yCoordinateSpacing"][()])
        fill = float(np.asarray(h[GROUP + "soilMoisture"].attrs.get("_FillValue", -9999.0)).ravel()[0])
        for name in sites:
            crs, transform, width, height = coarse_grid(name)
            left, top = transform.c, transform.f
            b = transform_bounds(crs, f"EPSG:{epsg}", left, top + height * transform.e, left + width * transform.a, top)
            ix = np.where((x >= b[0] - MARGIN_M) & (x <= b[2] + MARGIN_M))[0]
            iy = np.where((y >= b[1] - MARGIN_M) & (y <= b[3] + MARGIN_M))[0]
            sm_out = np.full((height, width), np.nan, dtype="float32")
            rec_out = np.full((height, width), np.nan, dtype="float32")
            if ix.size and iy.size:
                win = (slice(iy[0], iy[-1] + 1), slice(ix[0], ix[-1] + 1))
                sm = h[GROUP + "soilMoisture"][win].astype("float32")
                qf = h[GROUP + "retrievalQualityFlag"][win]
                bad = (sm == fill) | ~np.isfinite(sm) | (sm < 0) | (sm > 1)
                sm[bad] = np.nan
                rec = np.where(bad, np.nan, (qf & 1) == 0).astype("float32")  # bit 0 = 0: recommended retrieval
                if dy > 0:  # rows from south to north: flip so the first row is the northern one
                    sm, rec, y_top = sm[::-1], rec[::-1], y[iy[-1]]
                else:
                    y_top = y[iy[0]]
                src_t = from_origin(x[ix[0]] - abs(dx) / 2, y_top + abs(dy) / 2, abs(dx), abs(dy))
                for src, dst in ((sm, sm_out), (rec, rec_out)):
                    reproject(src, dst, src_transform=src_t, src_crs=f"EPSG:{epsg}", src_nodata=np.nan,
                              dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
            out[name] = (sm_out, rec_out)
    return out


def granules(site_name: str) -> list[str]:
    import earthaccess

    found = earthaccess.search_data(short_name=SHORT_NAME, bounding_box=get_site(site_name).bbox, temporal=SEASON)
    return sorted({g["umm"]["GranuleUR"] for g in found})


def fetch(sites: tuple[str, ...] = SITES, workers: int = 4) -> dict:
    """Read every granule over the sites once, average per date, write the 200 m maps and the index."""
    _login()
    by_granule: dict[str, list[str]] = defaultdict(list)
    for name in sites:
        for ur in granules(name):
            by_granule[ur].append(name)
    print(f"{len(by_granule)} granules over {', '.join(sites)}", flush=True)
    parts: dict[tuple[str, str], list] = defaultdict(list)
    with ProcessPoolExecutor(max_workers=workers, initializer=_login) as pool:
        futures = {pool.submit(read_window, ur, tuple(names)): ur for ur, names in by_granule.items()}
        for fut in as_completed(futures):
            ur = futures[fut]
            for name, (sm, rec) in fut.result().items():
                if np.isfinite(sm).any():
                    parts[(name, granule_day(ur))].append((ur, sm, rec))
            print(f"[{time.strftime('%H:%M:%S')}] {ur[17:60]} read", flush=True)
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, list] = {name: [] for name in sites}
    for (name, day), items in sorted(parts.items()):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels stay NaN
            sm = np.nanmean(np.stack([i[1] for i in items]), axis=0)
            rec = np.nanmean(np.stack([i[2] for i in items]), axis=0)
        crs, transform, width, height = coarse_grid(name)
        with rasterio.open(tif_path(name, day), "w", driver="GTiff", height=height, width=width, count=1,
                           dtype="uint16", crs=crs, transform=transform, nodata=NODATA, compress="deflate",
                           predictor=2) as dst:
            dst.write(to_uint16(sm), 1)
        index[name].append({"date": day, "granules": [i[0] for i in items], "file": tif_path(name, day).as_posix(),
                            "share_with_value": round(float(np.isfinite(sm).mean()), 3),
                            "share_recommended": round(float(np.nanmean(rec)), 3) if np.isfinite(rec).any() else None,
                            "median_m3m3": round(float(np.nanmedian(sm)), 3) if np.isfinite(sm).any() else None})
    for name in sites:
        index_path(name).write_text(json.dumps({
            "product": SHORT_NAME, "maturity": "PROVISIONAL", "units": "m3/m3", "storage": f"uint16 x {SCALE}, {NODATA} no data",
            "grid": "200 m, aligned with the 20 m site grid (pipeline.stack.site_grid); load() resamples to 20 m",
            "dates": index[name]}, indent=1) + "\n", encoding="utf-8")
        print(f"{name}: {len(index[name])} dates -> {index_path(name)}", flush=True)
    return index


def dates_of(site_name: str) -> list[str]:
    return [d["date"] for d in json.loads(index_path(site_name).read_text(encoding="utf-8"))["dates"]]


def load_day(site_name: str, day: str) -> np.ndarray:
    """(H, W) float32 soil moisture of one date on the 20 m site grid, bilinear from 200 m, NaN where no data."""
    g = site_grid(get_site(site_name))
    with rasterio.open(tif_path(site_name, day)) as src:
        coarse = from_uint16(src.read(1))
        src_t, crs = src.transform, src.crs
    out = np.full((g.height, g.width), np.nan, dtype="float32")
    reproject(coarse, out, src_transform=src_t, src_crs=crs, src_nodata=np.nan, dst_transform=g.transform,
              dst_crs=g.crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return out


def load(site_name: str) -> tuple[np.ndarray, list[str]]:
    """(dates, H, W) float32 stack on the 20 m site grid and its dates (oldest first)."""
    days = dates_of(site_name)
    return np.stack([load_day(site_name, d) for d in days]), days


def latest_day_before(days: list[str], day: str, max_age_days: int = 24) -> str | None:
    """The newest date at least one day before `day` and at most max_age_days before it, else None."""
    d = date.fromisoformat(day)
    ok = [x for x in days if d - timedelta(days=max_age_days) <= date.fromisoformat(x) < d]
    return max(ok) if ok else None


def latest_before(site_name: str, day: str, max_age_days: int = 24) -> tuple[np.ndarray | None, int | None]:
    """The newest soil-moisture map before `day` on the 20 m grid and its age in days, or (None, None)."""
    pick = latest_day_before(dates_of(site_name), day, max_age_days)
    if pick is None:
        return None, None
    return load_day(site_name, pick), (date.fromisoformat(day) - date.fromisoformat(pick)).days


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", nargs="+", default=list(SITES))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    fetch(tuple(args.site), args.workers)


if __name__ == "__main__":
    main()
