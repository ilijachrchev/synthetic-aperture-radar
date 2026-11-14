"""Who is right on 18 June 2026: NISAR or Sentinel-1? A sample-based check (discussion #25).

On 18 Jun, inside the Albufera rice mask, NISAR (track 066 D, 18:53 UTC, 5x5-filtered HH below
-15 dB) sees about 6,400 ha of water. DSWx-S1 (Sentinel-1, 17:54 UTC, open water + inundated
vegetation) sees about 250 ha. This module settles it with an independent referee, no hand labels.

Referee: Sentinel-2. There is no clear image on 18 Jun (100 % cloud over the rice). The nearest
clear ones are 8 Jun (10 days before) and 23 Jun (5 days after). Per point and date the rice is
"wet" when the classic rice-flooding signal holds (LSWI + 0.05 >= EVI, Xiao et al. 2005) or
MNDWI > 0 (Xu 2006). The 18 Jun label brackets the two dates:

    wet     wet on 8 Jun AND on 23 Jun   (water before and after: almost surely water between)
    dry     dry on 8 Jun AND on 23 Jun
    unclear the two disagree, or a date is cloudy

Neither radar is used to make the label, so the check is not circular.

Design (Olofsson et al. 2014, "Good practices for estimating area and assessing accuracy of
land change", RSE 148):

    strata  A both maps say water · B NISAR only · C Sentinel-1 only · D neither (rice pixels)
            E control: non-rice cropland (WorldCover 40), should be dry
    sample  candidates on a 200 m grid with a random offset (points are not neighbours), then
            n random points per stratum, fixed seed
    score   stratum-weighted estimates (weights = stratum area) of each map's user's and
            producer's accuracy and of the wet area, 95 % intervals by a stratified bootstrap

Pre-registered rule (discussion #25, before the score was run): NISAR "wins" when its user's
accuracy in stratum B is >= 70 % and the lower end of its 95 % interval is >= 60 %.

Known bias, said up front: optical images do not see water under a closed canopy (median NDVI of
the rice is about 0.7 on 23 Jun), so some flooded fields are labelled "dry" or "unclear". That
bias works AGAINST NISAR (its water calls look wrong more often) and in favour of Sentinel-1's
"dry" calls.

Two steps, so the points are fixed (and committed) before anyone sees the referee:

    python -m pipeline.validation.june18 sample [--data DIR]
    python -m pipeline.validation.june18 score  [--data DIR]

Writes data/validation/june18/points.csv, reference.csv and result.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path

import numpy as np

from pipeline.config import DATA_DIR

OUT_DIR = DATA_DIR / "validation" / "june18"
STACK_FILE = "albufera_066_D_069.nc"
DATE = "2026-06-18"
NISAR_DB = -15.0
DSWX_WATER = (1, 3)        # open water, inundated vegetation (JPL D-108761 Rev A)
DSWX_INVALID = (250, 251, 255)
WORLDCOVER_CROPLAND = 40
GRID_STEP_PX = 10          # 200 m between candidate points
N_PER_STRATUM = 150
SEED = 20261118
BOOTSTRAP = 2000
STRATA = ("A", "B", "C", "D", "E")
STRATUM_NAMES = {
    "A": "both say water",
    "B": "NISAR water, Sentinel-1 dry",
    "C": "Sentinel-1 water, NISAR dry",
    "D": "both say dry",
    "E": "control: non-rice cropland",
}
# Sentinel-2 L2A from Element 84 Earth Search (public COGs, no login). These items carry
# earthsearch:boa_offset_applied = true: reflectance is DN / 10000 (subtracting the 0.1 offset
# again gives negative SWIR and NDVI above 1 over the rice).
S2_ITEMS = {
    "2026-06-08": "S2C_30SYJ_20260608_0_L2A",
    "2026-06-23": "S2B_30SYJ_20260623_0_L2A",
}
S2_BASE = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/30/S/YJ"
S2_BANDS = ("B02", "B03", "B04", "B8A", "B11", "SCL")
SCL_BAD = (0, 1, 3, 8, 9, 10)   # no data, defective, cloud shadow, clouds, cirrus
RULE = {"min_share_pass": 0.70, "min_ci_low": 0.60}


# ---------- pure functions (tested) ----------

def strata_map(rice: np.ndarray, control: np.ndarray, valid: np.ndarray,
               nisar_water: np.ndarray, s1_water: np.ndarray, s1_valid: np.ndarray) -> np.ndarray:
    """One letter per pixel: A-D inside the rice, E on control cropland, '' elsewhere."""
    ok = valid & s1_valid
    out = np.full(rice.shape, "", dtype="<U1")
    r = rice & ok
    out[r & nisar_water & s1_water] = "A"
    out[r & nisar_water & ~s1_water] = "B"
    out[r & ~nisar_water & s1_water] = "C"
    out[r & ~nisar_water & ~s1_water] = "D"
    out[control & ok & ~rice] = "E"
    return out


def sample_points(strata: np.ndarray, n: int = N_PER_STRATUM, step: int = GRID_STEP_PX,
                  seed: int = SEED) -> list[tuple[str, int, int]]:
    """(stratum, row, col): candidates on a grid `step` pixels apart with a random offset, then up
    to n random candidates per stratum."""
    rng = np.random.default_rng(seed)
    r0, c0 = (int(v) for v in rng.integers(0, step, size=2))
    rows, cols = np.mgrid[r0:strata.shape[0]:step, c0:strata.shape[1]:step]
    rows, cols = rows.ravel(), cols.ravel()
    labels = strata[rows, cols]
    picked = []
    for s in STRATA:
        idx = np.flatnonzero(labels == s)
        take = idx if idx.size <= n else rng.choice(idx, size=n, replace=False)
        picked += [(s, int(rows[i]), int(cols[i])) for i in sorted(take)]
    return picked


def wet_on_date(b02, b03, b04, b8a, b11) -> np.ndarray:
    """Rice-flooding signal from surface reflectance (0-1): LSWI + 0.05 >= EVI, or MNDWI > 0."""
    b02, b03, b04, b8a, b11 = (np.asarray(x, dtype="float64") for x in (b02, b03, b04, b8a, b11))
    with np.errstate(divide="ignore", invalid="ignore"):
        lswi = (b8a - b11) / (b8a + b11)
        evi = 2.5 * (b8a - b04) / (b8a + 6.0 * b04 - 7.5 * b02 + 1.0)
        mndwi = (b03 - b11) / (b03 + b11)
    return (lswi + 0.05 >= evi) | (mndwi > 0)


def bracket_label(wet_before, wet_after, ok_before, ok_after) -> np.ndarray:
    """'wet' when wet on both dates, 'dry' when dry on both, else 'unclear'."""
    wb, wa = np.asarray(wet_before, bool), np.asarray(wet_after, bool)
    ok = np.asarray(ok_before, bool) & np.asarray(ok_after, bool)
    out = np.full(wb.shape, "unclear", dtype="<U7")
    out[ok & wb & wa] = "wet"
    out[ok & ~wb & ~wa] = "dry"
    return out


def estimates(points: list[dict], weights: dict[str, float]) -> dict:
    """Stratum-weighted accuracy and area from decided points (wet/dry) of strata A-D.

    p_h = share of decided points in stratum h that the referee calls wet. With W_h the stratum's
    share of the rice area:
        NISAR user's accuracy     = (W_A p_A + W_B p_B) / (W_A + W_B)
        NISAR producer's accuracy = (W_A p_A + W_B p_B) / sum_h W_h p_h
        Sentinel-1 user's         = (W_A p_A + W_C p_C) / (W_A + W_C)
        Sentinel-1 producer's     = (W_A p_A + W_C p_C) / sum_h W_h p_h
        wet share of the rice     = sum_h W_h p_h
    """
    p = {}
    for s in "ABCD":
        lab = [q["label"] for q in points if q["stratum"] == s and q["label"] in ("wet", "dry")]
        p[s] = (sum(x == "wet" for x in lab) / len(lab)) if lab else float("nan")
    W = {s: weights.get(s, 0.0) for s in "ABCD"}
    term = {s: (W[s] * p[s] if W[s] > 0 else 0.0) for s in "ABCD"}
    wet_total = sum(term.values())
    div = lambda a, b: a / b if b > 0 else float("nan")
    return {
        "p_wet": p,
        "nisar_user": div(term["A"] + term["B"], W["A"] + W["B"]),
        "nisar_producer": div(term["A"] + term["B"], wet_total),
        "s1_user": div(term["A"] + term["C"], W["A"] + W["C"]),
        "s1_producer": div(term["A"] + term["C"], wet_total),
        "b_user": p["B"],
        "wet_share": wet_total,
    }


def bootstrap(points: list[dict], weights: dict[str, float], reps: int = BOOTSTRAP, seed: int = SEED) -> dict:
    """95 % intervals: resample points within each stratum, recompute `estimates`."""
    rng = np.random.default_rng(seed)
    by = {s: [q for q in points if q["stratum"] == s] for s in "ABCD"}
    keys = ("nisar_user", "nisar_producer", "s1_user", "s1_producer", "b_user", "wet_share")
    draws = {k: [] for k in keys}
    for _ in range(reps):
        res = []
        for s, qs in by.items():
            if qs:
                res += [qs[i] for i in rng.integers(0, len(qs), size=len(qs))]
        e = estimates(res, weights)
        for k in keys:
            draws[k].append(e[k])
    return {k: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))] for k, v in draws.items()}


def verdict(b_user: float, b_ci: list[float]) -> str:
    """The pre-registered rule, applied to NISAR's user's accuracy in stratum B."""
    if b_user >= RULE["min_share_pass"] and b_ci[0] >= RULE["min_ci_low"]:
        return "NISAR wins: most water only NISAR sees is water by the independent referee"
    return "NISAR does not pass the pre-registered rule"


# ---------- data (needs the stack, DSWx files and network) ----------

def _grid(data: Path):
    import rasterio
    from pipeline.prediction.albufera.mask import load as load_mask
    rice, grid = load_mask(data / "prediction" / "albufera" / "rice_mask.tif")
    with rasterio.open(data / "prediction" / "albufera" / "rice_mask.tif") as src:
        transform, crs, shape = src.transform, src.crs, src.shape
    with rasterio.open(data / "context" / "albufera_worldcover_2021_20m.tif") as src:
        control = (src.read(1) == WORLDCOVER_CROPLAND) & ~rice
    return rice, control, transform, crs, shape


def _onto(path: str, transform, crs, shape, fill: float, resampling):
    import rasterio
    from rasterio.warp import reproject
    out = np.full(shape, fill, dtype="float32")
    with rasterio.open(path) as src:
        reproject(rasterio.band(src, 1), out, src_nodata=src.nodata, dst_nodata=fill,
                  dst_transform=transform, dst_crs=crs, resampling=resampling)
    return out


def build_strata(data: Path) -> tuple[np.ndarray, dict]:
    from rasterio.warp import Resampling
    from pipeline.cv.data import open_stack
    from pipeline.prediction.nisar_check import scene_db
    rice, control, transform, crs, shape = _grid(data)
    ds = open_stack(data / "stack" / STACK_FILE)
    times = [str(t)[:10] for t in ds["time"].values]
    i = times.index(DATE)
    hh, ok, _ = scene_db(ds, i)
    nisar_water = ok & (hh < NISAR_DB)
    files = sorted(glob.glob(str(data / "raw" / "dswx" / "albufera" / "066_D_069" / DATE.replace("-", "") / "*_B01_WTR.tif")))
    if not files:
        raise FileNotFoundError("no DSWx-S1 files for 18 Jun: run python -m pipeline.dswx first")
    wtr = np.full(shape, 255.0, dtype="float32")
    for f in files:   # the site spans two MGRS tiles: take each valid pixel from whichever tile has it
        layer = _onto(f, transform, crs, shape, 255.0, Resampling.nearest)
        take = ~np.isin(layer, DSWX_INVALID) & np.isin(wtr, DSWX_INVALID)
        wtr[take] = layer[take]
    s1_valid = ~np.isin(wtr, DSWX_INVALID)
    s1_water = np.isin(wtr, DSWX_WATER)
    strata = strata_map(rice, control, ok, nisar_water, s1_water, s1_valid)
    rice_px = float(np.isin(strata, list("ABCD")).sum())
    info = {
        "nisar_time": str(ds["time"].values[i])[:19],
        "granule": str(ds["granule_ur"].values[i]),
        "dswx_files": [Path(f).name for f in files],
        "rice_ha_scored": round(rice_px * 0.04, 1),
        "nisar_water_ha": round(float((rice & ok & s1_valid & nisar_water).sum()) * 0.04, 1),
        "s1_water_ha": round(float((rice & ok & s1_valid & s1_water).sum()) * 0.04, 1),
        "stratum_ha": {s: round(float((strata == s).sum()) * 0.04, 1) for s in STRATA},
        "weights": {s: float((strata == s).sum()) / rice_px for s in "ABCD"},
    }
    return strata, info


def cmd_sample(data: Path, out: Path) -> dict:
    import rasterio
    from rasterio.warp import transform as warp_xy
    strata, info = build_strata(data)
    _, _, transform, crs, _ = _grid(data)
    pts = sample_points(strata)
    xs, ys = zip(*[rasterio.transform.xy(transform, r, c) for _, r, c in pts])
    lons, lats = warp_xy(crs, "EPSG:4326", list(xs), list(ys))
    out.mkdir(parents=True, exist_ok=True)
    with (out / "points.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "stratum", "row", "col", "x_utm30n", "y_utm30n", "lon", "lat"])
        for k, ((s, r, c), x, y, lo, la) in enumerate(zip(pts, xs, ys, lons, lats)):
            w.writerow([k, s, r, c, round(x, 1), round(y, 1), round(lo, 6), round(la, 6)])
    info["n_points"] = {s: sum(p[0] == s for p in pts) for s in STRATA}
    info["design"] = {"grid_step_m": GRID_STEP_PX * 20, "n_per_stratum": N_PER_STRATUM, "seed": SEED,
                      "nisar_threshold_db": NISAR_DB, "dswx_water_classes": list(DSWX_WATER)}
    (out / "strata.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    return info


def _s2_layers(transform, crs, shape) -> dict:
    from rasterio.warp import Resampling
    layers = {}
    for day, item in S2_ITEMS.items():
        y, m = day[:4], int(day[5:7])
        url = lambda b: f"/vsicurl/{S2_BASE}/{y}/{m}/{item}/{b}.tif"
        bands = {b: _onto(url(b), transform, crs, shape, np.nan, Resampling.average) / 10000.0 for b in S2_BANDS[:-1]}
        scl = _onto(url("SCL"), transform, crs, shape, 0.0, Resampling.nearest)
        layers[day] = (bands, scl)
    return layers


def cmd_score(data: Path, out: Path) -> dict:
    strata_info = json.loads((out / "strata.json").read_text(encoding="utf-8"))
    with (out / "points.csv").open(encoding="utf-8") as f:
        pts = list(csv.DictReader(f))
    _, _, transform, crs, shape = _grid(data)
    layers = _s2_layers(transform, crs, shape)
    rows = np.array([int(p["row"]) for p in pts])
    cols = np.array([int(p["col"]) for p in pts])

    def at(a):   # 3x3 mean around each point (60 m): less noise from one pixel
        vals = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr = np.clip(rows + dr, 0, shape[0] - 1)
                cc = np.clip(cols + dc, 0, shape[1] - 1)
                vals.append(a[rr, cc])
        return np.nanmean(np.stack(vals), axis=0)

    per_day, sanity = {}, {}
    for day, (b, scl) in layers.items():
        v = {k: at(b[k]) for k in b}
        wet = wet_on_date(v["B02"], v["B03"], v["B04"], v["B8A"], v["B11"])
        ok = ~np.isin(scl[rows, cols], SCL_BAD) & np.isfinite(v["B11"])
        ndvi = (v["B8A"] - v["B04"]) / (v["B8A"] + v["B04"])
        sanity[day] = {"median_ndvi": round(float(np.nanmedian(ndvi)), 3), "median_b11": round(float(np.nanmedian(v["B11"])), 4)}
        if not (0 < sanity[day]["median_b11"] < 0.6 and -0.2 < sanity[day]["median_ndvi"] < 1):
            raise ValueError(f"Sentinel-2 {day} reflectance looks wrong ({sanity[day]}): check the offset")
        per_day[day] = (wet, ok)
    (d0, (w0, k0)), (d1, (w1, k1)) = per_day.items()
    label = bracket_label(w0, w1, k0, k1)
    for p, l, a, b, ka, kb in zip(pts, label, w0, w1, k0, k1):
        p.update({"label": str(l), f"wet_{d0}": int(a) if ka else "", f"wet_{d1}": int(b) if kb else ""})
    with (out / "reference.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(pts[0]))
        w.writeheader()
        w.writerows(pts)

    weights = strata_info["weights"]
    est = estimates(pts, weights)
    ci = bootstrap(pts, weights)
    counts = {s: {lab: sum(1 for p in pts if p["stratum"] == s and p["label"] == lab) for lab in ("wet", "dry", "unclear")} for s in STRATA}
    rice_ha = strata_info["rice_ha_scored"]
    result = {
        "question": "18 Jun 2026, Albufera rice: who is right, NISAR or Sentinel-1?",
        "referee": f"Sentinel-2 L2A {d0} and {d1}; wet = (LSWI + 0.05 >= EVI) or MNDWI > 0 on both dates",
        "maps": {"nisar_water_ha": strata_info["nisar_water_ha"], "s1_water_ha": strata_info["s1_water_ha"], "rice_ha_scored": rice_ha},
        "stratum_ha": strata_info["stratum_ha"],
        "counts": counts,
        "control_E_wet_share": _share(counts["E"]),
        "estimates": {k: (round(v, 3) if isinstance(v, float) else {s: round(x, 3) for s, x in v.items()}) for k, v in est.items()},
        "ci95": {k: [round(a, 3), round(b, 3)] for k, (a, b) in ci.items()},
        "wet_rice_ha": [round(est["wet_share"] * rice_ha), [round(ci["wet_share"][0] * rice_ha), round(ci["wet_share"][1] * rice_ha)]],
        "rule": RULE,
        "verdict": verdict(est["b_user"], ci["b_user"]),
        "s2_sanity": sanity,
        "bias_note": "optical misses water under a closed canopy: the referee is biased against NISAR",
    }
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def _share(c: dict) -> float | None:
    n = c["wet"] + c["dry"]
    return round(c["wet"] / n, 3) if n else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("sample", "score"))
    ap.add_argument("--data", type=Path, default=DATA_DIR, help="data folder with the stack and DSWx files")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    a = ap.parse_args(argv)
    res = cmd_sample(a.data, a.out) if a.step == "sample" else cmd_score(a.data, a.out)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
