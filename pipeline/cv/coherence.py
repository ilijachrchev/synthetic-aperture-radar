"""12-day NISAR coherence on the site grid, from the GUNW products, for the CV model and benchmark.

    python -m pipeline.cv.coherence                        # every CV stack
    python -m pipeline.cv.coherence --site donana --workers 3

At L-band a dry, smooth surface (dry marsh, salt crust) is as dark as water, so darkness alone
cannot tell them apart. Coherence can: water loses its radar phase within days, while dry, stable
ground keeps it over the 12 days of a pair (Donana, 7 Sep 2026, judged by optical water maps:
median coherence 0.25 on water, 0.69 on dark dry ground, 0.81 on other dry land).

For every GUNW pair of a stack in data/catalog/<site>.json, this reads only the site window of the
20 m layer science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram/HH/coherenceMagnitude from the
remote HDF5 file (about 30 s; a whole file is about 2.25 GB, never downloaded), averages it onto
the site grid and writes data/coherence/<site>_<stack>/<reference date>_<secondary date>.tif:
uint8, coherence x 250, 255 where the pair does not cover the pixel. One file per date pair:
VALIDATED before PROVISIONAL, then the newest CRID. Pairs already on disk are skipped.
Writes data/coherence/index.json (every pair, its granule and the share of the site it covers).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from pipeline.config import CV_LABEL_SITES, get_site, site_stacks
from pipeline.cv.evaluate import EXTRA_TEST_STACKS
from pipeline.stack import site_grid

COHERENCE_DIR = Path("data/coherence")
CATALOG_DIR = Path("data/catalog")
LAYER = "science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram"
SCALE, NODATA = 250, 255
MARGIN_M = 200.0


def pairs_of(site: str, stack_id: str) -> list[dict]:
    """One GUNW catalog entry per (reference date, secondary date) of a stack, oldest first."""
    granules = json.loads((CATALOG_DIR / f"{site}.json").read_text(encoding="utf-8"))["granules"]
    best: dict[tuple[str, str], tuple[tuple, dict]] = {}
    for e in granules:
        if e.get("product") != "GUNW" or e.get("stack_id") != stack_id or not e.get("reference_utc"):
            continue
        key = (e["reference_utc"][:10], e["secondary_utc"][:10])
        rank = (e.get("maturity") == "VALIDATED", e.get("crid") or "", e["granule_ur"])
        if key not in best or rank > best[key][0]:
            best[key] = (rank, e)
    return [best[k][1] for k in sorted(best)]


def pair_path(site: str, stack_id: str, entry: dict) -> Path:
    return COHERENCE_DIR / f"{site}_{stack_id}" / f"{entry['reference_utc'][:10]}_{entry['secondary_utc'][:10]}.tif"


def to_uint8(coh: np.ndarray) -> np.ndarray:
    """Coherence 0..1 as uint8 x SCALE; NODATA where not finite or not positive (outside the pair)."""
    ok = np.isfinite(coh) & (coh > 0)
    out = np.full(coh.shape, NODATA, dtype="uint8")
    out[ok] = np.clip(np.rint(coh[ok] * SCALE), 0, SCALE).astype("uint8")
    return out


def from_uint8(q: np.ndarray) -> np.ndarray:
    """float32 coherence, NaN where NODATA."""
    out = q.astype("float32") / SCALE
    out[q == NODATA] = np.nan
    return out


def _login() -> None:
    import earthaccess

    earthaccess.login(strategy="netrc")


def read_pair(site: str, stack_id: str, entry: dict, out: Path) -> dict:
    """Read the site window of one pair's coherence, put it on the site grid and write it."""
    import earthaccess
    import h5py

    t0 = time.time()
    grid = site_grid(get_site(site))
    found = earthaccess.search_data(short_name=entry["collection"], granule_name=entry["granule_ur"])
    if not found:
        raise RuntimeError(f"{entry['granule_ur']}: not found in CMR")
    with h5py.File(earthaccess.open(found[:1])[0], "r") as f:
        epsg = int(f[f"{LAYER}/projection"][()])
        x, y = f[f"{LAYER}/xCoordinates"][:], f[f"{LAYER}/yCoordinates"][:]
        dx, dy = float(f[f"{LAYER}/xCoordinateSpacing"][()]), float(f[f"{LAYER}/yCoordinateSpacing"][()])
        left, top = grid.transform.c, grid.transform.f
        right, bottom = left + grid.width * grid.transform.a, top + grid.height * grid.transform.e
        b = transform_bounds(grid.crs, f"EPSG:{epsg}", left, bottom, right, top)
        ix = np.where((x >= b[0] - MARGIN_M) & (x <= b[2] + MARGIN_M))[0]
        iy = np.where((y >= b[1] - MARGIN_M) & (y <= b[3] + MARGIN_M))[0]
        coh = np.full((grid.height, grid.width), np.nan, dtype="float32")
        if ix.size and iy.size:
            src = f[f"{LAYER}/HH/coherenceMagnitude"][iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1].astype("float32")
            if dy > 0:  # rows from south to north: flip so the first row is the northern one
                src, y_top = src[::-1], y[iy[-1]]
            else:
                y_top = y[iy[0]]
            # x/yCoordinates are pixel centres; at most half a pixel (10 m) off if they were edges
            src_transform = from_origin(x[ix[0]] - abs(dx) / 2, y_top + abs(dy) / 2, abs(dx), abs(dy))
            src[~np.isfinite(src) | (src <= 0)] = np.nan
            reproject(src, coh, src_transform=src_transform, src_crs=f"EPSG:{epsg}", src_nodata=np.nan,
                      dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan,
                      resampling=Resampling.average)
    q = to_uint8(coh)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="uint8",
                       crs=grid.crs, transform=grid.transform, nodata=NODATA, compress="deflate", tiled=True) as dst:
        dst.write(q, 1)
    tmp.replace(out)
    return {"covered": round(float((q != NODATA).mean()), 3), "seconds": round(time.time() - t0)}


def read_coherence(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return from_uint8(src.read(1))


def coherence_path(site: str, stack_id: str, day: str) -> Path | None:
    """The pair that describes one acquisition (pre-registered in docs/CV_BENCHMARK.md).

    The pair that ends on the date, with the latest reference date (the 12-day pair; only the
    past is needed, as in real use); else, for the first date of a stack or after a gap, the
    pair that starts on it, with the earliest secondary date; else None.
    """
    folder = COHERENCE_DIR / f"{site}_{stack_id}"
    ending = sorted(folder.glob(f"*_{day}.tif"))
    if ending:
        return ending[-1]
    starting = sorted(folder.glob(f"{day}_*.tif"))
    return starting[0] if starting else None


def coherence_for(site: str, stack_id: str, day: str, shape: tuple[int, int]) -> np.ndarray:
    """(H, W) float32 coherence of one acquisition on the site grid, all NaN when no pair is on disk."""
    path = coherence_path(site, stack_id, day)
    if path is None:
        return np.full(shape, np.nan, dtype="float32")
    coh = read_coherence(path)
    if coh.shape != shape:
        raise ValueError(f"{path} is {coh.shape}, the stack grid is {shape}: rerun python -m pipeline.cv.coherence")
    return coh


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", nargs="+", default=list(CV_LABEL_SITES))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    jobs = [(site, stack_id, e, pair_path(site, stack_id, e))
            for site in args.site for stack_id in site_stacks(site) + EXTRA_TEST_STACKS.get(site, ())
            for e in pairs_of(site, stack_id)]
    todo = [j for j in jobs if not j[3].exists()]
    print(f"{len(jobs)} pairs, {len(todo)} to read with {args.workers} workers", flush=True)
    covered: dict[Path, float] = {}
    if todo:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_login) as pool:
            futures = {pool.submit(read_pair, *j): j for j in todo}
            for fut in as_completed(futures):
                site, stack_id, e, out = futures[fut]
                try:
                    r = fut.result()
                    covered[out] = r["covered"]
                    print(f"[{time.strftime('%H:%M:%S')}] {site} {stack_id} {out.stem}: "
                          f"covers {r['covered']:.0%} of the site, {r['seconds']} s", flush=True)
                except Exception as ex:  # one failed pair must not stop the others; it is retried next run
                    print(f"[{time.strftime('%H:%M:%S')}] {site} {stack_id} {out.stem}: FAILED {ex!r}", flush=True)
    index = []
    for site, stack_id, e, out in jobs:
        if out.exists() and out not in covered:
            covered[out] = round(float(np.isfinite(read_coherence(out)).mean()), 3)
        index.append({"site": site, "stack": stack_id, "reference_date": e["reference_utc"][:10],
                      "secondary_date": e["secondary_utc"][:10], "granule_ur": e["granule_ur"],
                      "maturity": e.get("maturity"), "crid": e.get("crid"),
                      "file": out.as_posix() if out.exists() else None, "covers_site": covered.get(out)})
    COHERENCE_DIR.mkdir(parents=True, exist_ok=True)
    (COHERENCE_DIR / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"{sum(1 for i in index if i['file'])} of {len(index)} pairs on disk -> {COHERENCE_DIR / 'index.json'}")


if __name__ == "__main__":
    main()
