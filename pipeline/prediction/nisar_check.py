"""NISAR check of the prediction inputs: does L-band see what the forecasts are built on?

The forecasts run on Sentinel-1 water maps (OPERA DSWx-S1), because NISAR over
Spain only starts in Jun 2026. "NISAR stays first" (discussion #9) means NISAR
is the check. Two checks, both with the CV baseline that is on main
(pipeline.cv.baseline: Otsu threshold per scene on 5x5-filtered HH in dB):

1. Albufera rice fields, track 066 D (11 dates, 18 Jun to 28 Oct 2026): the
   share of the rice mask that NISAR sees dark (filtered HH below a FIXED
   threshold, -15 dB as in pipeline.ml's fallback, and -18 dB) vs the share
   DSWx-S1 maps as flooded on the nearest pass on the same or next day, with
   non-rice cropland as a control. The per-scene Otsu threshold is reported
   too, but it follows the whole scene (sea, towns) and swung from -7.5 to
   -11.3 dB between dates, calling about 90 % of the rice "water" in June and
   September, so it is not used for the comparison.
2. DANA "Adam" at Pego-Oliva, track 066 D, 16 Oct (before) and 28 Oct (after):
   new NISAR water inside the EMSR935 mapped areas, the share of it inside the
   official flood outline, and the DSWx-S1 change on the nearest passes.

The baseline over-maps water (precision about 0.2 against DSWx-S1 in
data/metrics/cv_baseline.json), so the hectares are not truth; the questions are
"does NISAR rise and fall with DSWx" and "where does new NISAR water appear".

Usage:
    python -m pipeline.nisar_fetch --site albufera --stack 066_D_069      # Earthdata login
    python -m pipeline.stack --site albufera --stack 066_D_069
    (same for pego_oliva)
    python -m pipeline.prediction.nisar_check

Writes data/prediction/nisar_check.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path

import numpy as np

from pipeline.config import DATA_DIR, REPO_ROOT, STACK_DIR

STACK_ID = "066_D_069"
OUT = DATA_DIR / "prediction" / "nisar_check.json"
DELTAS_DB = (-1.0, 0.0, 1.0)
FIXED_DB = (-15.0, -18.0)
AUTUMN_FROM = "2026-10-01"   # the winter flooding the Albufera forecast predicts
MAX_DAY_GAP = 1


def water_ha(hh_db: np.ndarray, valid: np.ndarray, region: np.ndarray, threshold_db: float) -> float:
    from pipeline.cv.baseline import area_ha, water_mask
    return area_ha(water_mask(hh_db, valid, threshold_db) & region)


def scene_db(ds, i: int):
    """Filtered HH in dB, validity, and the scene's Otsu threshold, for time index i."""
    from pipeline.cv.baseline import otsu_threshold_db
    from pipeline.cv.data import boxcar_power, to_db
    valid = ds["valid"].values[i].astype(bool)
    hh = to_db(boxcar_power(ds["HH"].values[i], valid))
    ok = valid & np.isfinite(hh)
    return hh, ok, otsu_threshold_db(hh, ok)


def nearest_pass(day: date, rows: list[dict], key: str) -> dict | None:
    """The usable DSWx-S1 row on the same day or within MAX_DAY_GAP days after (prefer same day)."""
    best = None
    for r in rows:
        if str(r.get("usable")) != "True":
            continue
        gap = (date.fromisoformat(r["date"]) - day).days
        if 0 <= gap <= MAX_DAY_GAP and (best is None or gap < best[0]):
            best = (gap, r)
    if best is None:
        return None
    vals = [float(r[key]) for r in rows if r["date"] == best[1]["date"] and str(r.get("usable")) == "True"]
    return {"date": best[1]["date"], "day_gap": best[0], "value": float(np.mean(vals))}


def pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return round(float(np.corrcoef(a, b)[0, 1]), 3)


def check_albufera(stack_path: Path) -> dict:
    import rasterio
    from pipeline.cv.data import open_stack
    from pipeline.prediction.albufera.mask import load as load_mask

    ds = open_stack(stack_path)
    rice, grid = load_mask(DATA_DIR / "prediction" / "albufera" / "rice_mask.tif")
    if rice.shape != (ds.sizes["y"], ds.sizes["x"]):
        raise ValueError("Rice mask and stack are not on the same grid")
    mask_ha = float(rice.sum()) * 0.04
    with rasterio.open(DATA_DIR / "context" / "albufera_worldcover_2021_20m.tif") as src:
        control = (src.read(1) == 40) & ~rice   # non-rice cropland
    rows = list(csv.DictReader((DATA_DIR / "prediction" / "albufera" / "water_area.csv").open(encoding="utf-8")))
    for r in rows:
        if r["flooded_share_of_observed"] not in ("", None):
            r["flooded_est_ha"] = float(r["flooded_share_of_observed"]) * mask_ha
    out = []
    for i, t in enumerate(ds["time"].values):
        day = date.fromisoformat(str(t)[:10])
        hh, ok, thr = scene_db(ds, i)
        observed = float((ok & rice).sum()) / float(rice.sum())
        r_ok, c_ok = ok & rice, ok & control
        dark = {f"{t:.0f}": round(100 * float(np.mean(hh[r_ok] < t)), 1) for t in FIXED_DB}
        dark_control = {f"{t:.0f}": round(100 * float(np.mean(hh[c_ok] < t)), 1) for t in FIXED_DB}
        otsu = {f"{d:+.0f}": round(water_ha(hh, ok, rice, thr + d), 1) for d in DELTAS_DB}
        dswx = nearest_pass(day, [r for r in rows if "flooded_est_ha" in r], "flooded_est_ha")
        out.append({"date": day.isoformat(), "crid": str(ds["crid"].values[i]) if "crid" in ds else None,
                    "rice_observed_fraction": round(observed, 4),
                    "nisar_dark_pct": dark, "control_cropland_dark_pct": dark_control,
                    "median_hh_db": {"rice": round(float(np.median(hh[r_ok])), 2),
                                     "control": round(float(np.median(hh[c_ok])), 2)},
                    "otsu": {"threshold_db": round(thr, 2), "water_ha": otsu},
                    "dswx": None if dswx is None else
                    {"date": dswx["date"], "day_gap": dswx["day_gap"],
                     "flooded_pct": round(100 * dswx["value"] / mask_ha, 1)}})
    paired = [o for o in out if o["dswx"] and o["rice_observed_fraction"] >= 0.9]
    autumn = [o for o in paired if o["date"] >= AUTUMN_FROM]
    corr = lambda sel, key: pearson([o["nisar_dark_pct"][key] for o in sel], [o["dswx"]["flooded_pct"] for o in sel])
    return {"site": "albufera", "stack": STACK_ID, "rice_mask_ha": round(mask_ha, 1), "dates": out,
            "paired_dates": len(paired),
            "pearson_r_all_dates": {"-15": corr(paired, "-15"), "-18": corr(paired, "-18"),
                                    "otsu": pearson([o["otsu"]["water_ha"]["+0"] for o in paired],
                                                    [o["dswx"]["flooded_pct"] for o in paired])},
            "autumn": {"dates": [o["date"] for o in autumn],
                       "nisar_dark_pct_-15": [o["nisar_dark_pct"]["-15"] for o in autumn],
                       "dswx_flooded_pct": [o["dswx"]["flooded_pct"] for o in autumn],
                       "pearson_r_-15": corr(autumn, "-15") if len(autumn) >= 5 else None,
                       "note": "too few autumn dates for a correlation; compare the two series directly"},
            "reading": "Autumn (the winter flooding the forecast predicts): NISAR and DSWx-S1 rise together. "
                       "June: NISAR sees up to 44 % of the rice dark while DSWx-S1 sees about 2 %; the rice "
                       "calendar has the paddies flooded from May sowing to the August drainage, so L-band may "
                       "see water among young rice that the C-band map misses. Not confirmed on the ground."}


def check_dana(stack_path: Path, before: str = "2026-10-16", after: str = "2026-10-28") -> dict:
    import geopandas as gpd
    from pipeline.cv.baseline import area_ha, water_mask
    from pipeline.cv.data import open_stack, rasterize_on
    import rasterio

    ds = open_stack(stack_path)
    days = [str(t)[:10] for t in ds["time"].values]
    ib, ia = days.index(before), days.index(after)
    hb, okb, tb = scene_db(ds, ib)
    ha, oka, ta = scene_db(ds, ia)
    labels = DATA_DIR / "labels"
    aoi = rasterize_on(ds, gpd.read_file(labels / "pego_oliva_emsr935_aoi.geojson"))
    flood = gpd.read_file(labels / "pego_oliva_emsr935_flood.geojson")
    # Same rule as pipeline.cv.evaluate: flood traces (no water left to see) leave the scoring region.
    outline = rasterize_on(ds, flood[flood["class"] == "flooded_area"]).astype(bool)
    trace = rasterize_on(ds, flood[flood["class"] == "flood_trace"]).astype(bool)
    with rasterio.open(DATA_DIR / "context" / "pego_oliva_jrc_occurrence_20m.tif") as src:
        jrc = src.read(1)
    with rasterio.open(DATA_DIR / "context" / "pego_oliva_sea_20m.tif") as src:
        sea = src.read(1) == 1
    region = aoi.astype(bool) & ~sea & ~((jrc >= 90) & (jrc != 255)) & ~trace
    both = okb & oka & region
    res = {}
    for d in DELTAS_DB:
        new = water_mask(ha, oka, ta + d) & ~water_mask(hb, okb, tb + d) & both
        res[f"{d:+.0f}"] = {"new_water_ha": round(area_ha(new), 1),
                            "inside_outline_ha": round(area_ha(new & outline), 1),
                            "share_inside_outline": round(float((new & outline).sum()) / max(1, int(new.sum())), 3)}
    rows = list(csv.DictReader((DATA_DIR / "prediction" / "flood" / "water_pego_oliva.csv").open(encoding="utf-8")))
    d_b = nearest_pass(date.fromisoformat(before), rows, "flooded_in_emsr935_ha")
    d_a = nearest_pass(date.fromisoformat(after), rows, "flooded_in_emsr935_ha")
    return {"site": "pego_oliva", "stack": STACK_ID, "before": before, "after": after,
            "thresholds_db": {"before": round(tb, 2), "after": round(ta, 2)},
            "outline_ha_scored": round(area_ha(outline & both), 1),
            "nisar_new_water": res,
            "dswx_in_emsr935_outline_ha": {"before": d_b, "after": d_a},
            "note": "EMSR935 imagery is from 20 Oct; NISAR 28 Oct is 9 days after the peak, so part of the water had drained."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    result = {"issued_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "method": "pipeline.cv.baseline: Otsu per scene on 5x5-filtered HH (dB); +-1 dB threshold range"}
    for key, site, fn in (("albufera_rice", "albufera", check_albufera), ("pego_oliva_dana", "pego_oliva", check_dana)):
        path = STACK_DIR / f"{site}_{STACK_ID}.nc"
        result[key] = fn(path) if path.exists() else {"status": f"missing {path.relative_to(REPO_ROOT)}"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    a = result["albufera_rice"]
    if "dates" in a:
        print(f"Albufera rice ({a['paired_dates']} paired dates): r all dates {a['pearson_r_all_dates']}, "
              f"autumn r {a['autumn']['pearson_r_-15']}")
        for o in a["dates"]:
            print(f"  {o['date']} NISAR dark {o['nisar_dark_pct']['-15']:>5} %  control {o['control_cropland_dark_pct']['-15']:>4} %  "
                  f"DSWx {o['dswx']['flooded_pct'] if o['dswx'] else '-':>5} %")
    p = result["pego_oliva_dana"]
    if "nisar_new_water" in p:
        print(f"Pego-Oliva DANA {p['before']} -> {p['after']}: {p['nisar_new_water']}")
        print(f"  DSWx in outline: {p['dswx_in_emsr935_outline_ha']}")
    print(f"-> {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
