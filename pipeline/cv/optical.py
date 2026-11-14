"""Optical answer key for the CV benchmark: OPERA DSWx-HLS water maps on every NISAR date.

    python -m pipeline.cv.optical                        # every CV site
    python -m pipeline.cv.optical --site donana

The benchmark judges every radar water map (Sentinel-1 DSWx-S1, the NISAR thresholds, the
U-Nets) against an optical one, so no contestant is scored against itself. The optical map is
OPERA DSWx-HLS v1 (Landsat 8/9 and Sentinel-2 through HLS, 30 m), layer B01_WTR.

Pre-registered window: OPTICAL_WINDOW_DAYS = 1, so the same day as the NISAR pass or one day
before or after (UTC dates). Per pixel the first CLEAR value wins (0 not water, 1 open water,
2 partial surface water), taking the granules in this order: same day, then the day before, then
the day after, and by granule name within a day. Where no granule is clear the first other code
seen is kept (252 snow or ice, 253 cloud or cloud shadow, 254 ocean masked), else 255 (fill).
The codes were checked on the files themselves (band description "Water classification (WTR)"
and its colour table: 0 white, 1 blue, 2 light blue, 252 cyan, 253 grey, 254 navy, 255
transparent), in line with the DSWx-HLS product specification.

For every site in CV_LABEL_SITES and every stack (with the extra test stacks), for every NISAR
date of the stack, this writes data/optical/<site>_<stack>/<NISAR date>.tif on the stack grid:
uint8, band 1 the WTR class, band 2 the days between the NISAR date and the value used (0 or 1,
255 where none), nodata 255. And data/optical/index.json, one row per (site, stack, date): the
optical dates and granules used, and the clear share of the site grid and of the NISAR-valid
pixels of that date. The tiles are downloaded once per site to data/optical/_tiles/<site>/ (on
the project drive, never under data/raw) and deleted when the site is done.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from pipeline.config import CV_LABEL_SITES, DATA_DIR, STACK_DIR, get_site, site_stacks
from pipeline.cv.data import grid_of, open_stack
from pipeline.cv.evaluate import EXTRA_TEST_STACKS, date_index

SHORT_NAME = "OPERA_L3_DSWX-HLS_V1"
SEASON = ("2026-06-10", "2026-11-15")
OPTICAL_WINDOW_DAYS = 1
OPTICAL_DIR = DATA_DIR / "optical"
TILE_DIR = OPTICAL_DIR / "_tiles"
INDEX_PATH = OPTICAL_DIR / "index.json"

NOT_WATER, OPEN, PARTIAL = 0, 1, 2
SNOW_ICE, CLOUD, OCEAN_MASKED, FILL = 252, 253, 254, 255
CLEAR = (NOT_WATER, OPEN, PARTIAL)
MIN_FREE_GB = 5.0

_NAME = re.compile(r"OPERA_L3_DSWx-HLS_(T\w{5})_(\d{8}T\d{6})Z_(\d{8}T\d{6})Z_(\w+?)_30_v([\d.]+)_B01_WTR\.tif$")


def window_order(nisar_day: str, by_date: dict[str, list[str]],
                 window: int = OPTICAL_WINDOW_DAYS) -> list[tuple[int, str, str]]:
    """(days from NISAR, optical date, file name) in priority order: same day, the day before, the
    day after (then two days before, two after, ... up to window), by name within a day."""
    d = date.fromisoformat(nisar_day)
    offsets = [0] + [s * k for k in range(1, window + 1) for s in (-1, 1)]
    out = []
    for off in offsets:
        day = (d + timedelta(days=off)).isoformat()
        out += [(abs(off), day, name) for name in sorted(by_date.get(day, []))]
    return out


def combine(layers: list[tuple[int, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    """Clear-first mosaic of WTR layers already on one grid and in priority order.

    layers: (days from NISAR, WTR uint8 array). Returns (wtr, days): per pixel the first clear value
    (0, 1, 2); where none is clear, the first value that is not fill; else FILL. days holds the day
    distance of the value taken, FILL where nothing was taken.
    """
    if not layers:
        raise ValueError("no layers to combine")
    shape = layers[0][1].shape
    wtr = np.full(shape, FILL, dtype="uint8")
    days = np.full(shape, FILL, dtype="uint8")
    taken = np.zeros(shape, dtype=bool)
    for clear_pass in (True, False):
        for d, a in layers:
            ok = np.isin(a, CLEAR) if clear_pass else (a != FILL)
            take = ~taken & ok
            wtr[take], days[take] = a[take], d
            taken |= take
    return wtr, days


def on_grid(path: Path, crs: str, transform, shape: tuple[int, int]) -> np.ndarray:
    """One B01_WTR granule on the stack grid (nearest), FILL outside it."""
    out = np.full(shape, FILL, dtype="uint8")
    with rasterio.open(path) as src:
        reproject(rasterio.band(src, 1), out, src_nodata=src.nodata if src.nodata is not None else FILL,
                  dst_transform=transform, dst_crs=crs, dst_nodata=FILL, resampling=Resampling.nearest)
    return out


def season_links(site_name: str) -> dict[str, list[str]]:
    """B01_WTR links over the site for the whole season, by acquisition date (UTC), one link per
    (tile, sensing time, sensor): the newest version and production time."""
    import earthaccess

    site = get_site(site_name)
    found = earthaccess.search_data(short_name=SHORT_NAME, bounding_box=site.bbox, temporal=SEASON)
    best: dict[tuple[str, str, str], tuple[tuple, str, str]] = {}
    for g in found:
        start = g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10]
        for url in g.data_links():
            m = _NAME.search(url.rsplit("/", 1)[-1])
            if not m:
                continue
            tile, sensed, produced, sensor, version = m.groups()
            key = (tile, sensed, sensor)
            rank = (tuple(int(v) for v in version.split(".")), produced)
            if key not in best or rank > best[key][0]:
                best[key] = (rank, start, url)
    by_date: dict[str, list[str]] = defaultdict(list)
    for _, start, url in best.values():
        by_date[start].append(url)
    return {k: sorted(v) for k, v in sorted(by_date.items())}


def needed_dates(nisar_days: set[str], window: int = OPTICAL_WINDOW_DAYS) -> set[str]:
    out = set()
    for day in nisar_days:
        d = date.fromisoformat(day)
        out |= {(d + timedelta(days=k)).isoformat() for k in range(-window, window + 1)}
    return out


def download(site_name: str, links: dict[str, list[str]], days: set[str]) -> dict[str, list[str]]:
    """Fetch the granules of the needed optical dates; returns file names on disk by date."""
    import earthaccess

    on_disk: dict[str, list[str]] = {}
    for day in sorted(days & set(links)):
        folder = TILE_DIR / site_name / day.replace("-", "")
        folder.mkdir(parents=True, exist_ok=True)
        todo = [u for u in links[day] if not (folder / u.rsplit("/", 1)[-1]).exists()]
        if todo:
            earthaccess.download(todo, local_path=str(folder), show_progress=False)
        names = [u.rsplit("/", 1)[-1] for u in links[day]]
        missing = [n for n in names if not (folder / n).exists()]
        if missing:
            raise RuntimeError(f"{site_name} {day}: {len(missing)} granules failed to download, e.g. {missing[0]}")
        on_disk[day] = names
    return on_disk


def write_key(path: Path, wtr: np.ndarray, days: np.ndarray, crs: str, transform) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", driver="GTiff", height=wtr.shape[0], width=wtr.shape[1], count=2, dtype="uint8",
                       crs=crs, transform=transform, nodata=FILL, compress="deflate", tiled=True) as dst:
        dst.write(wtr, 1)
        dst.write(days, 2)
        dst.set_band_description(1, "DSWx-HLS WTR class (clear first within the window)")
        dst.set_band_description(2, "days between the NISAR date and the optical value")
    tmp.replace(path)


def key_path(site_name: str, stack_id: str, day: str) -> Path:
    return OPTICAL_DIR / f"{site_name}_{stack_id}" / f"{day}.tif"


def read_key(site_name: str, stack_id: str, day: str) -> tuple[np.ndarray, np.ndarray] | None:
    """(wtr, days) of one NISAR date on the stack grid, or None when no optical granule was in the window."""
    path = key_path(site_name, stack_id, day)
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        return src.read(1), src.read(2)


def site_rows(site_name: str) -> list[dict]:
    """Build the answer key of every stack and NISAR date of one site."""
    stacks = [s for s in site_stacks(site_name) + EXTRA_TEST_STACKS.get(site_name, ())
              if (STACK_DIR / f"{site_name}_{s}.nc").exists()]
    dates_of = {}
    for stack_id in stacks:
        ds = open_stack(STACK_DIR / f"{site_name}_{stack_id}.nc")
        dates_of[stack_id] = date_index(ds)
        del ds
    links = season_links(site_name)
    on_disk = download(site_name, links, needed_dates({d for v in dates_of.values() for d in v}))
    rows = []
    for stack_id in stacks:
        ds = open_stack(STACK_DIR / f"{site_name}_{stack_id}.nc")
        crs, transform, shape = grid_of(ds)
        valid_all = ds["valid"].values.astype(bool)
        for day, t in dates_of[stack_id].items():
            order = window_order(day, on_disk)
            row = {"site": site_name, "stack": stack_id, "date": day, "candidates": len(order),
                   "optical_dates_used": [], "granules_used": [], "clear_share_site": 0.0,
                   "clear_share_valid": 0.0, "same_day_share_of_clear": None, "open_share_of_clear": None,
                   "file": None}
            if order:
                layers, names = [], []
                for d, opt_day, name in order:
                    layers.append((d, on_grid(TILE_DIR / site_name / opt_day.replace("-", "") / name, crs, transform,
                                              shape)))
                    names.append((opt_day, name))
                wtr, days = combine(layers)
                used = []
                taken = np.zeros(shape, dtype=bool)
                for (opt_day, name), (_, a) in zip(names, layers):  # which granules gave at least one pixel
                    clear_here = np.isin(a, CLEAR) & ~taken & np.isin(wtr, CLEAR)
                    if clear_here.any():
                        used.append((opt_day, name))
                    taken |= clear_here
                clear = np.isin(wtr, CLEAR)
                valid = valid_all[t]
                path = key_path(site_name, stack_id, day)
                write_key(path, wtr, days, crs, transform)
                row.update({
                    "optical_dates_used": sorted({d for d, _ in used}),
                    "granules_used": [n for _, n in used],
                    "clear_share_site": round(float(clear.mean()), 4),
                    "clear_share_valid": round(float((clear & valid).sum() / max(int(valid.sum()), 1)), 4),
                    "same_day_share_of_clear": round(float((clear & (days == 0)).sum() / max(int(clear.sum()), 1)), 4),
                    "open_share_of_clear": round(float((wtr == OPEN).sum() / max(int(clear.sum()), 1)), 4),
                    "file": path.relative_to(DATA_DIR.parent).as_posix(),
                })
            rows.append(row)
            print(f"[{time.strftime('%H:%M:%S')}] {site_name} {stack_id} {day}: {len(order)} granules in the window, "
                  f"clear {row['clear_share_valid']:.0%} of NISAR-valid pixels", flush=True)
        del ds, valid_all
    return rows


def main() -> None:
    import earthaccess

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", nargs="+", default=list(CV_LABEL_SITES))
    parser.add_argument("--keep-tiles", action="store_true", help="do not delete the downloaded granules")
    args = parser.parse_args()
    OPTICAL_DIR.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(OPTICAL_DIR).free / 1e9
    print(f"free space on the project drive: {free_gb:.1f} GB", flush=True)
    if free_gb < MIN_FREE_GB:
        raise SystemExit(f"less than {MIN_FREE_GB} GB free: stopping before any download")
    earthaccess.login(strategy="netrc")
    old = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else []
    for site_name in args.site:
        rows = site_rows(site_name)
        old = [r for r in old if r["site"] != site_name] + rows
        INDEX_PATH.write_text(json.dumps(old, indent=1), encoding="utf-8")
        if not args.keep_tiles:
            shutil.rmtree(TILE_DIR / site_name, ignore_errors=True)
        n = len(rows)
        print(f"{site_name}: {n} NISAR dates, {sum(r['clear_share_valid'] >= 0.1 for r in rows)} with at least 10 % "
              f"of NISAR-valid pixels clear, {sum(r['clear_share_valid'] >= 0.5 for r in rows)} with at least 50 %",
              flush=True)
    print(f"-> {INDEX_PATH}")


if __name__ == "__main__":
    main()
