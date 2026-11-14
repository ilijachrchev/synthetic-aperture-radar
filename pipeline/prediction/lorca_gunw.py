"""Lorca ground sinking seen by NISAR: chained 12-day GUNW interferograms vs GNSS LOR1.

The Lorca forecast runs on GNSS (and EGMS once downloaded), because NISAR over
Spain starts in Jun 2026. "NISAR stays first" (discussion #9) makes NISAR the
check: does L-band see the Alto Guadalentin bowl sinking, and at the rate the
station shows over the same dates?

Steps, all fixed before looking at the result:

1. Read, straight from each GUNW HDF5 over HTTP (h5py range reads, no full
   download), the Lorca box of: unwrapped phase, coherence, connected
   components, ionosphere phase screen and mask (80 m UTM 30N grid), plus the
   troposphere phase screens and line-of-sight vectors from the metadata cubes.
2. Valid pixel: valid subswath in both dates, not water, coherence >= 0.3, in
   the largest connected component of that pair.
3. Corrections: the ionosphere screen and the wet + hydrostatic troposphere
   screens (cubes interpolated at the Copernicus GLO-30 height + 50 m geoid)
   are subtracted only if doing so lowers the median spatial spread of the
   referenced phase over the pairs. The choice is written to the output.
4. Phase to line of sight (towards the satellite positive):
   d = -lambda / (4 pi) * phase; to vertical: d / up component of the LOS
   vector (horizontal motion assumed zero, the usual reading of this bowl).
5. Each pair is referenced to the median of the valid pixels in the box (the
   bowl is a small part of it), then pairs are summed in time order; a pixel
   counts only if valid in every pair.
6. LOR1: median of the valid pixels within 3 x 3 cells (240 m). GNSS: mean of
   the daily vertical within +-3 days of each date, minus the first date.

Two tracks, two viewing geometries: 167 D frame 069 and 159 A frame 021.

Usage:
    python -m pipeline.prediction.lorca_gunw fetch     # Earthdata login (~/.netrc), ~2 min per stack
    python -m pipeline.prediction.lorca_gunw analyse   # writes data/prediction/lorca_gunw.json + png

The Copernicus GLO-30 DEM tile is downloaded once to data/raw/dem/ (public,
no login). Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import numpy as np

from pipeline.config import CATALOG_DIR, DATA_DIR, RAW_DIR, REPO_ROOT, get_site

STACKS = {"167_D_069": "20", "159_A_021": "20"}   # stack id -> bandwidth (MHz) with full Lorca coverage
GUNW_RAW = RAW_DIR / "nisar_gunw" / "lorca"
OUT = DATA_DIR / "prediction" / "lorca_gunw.json"
FIG = DATA_DIR / "prediction" / "lorca_gunw.png"
GNSS_CSV = DATA_DIR / "context" / "lorca_gnss_LOR1_up.csv"
DEM = RAW_DIR / "dem" / "lorca_cop30.tif"
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N37_00_W002_00_DEM/"
           "Copernicus_DSM_COG_10_N37_00_W002_00_DEM.tif")
LOR1_LATLON = (37.6538928785, -1.6867701674)   # from the NGL file header, as in metrics.json
GEOID_M = 50.0          # EGM2008 geoid height around Lorca (approx.), DEM is orthometric
COH_MIN = 0.3
DETREND_NOTE = ("Added after the first run: without it both tracks show opposite 30-40 mm ramps over the box "
                "(atmosphere/orbit), not ground motion. Results without it are kept under without_detrend.")
CUBE_MAX_H = 2000.0    # m: the Lorca box tops out near 1,600 m (Sierra Espuna edge)
WORKERS = 7
GNSS_HALF_WINDOW_D = 3
GRID = "/science/LSAR/GUNW/grids/frequencyA"
UNW = f"{GRID}/unwrappedInterferogram"
CUBE = "/science/LSAR/GUNW/metadata/radarGrid"
C = 299_792_458.0


# ----------------------------------------------------------------------------- selection

def select_pairs(catalog: dict, stack_id: str, bandwidth: str) -> list[dict]:
    """Full-frame GUNW pairs of one stack, one per (reference, secondary), newest CRID, in time order."""
    best: dict[tuple[str, str], dict] = {}
    for g in catalog["granules"]:
        if g.get("product") != "GUNW" or g["stack_id"] != stack_id or g.get("bandwidth_mhz") != bandwidth:
            continue
        key = (g["reference_utc"][:10], g["secondary_utc"][:10])
        if key not in best or (g["crid"], g["granule_ur"]) > (best[key]["crid"], best[key]["granule_ur"]):
            best[key] = g
    return [best[k] for k in sorted(best)]


def chain(pairs: list[dict]) -> list[dict]:
    """The longest run of pairs where each secondary date is the next reference date."""
    runs: list[list[dict]] = []
    for p in pairs:
        for run in runs:
            if run[-1]["secondary_utc"][:10] == p["reference_utc"][:10]:
                run.append(p)
                break
        else:
            runs.append([p])
    return max(runs, key=len) if runs else []


# ----------------------------------------------------------------------------- fetch

def window(coords: np.ndarray, lo: float, hi: float) -> slice:
    idx = np.where((coords >= lo) & (coords <= hi))[0]
    return slice(int(idx.min()), int(idx.max()) + 1)


def read_pair(fs, url: str, box: tuple[float, float, float, float]) -> dict[str, np.ndarray]:
    """The box (xmin, ymin, xmax, ymax in EPSG:32630) of one GUNW, by HTTP range reads."""
    import h5py

    xmin, ymin, xmax, ymax = box
    with fs.open(url, block_size=4 * 2**20, cache_type="blockcache") as f, h5py.File(f, "r") as h:
        if int(h[f"{UNW}/projection"][()]) != 32630:
            raise ValueError(f"{url}: not on EPSG:32630")
        x, y = h[f"{UNW}/xCoordinates"][()], h[f"{UNW}/yCoordinates"][()]
        sx, sy = window(x, xmin, xmax), window(y, ymin, ymax)
        out = {"x": x[sx], "y": y[sy], "frequency_hz": float(h[f"{GRID}/centerFrequency"][()])}
        for name in ("unwrappedPhase", "coherenceMagnitude", "connectedComponents", "ionospherePhaseScreen"):
            out[name] = h[f"{UNW}/HH/{name}"][sy, sx]
        out["mask"] = h[f"{UNW}/mask"][sy, sx]
        cx, cy = h[f"{CUBE}/xCoordinates"][()], h[f"{CUBE}/yCoordinates"][()]
        m = 1000.0
        csx, csy = window(cx, xmin - m, xmax + m), window(cy, ymin - m, ymax + m)
        out["cube_x"], out["cube_y"] = cx[csx], cy[csy]
        heights = h[f"{CUBE}/heightAboveEllipsoid"][()]
        nh = int(np.searchsorted(heights, CUBE_MAX_H)) + 1   # levels up to the first one above CUBE_MAX_H
        out["cube_h"] = heights[:nh]
        for name in ("wetTroposphericPhaseScreen", "hydrostaticTroposphericPhaseScreen",
                     "losUnitVectorX", "losUnitVectorY"):
            out[name] = h[f"{CUBE}/{name}"][:nh, csy, csx]
    return out


def site_box() -> tuple[float, float, float, float]:
    from pipeline.stack import site_grid
    g = site_grid(get_site("lorca"))
    x0, y0 = g.transform.c, g.transform.f
    return (x0, y0 - g.height * 20.0, x0 + g.width * 20.0, y0)


def pair_path(stack_id: str, p: dict) -> Path:
    return GUNW_RAW / stack_id / f"{p['reference_utc'][:10]}_{p['secondary_utc'][:10]}.npz"


def _fetch_one(job: tuple[str, dict, tuple]) -> str:
    """One pair, in its own process (h5py holds a global lock, so threads would not overlap)."""
    import earthaccess
    stack_id, p, box = job
    earthaccess.login(strategy="netrc")
    arrays = read_pair(earthaccess.get_fsspec_https_session(), p["h5_url"], box)
    path = pair_path(stack_id, p)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, granule_ur=p["granule_ur"], **arrays)
    tmp.replace(path)        # a pair is on disk only when complete
    return f"{stack_id} {path.name}"


def fetch(stacks: dict[str, str] = STACKS, workers: int = WORKERS) -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    catalog = json.loads((CATALOG_DIR / "lorca.json").read_text(encoding="utf-8"))
    box = site_box()
    jobs = []
    for stack_id, bw in stacks.items():
        pairs = chain(select_pairs(catalog, stack_id, bw))
        todo = [p for p in pairs if not pair_path(stack_id, p).exists()]
        print(f"{stack_id}: {len(pairs)} chained pairs, {len(todo)} to read", flush=True)
        jobs += [(stack_id, p, box) for p in todo]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(_fetch_one, j) for j in jobs]):
            print(f"  {fut.result()}", flush=True)
    if not DEM.exists():
        import requests
        DEM.parent.mkdir(parents=True, exist_ok=True)
        DEM.write_bytes(requests.get(DEM_URL, timeout=300).content)


# ----------------------------------------------------------------------------- analysis

def valid_pixels(d: dict[str, np.ndarray]) -> np.ndarray:
    """Valid subswaths in both dates, not water, coherent, in the pair's largest connected component."""
    m = d["mask"].astype(np.int64) & 0xFF
    ok = (m % 10 > 0) & ((m // 10) % 10 > 0) & ((m // 100) % 10 == 0)
    ok &= np.isfinite(d["unwrappedPhase"]) & (d["coherenceMagnitude"] >= COH_MIN)
    cc = d["connectedComponents"]
    labels, counts = np.unique(cc[ok & (cc > 0) & (cc != 65535)], return_counts=True)
    if labels.size == 0:
        return np.zeros_like(ok)
    return ok & (cc == labels[np.argmax(counts)])


def cube_at(d: dict[str, np.ndarray], name: str, height: np.ndarray) -> np.ndarray:
    """A metadata cube interpolated at each pixel's ellipsoid height."""
    from scipy.interpolate import RegularGridInterpolator
    cy, cx = d["cube_y"], d["cube_x"]
    cube = d[name]
    if cy[0] > cy[-1]:
        cy, cube = cy[::-1], cube[:, ::-1, :]
    f = RegularGridInterpolator((d["cube_h"], cy, cx), cube, bounds_error=False, fill_value=None)
    yy, xx = np.meshgrid(d["y"], d["x"], indexing="ij")
    return f(np.stack([height, yy, xx], axis=-1))


def dem_on(d: dict[str, np.ndarray]) -> np.ndarray:
    """GLO-30 ellipsoid height (orthometric + GEOID_M) averaged onto the product's 80 m cells."""
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject
    dx = float(d["x"][1] - d["x"][0])
    out = np.full((d["y"].size, d["x"].size), np.nan, dtype="float32")
    with rasterio.open(DEM) as src:
        reproject(src.read(1), out, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=from_origin(d["x"][0] - dx / 2, d["y"][0] + dx / 2, dx, dx),
                  dst_crs="EPSG:32630", resampling=Resampling.average)
    return out + GEOID_M


def spread(a: np.ndarray, ok: np.ndarray) -> float:
    v = a[ok]
    return float(np.median(np.abs(v - np.median(v))))


def to_vertical_mm(phase: np.ndarray, up: np.ndarray, frequency_hz: float) -> np.ndarray:
    """Unwrapped phase (rad) -> vertical displacement in mm, up positive (LOS towards the satellite)."""
    return -(C / frequency_hz) / (4 * np.pi) * phase / up * 1000.0


def lor1_cell(d: dict[str, np.ndarray]) -> tuple[int, int]:
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True).transform(LOR1_LATLON[1], LOR1_LATLON[0])
    return int(np.argmin(np.abs(d["y"] - y))), int(np.argmin(np.abs(d["x"] - x)))


def gnss_series(dates: list[str], path: Path = GNSS_CSV, half: int = GNSS_HALF_WINDOW_D) -> list[float | None]:
    """GNSS LOR1 vertical (mm) at each date (mean within +-half days) minus the first date."""
    rows = {r["date"]: float(r["up_m"]) * 1000 for r in csv.DictReader(path.open(encoding="utf-8"))}
    vals = []
    for s in dates:
        d0 = date.fromisoformat(s)
        got = [rows[k] for k in ((d0 + timedelta(days=i)).isoformat() for i in range(-half, half + 1)) if k in rows]
        vals.append(float(np.mean(got)) if got else None)
    if vals[0] is None:
        return [None] * len(vals)
    return [None if v is None else round(v - vals[0], 2) for v in vals]


def rate_mm_yr(dates: list[str], values: list[float | None]) -> float | None:
    pts = [(date.fromisoformat(d).toordinal() / 365.25, v) for d, v in zip(dates, values) if v is not None]
    if len(pts) < 3:
        return None
    t, v = np.array(pts).T
    return round(float(np.polyfit(t - t[0], v, 1)[0]), 1)


def detrend(v: np.ndarray, ok: np.ndarray, height: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Remove a plane and a linear height term fitted on the valid pixels (residual atmosphere, orbit)."""
    yy, xx = np.meshgrid((y - y.mean()) / 1e4, (x - x.mean()) / 1e4, indexing="ij")
    hh = (height - np.nanmean(height)) / 1e3
    use = ok & np.isfinite(v) & np.isfinite(hh)
    A = np.column_stack([np.ones(use.sum()), xx[use], yy[use], hh[use]])
    coef, *_ = np.linalg.lstsq(A, v[use], rcond=None)
    return v - (coef[0] + coef[1] * xx + coef[2] * yy + coef[3] * np.nan_to_num(hh))


def detectable_after_days(dates: list[str], sigma_epoch_mm: float, rate_mm_yr: float,
                          step_days: int = 12, k: float = 3.0, horizon_days: int = 3 * 365) -> int | None:
    """Days of record after which a linear fit through epochs with independent noise sigma_epoch_mm
    (atmosphere of each date; it does not accumulate when pairs are chained) resolves rate_mm_yr at k sigma,
    extending the current dates every step_days."""
    t = [date.fromisoformat(d).toordinal() for d in dates]
    while t[-1] - t[0] <= horizon_days:
        ty = (np.array(t) - t[0]) / 365.25
        se = sigma_epoch_mm / np.sqrt(np.sum((ty - ty.mean()) ** 2))
        if abs(rate_mm_yr) >= k * se:
            return t[-1] - t[0]
        t.append(t[-1] + step_days)
    return None


def analyse_stack(stack_id: str, with_detrend: bool = True) -> tuple[dict, np.ndarray | None, dict | None]:
    files = sorted(f for f in (GUNW_RAW / stack_id).glob("*.npz") if ".tmp" not in f.name)
    if not files:
        return {"status": f"no pairs in {GUNW_RAW.relative_to(REPO_ROOT)}/{stack_id}"}, None, None
    pairs = [dict(np.load(f, allow_pickle=False)) for f in files]
    height = dem_on(pairs[0])
    corrections = {"none": lambda d: 0.0,
                   "ionosphere": lambda d: d["ionospherePhaseScreen"],
                   "ionosphere+troposphere": lambda d: d["ionospherePhaseScreen"]
                   + cube_at(d, "wetTroposphericPhaseScreen", height)
                   + cube_at(d, "hydrostaticTroposphericPhaseScreen", height)}
    valid = [valid_pixels(d) for d in pairs]
    scores = {}
    for name, corr in corrections.items():
        s = []
        for d, ok in zip(pairs, valid):
            ph = d["unwrappedPhase"] - corr(d)
            s.append(spread(ph - np.nanmedian(ph[ok]), ok & np.isfinite(ph)))
        scores[name] = round(float(np.median(s)), 3)
    chosen = min(scores, key=scores.get)

    all_ok = np.logical_and.reduce(valid)
    cum = np.zeros_like(pairs[0]["unwrappedPhase"], dtype="float64")
    iy, ix = lor1_cell(pairs[0])
    dates = [str(f.stem).split("_")[0] for f in files[:1]] + [str(f.stem).split("_")[1] for f in files]
    lor1 = [0.0]
    for d, ok in zip(pairs, valid):
        ph = d["unwrappedPhase"] - corrections[chosen](d)
        up = np.sqrt(np.clip(1 - cube_at(d, "losUnitVectorX", height) ** 2 - cube_at(d, "losUnitVectorY", height) ** 2, 0, 1))
        v = to_vertical_mm(ph, up, float(d["frequency_hz"]))
        v = v - np.median(v[ok & np.isfinite(v)])
        if with_detrend:
            v = detrend(v, ok, height, d["x"], d["y"])
        cum += v
        win = (slice(max(iy - 1, 0), iy + 2), slice(max(ix - 1, 0), ix + 2))
        cell = cum[win][all_ok[win]]
        lor1.append(round(float(np.median(cell)), 2) if cell.size else None)
    cum_map = np.where(all_ok, cum, np.nan)
    gnss = gnss_series(dates)
    diffs = [a - b for a, b in zip(lor1, gnss) if a is not None and b is not None]
    incidence_up = float(np.nanmedian(up))

    from scipy.ndimage import uniform_filter
    filled = np.where(all_ok, cum, 0.0)
    w = uniform_filter(all_ok.astype(float), 5)
    smooth = np.where(w > 0.5, uniform_filter(filled, 5) / np.maximum(w, 1e-9), np.nan)
    by, bx = np.unravel_index(np.nanargmin(smooth), smooth.shape)
    dist_km = float(np.hypot(pairs[0]["x"][bx] - pairs[0]["x"][ix], pairs[0]["y"][by] - pairs[0]["y"][iy]) / 1000)
    span_d = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
    result = {
        "stack": stack_id, "pairs": len(pairs), "dates": dates, "span_days": span_d,
        "granules": [str(d["granule_ur"]) for d in pairs],
        "correction_scores_median_spread_rad": scores, "correction_used": chosen,
        "detrend_plane_and_height": with_detrend,
        "valid_in_all_pairs_share": round(float(all_ok.mean()), 3),
        "los_up_component_median": round(incidence_up, 3),
        "lor1": {"nisar_vertical_mm": lor1, "gnss_vertical_mm": gnss,
                 "nisar_rate_mm_yr": rate_mm_yr(dates, lor1), "gnss_rate_mm_yr": rate_mm_yr(dates, gnss),
                 "rms_difference_mm": round(float(np.sqrt(np.mean(np.square(diffs)))), 2) if diffs else None},
        "noise": {"map_p05_p95_mm": [round(float(np.nanpercentile(cum_map, 5)), 1),
                                     round(float(np.nanpercentile(cum_map, 95)), 1)]},
        "most_negative_5x5_cell": {"note": "at the noise level, not a detected bowl", "min_5x5_mm": round(float(np.nanmin(smooth)), 1),
                 "min_rate_mm_yr": round(float(np.nanmin(smooth)) * 365.25 / span_d, 1),
                 "x": float(pairs[0]["x"][bx]), "y": float(pairs[0]["y"][by]), "km_from_lor1": round(dist_km, 1),
                 "p05_mm": round(float(np.nanpercentile(cum_map, 5)), 1),
                 "p50_mm": round(float(np.nanpercentile(cum_map, 50)), 1)},
    }
    L = result["lor1"]
    if L["rms_difference_mm"] and L["gnss_rate_mm_yr"]:
        n_days = detectable_after_days(dates, L["rms_difference_mm"], L["gnss_rate_mm_yr"])
        result["detectability"] = {
            "assumption": "per-date noise = RMS(NISAR - GNSS) at LOR1, independent between dates; GNSS rate holds",
            "rate_1sigma_now_mm_yr": round(L["rms_difference_mm"] / float(np.sqrt(np.sum(np.square(
                (np.array([date.fromisoformat(d).toordinal() for d in dates]) - np.mean([date.fromisoformat(d).toordinal() for d in dates])) / 365.25)))), 1),
            "days_of_record_for_3_sigma": n_days,
            "date_for_3_sigma": None if n_days is None else (date.fromisoformat(dates[0]) + timedelta(days=n_days)).isoformat()}
    return result, cum_map, {"x": pairs[0]["x"], "y": pairs[0]["y"], "lor1": (iy, ix), "bowl": (by, bx)}


def plot(results: list[tuple[dict, np.ndarray, dict]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(results)
    fig, axes = plt.subplots(2, n, figsize=(6 * n, 10), squeeze=False)
    for k, (res, cum, geo) in enumerate(results):
        ax = axes[0, k]
        ext = [geo["x"][0] / 1e3, geo["x"][-1] / 1e3, geo["y"][-1] / 1e3, geo["y"][0] / 1e3]
        im = ax.imshow(cum, cmap="RdBu", vmin=-40, vmax=40, extent=ext)
        ax.plot(geo["x"][geo["lor1"][1]] / 1e3, geo["y"][geo["lor1"][0]] / 1e3, "k^", ms=8, label="GNSS LOR1")
        ax.set_title(f"NISAR {res['stack']}: vertical {res['dates'][0]} → {res['dates'][-1]}")
        ax.set_xlabel("UTM 30N x (km)"), ax.set_ylabel("y (km)"), ax.legend(loc="lower right", fontsize=8)
        fig.colorbar(im, ax=ax, label="mm (up +)", shrink=0.8)
        ax = axes[1, k]
        t = [date.fromisoformat(d) for d in res["dates"]]
        ax.plot(t, res["lor1"]["nisar_vertical_mm"], "o-", label=f"NISAR at LOR1 ({res['lor1']['nisar_rate_mm_yr']} mm/yr)")
        ax.plot(t, res["lor1"]["gnss_vertical_mm"], "s--", label=f"GNSS LOR1 ({res['lor1']['gnss_rate_mm_yr']} mm/yr)")
        ax.axhline(0, color="#999", lw=0.8)
        ax.set_ylabel("vertical since first date (mm)"), ax.legend(fontsize=8), ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(FIG, dpi=110)


def analyse() -> int:
    if not DEM.exists() or not any(GUNW_RAW.glob("*/*.npz")):
        print(f"missing GUNW subsets or DEM: run python -m pipeline.prediction.lorca_gunw fetch; {OUT.name} left unchanged")
        return 1
    done = [analyse_stack(s) for s in STACKS]
    raw = {s: analyse_stack(s, with_detrend=False)[0] for s in STACKS}
    ok = [r for r in done if r[1] is not None]
    result = {"issued_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "method": __doc__.split("Steps, all fixed before looking at the result:")[1].split("Two tracks")[0].strip(),
              "dem": "Copernicus GLO-30 (c) DLR e.V. 2010-2014 and (c) Airbus 2014-2018, provided under COPERNICUS by the EU and ESA",
              "detrend_note": DETREND_NOTE,
              "stacks": {r[0].get("stack", s): r[0] for r, s in zip(done, STACKS)},
              "without_detrend": {s: {"lor1": raw[s].get("lor1")} for s in STACKS}}
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    if ok:
        plot(ok)
    for r, _, _ in ok:
        L = r["lor1"]
        print(f"{r['stack']} {r['dates'][0]}..{r['dates'][-1]} ({r['pairs']} pairs, {r['correction_used']}): "
              f"LOR1 NISAR {L['nisar_rate_mm_yr']} mm/yr vs GNSS {L['gnss_rate_mm_yr']} mm/yr, RMS {L['rms_difference_mm']} mm; "
              f"map 5-95 % {r['noise']['map_p05_p95_mm']} mm; 3 sigma by {r.get('detectability', {}).get('date_for_3_sigma')}")
        print(f"   NISAR {L['nisar_vertical_mm']}\n   GNSS  {L['gnss_vertical_mm']}\n   scores {r['correction_scores_median_spread_rad']}")
    print(f"-> {OUT.relative_to(REPO_ROOT)}, {FIG.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("fetch", "analyse", "all"))
    args = parser.parse_args(argv)
    if args.command in ("fetch", "all"):
        fetch()
    if args.command in ("analyse", "all"):
        return analyse()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
