"""Who is right on 18 June 2026: NISAR or Sentinel-1? A sample-based check (discussion #25).

On 18 Jun, inside the Albufera rice mask, NISAR (track 066 D, 18:53 UTC, 5x5-filtered HH below
-15 dB) sees about 6,400 ha of water. DSWx-S1 (Sentinel-1, 17:54 UTC, open water + inundated
vegetation) sees about 250 ha. This module settles it with an independent referee, no hand labels.

Referee: optical satellites, never the radars, so the check is not circular. There is no clear
image on 18 Jun (100 % cloud over the rice). Per point and date the rice is "wet" when the
classic rice-flooding signal holds (LSWI + 0.05 >= EVI, Xiao et al. 2005) or MNDWI > 0 (Xu 2006).

Rule v2 (pre-registered in its own commit before it was run, after the review on #25):

    before  Sentinel-2, 8 Jun (10 days before)
    after   the closest clear look after 18 Jun: Landsat 9, 22 Jun (4 days after; Planetary
            Computer, no login); where Landsat is cloudy or has no data, Sentinel-2, 23 Jun
    wet     wet before AND wet after (water before and after: very likely water between)
    dry     dry before AND dry after
    unclear the two disagree, or no clear look

Rule v1 (8 Jun + 23 Jun) and a strict variant (MNDWI > 0 only, the open-water signal, which wet
mud trips less often than LSWI) are reported next to it.

Design (Olofsson et al. 2014, "Good practices for estimating area and assessing accuracy of
land change", RSE 148):

    strata  A both maps say water · B NISAR only · C Sentinel-1 only · D neither (rice pixels)
            E control: non-rice cropland (WorldCover 40), should be dry
    sample  candidates on a 200 m grid with a random offset (points are not neighbours), then
            n random points per stratum, fixed seed (points committed before any scoring)
    score   any binary water map is scored on the same points, stratum-weighted (weight = the
            stratum's share of the rice). Only decided points (wet or dry) count: nothing is
            imputed. Bounds show the two extremes: every unclear point dry, every one wet.
            95 % intervals by a stratified bootstrap.

Maps scored: NISAR threshold (the strata), DSWx-S1, and the app's U-Net water map (decoded from
the baked web frame web/public/layers/albufera/nisar_066_D_069/00.webp, all water = open +
flooded vegetation).

Pre-registered rule (discussion #25, before the first score): NISAR "wins" when its user's
accuracy in stratum B is >= 70 % and the lower end of its 95 % interval is >= 60 %.

Known limits, said up front: optical images do not see water under a closed canopy, so the
referee is biased against NISAR; "wet before and after" cannot see a drainage of a few days
around 18 Jun (eixugo); and wet mud can trip both the flooding index and NISAR's dark threshold.

    python -m pipeline.validation.june18 sample [--data DIR]
    python -m pipeline.validation.june18 score  [--data DIR]

Writes data/validation/june18/points.csv, strata.json, reference.csv and result.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
from pathlib import Path

import numpy as np

from pipeline.config import DATA_DIR, REPO_ROOT

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
S2_BANDS = {"blue": "B02", "green": "B03", "red": "B04", "nir": "B8A", "swir": "B11"}
SCL_BAD = (0, 1, 3, 8, 9, 10)   # no data, defective, cloud shadow, clouds, cirrus
# Landsat 9 Collection 2 Level 2 from Microsoft Planetary Computer (signed with a free token)
L9_ITEM = ("2026-06-22", "LC09_L2SP_198033_20260622_02_T1")
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2/items/"
PC_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2"
L9_BANDS = {"blue": "blue", "green": "green", "red": "red", "nir": "nir08", "swir": "swir16"}
L9_SCALE, L9_OFFSET = 2.75e-5, -0.2
# QA_PIXEL bits: 0 fill, 1 dilated cloud, 3 cloud, 4 cloud shadow
L9_QA_BAD_BITS = (0, 1, 3, 4)
UNET_FRAME = REPO_ROOT / "web" / "public" / "layers" / "albufera" / "nisar_066_D_069" / "00.webp"
UNET_META = REPO_ROOT / "web" / "public" / "layers" / "albufera" / "meta.json"
WEB_ORIGIN = 20037508.342789244
RULE = {"min_share_pass": 0.70, "min_ci_low": 0.60}
MAPS = ("nisar", "s1", "unet")


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


def wet_on_date(blue, green, red, nir, swir, strict: bool = False) -> np.ndarray:
    """Rice-flooding signal from surface reflectance (0-1): LSWI + 0.05 >= EVI, or MNDWI > 0.
    `strict` keeps only MNDWI > 0 (open water), which wet mud trips less often."""
    blue, green, red, nir, swir = (np.asarray(x, dtype="float64") for x in (blue, green, red, nir, swir))
    with np.errstate(divide="ignore", invalid="ignore"):
        lswi = (nir - swir) / (nir + swir)
        evi = 2.5 * (nir - red) / (nir + 6.0 * red - 7.5 * blue + 1.0)
        mndwi = (green - swir) / (green + swir)
    return (mndwi > 0) if strict else ((lswi + 0.05 >= evi) | (mndwi > 0))


def bracket_label(wet_before, wet_after, ok_before, ok_after) -> np.ndarray:
    """'wet' when wet on both dates, 'dry' when dry on both, else 'unclear'."""
    wb, wa = np.asarray(wet_before, bool), np.asarray(wet_after, bool)
    ok = np.asarray(ok_before, bool) & np.asarray(ok_after, bool)
    out = np.full(wb.shape, "unclear", dtype="<U7")
    out[ok & wb & wa] = "wet"
    out[ok & ~wb & ~wa] = "dry"
    return out


def closest_after(wet_first, ok_first, wet_second, ok_second):
    """The first look where it is clear, else the second: (wet, ok)."""
    of, os_ = np.asarray(ok_first, bool), np.asarray(ok_second, bool)
    wet = np.where(of, np.asarray(wet_first, bool), np.asarray(wet_second, bool))
    return wet, of | os_


def map_accuracy(points: list[dict], weights: dict[str, float], key: str, label: str = "label",
                 unclear_as: str | None = None) -> dict:
    """User's and producer's accuracy of map `key` (0/1 per point), stratum-weighted.

    In each stratum h, over the decided points (or all points with unclear set to `unclear_as`):
        a_h = share where the map says water AND the referee says wet
        m_h = share where the map says water
        w_h = share the referee says wet
    user's = sum W_h a_h / sum W_h m_h ; producer's = sum W_h a_h / sum W_h w_h
    """
    num = den_u = den_p = 0.0
    n_used = 0
    for s in "ABCD":
        rows = []
        for q in points:
            if q["stratum"] != s:
                continue
            lab = q[label] if q[label] != "unclear" else unclear_as
            if lab in ("wet", "dry"):
                rows.append((int(q[key]), lab == "wet"))
        if not rows or weights.get(s, 0.0) <= 0:
            continue
        n_used += len(rows)
        W = weights[s]
        num += W * sum(m and w for m, w in rows) / len(rows)
        den_u += W * sum(m for m, _ in rows) / len(rows)
        den_p += W * sum(w for _, w in rows) / len(rows)
    div = lambda a, b: a / b if b > 0 else float("nan")
    return {"user": div(num, den_u), "producer": div(num, den_p), "wet_share": den_p, "n": n_used}


def stratum_wet_share(points: list[dict], stratum: str, label: str = "label") -> float:
    lab = [q[label] for q in points if q["stratum"] == stratum and q[label] in ("wet", "dry")]
    return sum(x == "wet" for x in lab) / len(lab) if lab else float("nan")


def bootstrap(points: list[dict], weights: dict[str, float], keys=MAPS, label: str = "label",
              reps: int = BOOTSTRAP, seed: int = SEED) -> dict:
    """95 % intervals: resample points within each stratum, recompute."""
    rng = np.random.default_rng(seed)
    by = {s: [q for q in points if q["stratum"] == s] for s in "ABCD"}
    draws: dict[str, list[float]] = {}
    for _ in range(reps):
        res = []
        for qs in by.values():
            if qs:
                res += [qs[i] for i in rng.integers(0, len(qs), size=len(qs))]
        for k in keys:
            m = map_accuracy(res, weights, k, label)
            draws.setdefault(f"{k}_user", []).append(m["user"])
            draws.setdefault(f"{k}_producer", []).append(m["producer"])
        draws.setdefault("b_user", []).append(stratum_wet_share(res, "B", label))
    return {k: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))] for k, v in draws.items()}


def verdict(b_user: float, b_ci: list[float]) -> str:
    """The pre-registered rule, applied to NISAR's user's accuracy in stratum B."""
    if b_user >= RULE["min_share_pass"] and b_ci[0] >= RULE["min_ci_low"]:
        return "NISAR wins: most water only NISAR sees is water by the independent referee"
    return "NISAR does not pass the pre-registered rule"


def decode_distance(code: np.ndarray) -> np.ndarray:
    """Signed distance (grid pixels, negative in water) from the web frame's byte (bake_water.py)."""
    linear_px, range_px = 4.0, 300.0
    c = code.astype("float32") - 128
    a = np.abs(c)
    s = np.where(a <= 32, a * (linear_px / 32), linear_px + (range_px - linear_px) * ((a - 32) / 95) ** 2)
    return np.sign(c) * s


# ---------- data (needs the stack, DSWx files and network) ----------

def _grid(data: Path):
    import rasterio
    from pipeline.prediction.albufera.mask import load as load_mask
    rice, _ = load_mask(data / "prediction" / "albufera" / "rice_mask.tif")
    with rasterio.open(data / "prediction" / "albufera" / "rice_mask.tif") as src:
        transform, crs, shape = src.transform, src.crs, src.shape
    with rasterio.open(data / "context" / "albufera_worldcover_2021_20m.tif") as src:
        control = (src.read(1) == WORLDCOVER_CROPLAND) & ~rice
    return rice, control, transform, crs, shape


def _onto(src_like, transform, crs, shape, fill: float, resampling, src_transform=None, src_crs=None):
    """Reproject a file path (or an array with its transform and crs) onto the site grid."""
    import rasterio
    from rasterio.warp import reproject
    out = np.full(shape, fill, dtype="float32")
    if isinstance(src_like, np.ndarray):
        reproject(src_like.astype("float32"), out, src_transform=src_transform, src_crs=src_crs,
                  dst_transform=transform, dst_crs=crs, resampling=resampling)
        return out
    with rasterio.open(src_like) as src:
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


def _s2_day(day: str, item: str, transform, crs, shape):
    from rasterio.warp import Resampling
    url = lambda b: f"/vsicurl/{S2_BASE}/{day[:4]}/{int(day[5:7])}/{item}/{b}.tif"
    bands = {k: _onto(url(b), transform, crs, shape, np.nan, Resampling.average) / 10000.0 for k, b in S2_BANDS.items()}
    scl = _onto(url("SCL"), transform, crs, shape, 0.0, Resampling.nearest)
    return bands, ~np.isin(scl, SCL_BAD)


def _l9_day(transform, crs, shape):
    import requests
    from rasterio.warp import Resampling
    item = requests.get(PC_STAC + L9_ITEM[1], timeout=60).json()
    token = requests.get(PC_TOKEN, timeout=60).json()["token"]
    href = lambda a: f"/vsicurl/{item['assets'][a]['href']}?{token}"
    bands = {}
    for k, a in L9_BANDS.items():
        dn = _onto(href(a), transform, crs, shape, np.nan, Resampling.average)
        dn[dn == 0] = np.nan
        bands[k] = dn * L9_SCALE + L9_OFFSET
    qa = _onto(href("qa_pixel"), transform, crs, shape, 1.0, Resampling.nearest).astype("int64")
    bad = np.zeros(shape, bool)
    for b in L9_QA_BAD_BITS:
        bad |= (qa >> b) & 1 == 1
    return bands, ~bad


def _unet_water(transform, crs, shape) -> tuple[np.ndarray, np.ndarray]:
    """The app's U-Net water map on 18 Jun (all water) and where that pass saw the ground."""
    from PIL import Image
    from rasterio.transform import Affine
    from rasterio.warp import Resampling
    meta = json.loads(UNET_META.read_text(encoding="utf-8"))
    frame0 = meta["series"][0]["frames"][0]
    if frame0["date"] != DATE:
        raise ValueError(f"first web frame is {frame0['date']}, not {DATE}")
    rgb = np.asarray(Image.open(UNET_FRAME).convert("RGB"))
    res = 2 * WEB_ORIGIN / (256 * 2 ** meta["zoom"])
    lon0, lat1 = meta["bounds"][0], meta["bounds"][3]
    x0 = WEB_ORIGIN * lon0 / 180.0
    y1 = WEB_ORIGIN * math.log(math.tan(math.pi / 4 + math.radians(lat1) / 2)) / math.pi
    t = Affine(res, 0, round((x0 + WEB_ORIGIN) / res) * res - WEB_ORIGIN, 0, -res,
               WEB_ORIGIN - round((WEB_ORIGIN - y1) / res) * res)
    water = (decode_distance(rgb[..., 1]) < 0).astype("float32")
    seen = (rgb[..., 0] > 127).astype("float32")
    w = _onto(water, transform, crs, shape, 0.0, Resampling.nearest, t, "EPSG:3857") > 0.5
    s = _onto(seen, transform, crs, shape, 0.0, Resampling.nearest, t, "EPSG:3857") > 0.5
    return w, s


def _at(a, rows, cols, shape):
    """3x3 mean around each point (60 m): less noise from one pixel."""
    vals = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            vals.append(a[np.clip(rows + dr, 0, shape[0] - 1), np.clip(cols + dc, 0, shape[1] - 1)])
    return np.nanmean(np.stack(vals).astype("float64"), axis=0)


def cmd_score(data: Path, out: Path) -> dict:
    strata_info = json.loads((out / "strata.json").read_text(encoding="utf-8"))
    with (out / "points.csv").open(encoding="utf-8") as f:
        pts = list(csv.DictReader(f))
    _, _, transform, crs, shape = _grid(data)
    rows = np.array([int(p["row"]) for p in pts])
    cols = np.array([int(p["col"]) for p in pts])

    looks = {d: _s2_day(d, item, transform, crs, shape) for d, item in S2_ITEMS.items()}
    looks[L9_ITEM[0]] = _l9_day(transform, crs, shape)
    wet, ok, wet_strict, sanity = {}, {}, {}, {}
    for day, (b, clear) in looks.items():
        v = {k: _at(b[k], rows, cols, shape) for k in b}
        wet[day] = wet_on_date(v["blue"], v["green"], v["red"], v["nir"], v["swir"])
        wet_strict[day] = wet_on_date(v["blue"], v["green"], v["red"], v["nir"], v["swir"], strict=True)
        ok[day] = clear[rows, cols] & np.isfinite(v["swir"])
        with np.errstate(divide="ignore", invalid="ignore"):
            ndvi = (v["nir"] - v["red"]) / (v["nir"] + v["red"])
        sanity[day] = {"median_ndvi": round(float(np.nanmedian(ndvi)), 3), "median_swir": round(float(np.nanmedian(v["swir"])), 4),
                       "clear_points": int(ok[day].sum())}
        if not (0 < sanity[day]["median_swir"] < 0.6 and -0.2 < sanity[day]["median_ndvi"] < 1):
            raise ValueError(f"{day} reflectance looks wrong ({sanity[day]}): check scale and offset")

    b8, l22, s23 = "2026-06-08", L9_ITEM[0], "2026-06-23"
    after_wet, after_ok = closest_after(wet[l22], ok[l22], wet[s23], ok[s23])
    after_ws, _ = closest_after(wet_strict[l22], ok[l22], wet_strict[s23], ok[s23])
    labels = {
        "label": bracket_label(wet[b8], after_wet, ok[b8], after_ok),            # rule v2 (main)
        "label_v1": bracket_label(wet[b8], wet[s23], ok[b8], ok[s23]),         # first run (8 + 23 Jun)
        "label_strict": bracket_label(wet_strict[b8], after_ws, ok[b8], after_ok),
    }
    unet, unet_seen = _unet_water(transform, crs, shape)
    for k, p in enumerate(pts):
        p["nisar"] = int(p["stratum"] in "AB")
        p["s1"] = int(p["stratum"] in "AC")
        p["unet"] = int(unet[rows[k], cols[k]])
        p["unet_seen"] = int(unet_seen[rows[k], cols[k]])
        for name, lab in labels.items():
            p[name] = str(lab[k])
        for day in looks:
            p[f"wet_{day}"] = int(wet[day][k]) if ok[day][k] else ""
    with (out / "reference.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(pts[0]))
        w.writeheader()
        w.writerows(pts)

    weights = strata_info["weights"]
    rice_ha = strata_info["rice_ha_scored"]
    # the U-Net map's water inside the rice, from the sample (it is not one of the strata)
    unet_ha = round(rice_ha * sum(weights[s] * float(np.mean([p["unet"] for p in pts if p["stratum"] == s])) for s in "ABCD"))
    unet_rice_px_ha = round(float((unet & _grid(data)[0]).sum()) * 0.04)
    r3 = lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, 3)

    def block(label: str, with_ci: bool) -> dict:
        counts = {s: {lab: sum(1 for p in pts if p["stratum"] == s and p[label] == lab) for lab in ("wet", "dry", "unclear")} for s in STRATA}
        res = {"counts": counts, "b_wet_share": r3(stratum_wet_share(pts, "B", label)),
               "control_E_wet_share": r3(stratum_wet_share(pts, "E", label))}
        for k in MAPS:
            m = map_accuracy(pts, weights, k, label)
            lo = map_accuracy(pts, weights, k, label, unclear_as="dry")
            hi = map_accuracy(pts, weights, k, label, unclear_as="wet")
            res[k] = {"user": r3(m["user"]), "producer": r3(m["producer"]),
                      "bounds_unclear_all_dry": {"user": r3(lo["user"]), "producer": r3(lo["producer"])},
                      "bounds_unclear_all_wet": {"user": r3(hi["user"]), "producer": r3(hi["producer"])}}
        res["map_ha"] = {"nisar": strata_info["nisar_water_ha"], "s1": strata_info["s1_water_ha"], "unet_estimated": unet_ha}
        if with_ci:
            ci = bootstrap(pts, weights, label=label)
            res["ci95"] = {k: [r3(a), r3(b)] for k, (a, b) in ci.items()}
            res["verdict"] = verdict(stratum_wet_share(pts, "B", label), ci["b_user"])
        return res

    result = {
        "question": "18 Jun 2026, Albufera rice: who is right, NISAR or Sentinel-1 (and the app's U-Net map)?",
        "referee_v2": f"optical only: wet before ({b8}, Sentinel-2) AND wet after (Landsat 9 {l22}, else Sentinel-2 {s23}); "
                      "wet = (LSWI + 0.05 >= EVI) or MNDWI > 0. Unclear points are not imputed",
        "rule": RULE,
        "v2": block("label", with_ci=True),
        "v1_8_and_23_jun": block("label_v1", with_ci=False),
        "strict_mndwi_only": block("label_strict", with_ci=True),
        "unet_check": {"rice_ha_all_pixels": unet_rice_px_ha, "rice_ha_from_sample": unet_ha,
                       "frame": UNET_FRAME.name, "note": "decoded from the baked web frame (all water = open + flooded vegetation)"},
        "stratum_ha": strata_info["stratum_ha"],
        "rice_ha_scored": rice_ha,
        "optical_sanity": sanity,
        "limits": ["optical misses water under a closed canopy: the referee is biased against NISAR",
                   "wet before and after cannot see a drainage of a few days around 18 Jun (eixugo)",
                   "wet mud can trip both the flooding index and NISAR's dark threshold (see strict_mndwi_only)",
                   "DSWx-S1 maps inundated vegetation (class 3) only where its land cover says wetland, so 2 % is the product, not raw C-band"],
    }
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


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
