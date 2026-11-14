"""Score CV water and burn maps on real data, against labels the models never see.

    python -m pipeline.cv.evaluate                                   # baseline -> data/metrics/cv_baseline.json
    python -m pipeline.cv.evaluate --model data/models/cv_unet.pt    # U-Net vs baseline -> data/metrics/cv_unet.json

Checks:

1. Water, per acquisition, vs the same-day Sentinel-1 water map (OPERA DSWx-S1),
   only where that map is at most MAX_GAP_H hours from the NISAR pass. Scored
   twice: against open water only, and against open water plus inundated
   vegetation (what the U-Net is trained on, keys prefixed any_). Scored on dynamic water: the sea and permanent water (WorldCover
   water, or JRC occurrence of 90 % or more) are left out, because they are easy
   and would inflate the score. Also reported: how much of the map's "inundated
   vegetation" a model finds (L-band sees flooded vegetation bright, not dark).
2. The DANA "Adam" flood at Pego-Oliva (track 066 D, 16 Oct before, 28 Oct after)
   vs the Copernicus EMS EMSR935 outline (imagery 20 to 21 Oct), scored inside the
   official mapped areas. Flood traces (no water left to see) and permanent water
   are left out. The label is 7 days older than the NISAR pass, so it is an upper
   bound on the water that was still there.
3. Baseline only: the Serra d'Espadà burn, HV drop from the last date before
   ignition (25 Jul) to each later date vs the EFFIS burnt area, in a 2 km band.

With --model, the U-Net and the baseline are scored on exactly the same pixels:
on the training site only inside the held-out validation blocks, on the other
site everywhere (it is the test site; the model never saw it).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr

from pipeline.config import DATA_DIR, DSWX_LABEL_SITES, RAW_DIR, STACK_DIR, STACKS, get_site
from pipeline.cv.baseline import BURN_DROP_DB, area_ha, burn_candidate, otsu_threshold_db, water_mask
from pipeline.cv.data import boxcar_power, dswx_on_grid, open_stack, rasterize_on, to_db
from pipeline.cv.metrics import confusion, scores

LABELS_DIR = DATA_DIR / "labels"
CONTEXT_DIR = DATA_DIR / "context"
METRICS_DIR = DATA_DIR / "metrics"
DSWX_RAW = RAW_DIR / "dswx"

MAX_GAP_H = 2.0            # same Sentinel-1 pass time as NISAR, within the hour or so
PERMANENT_OCCURRENCE = 90  # JRC: water at least 90 % of the time since 1984
WORLDCOVER_WATER = 80
DSWX_OPEN_WATER, DSWX_INUNDATED_VEG = 1, 3
DSWX_INVALID = (250, 251, 255)

FLOOD = {"site": "pego_oliva", "stack": "066_D_069", "before": "2026-10-16", "after": "2026-10-28"}
BURN = {"site": "espada", "ignition": "2026-07-25", "band_m": 2000.0}

# A predictor maps (stack, time index) to (water mask, usable pixels, extra info for the report).
Predictor = Callable[[xr.Dataset, int], tuple[np.ndarray, np.ndarray, dict]]


def date_index(ds: xr.Dataset) -> dict[str, int]:
    """YYYY-MM-DD of each acquisition -> its position in the stack."""
    return {str(t)[:10]: i for i, t in enumerate(ds["time"].values)}


def permanent_water(ds: xr.Dataset, site: str) -> np.ndarray:
    """Sea and permanent water on the stack grid (from the committed 20 m context layers)."""
    out = None
    for name in (f"{site}_worldcover_2021_20m.tif", f"{site}_jrc_occurrence_20m.tif"):
        with rasterio.open(CONTEXT_DIR / name) as src:
            if src.transform != ds["HH"].rio.transform() or (src.height, src.width) != (ds.sizes["y"], ds.sizes["x"]):
                raise ValueError(f"{name} is not on the stack grid: rerun python -m pipeline.context")
            band = src.read(1)
        part = band == WORLDCOVER_WATER if "worldcover" in name else (band >= PERMANENT_OCCURRENCE) & (band != 255)
        out = part if out is None else out | part
    return out


def scene_db(power: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Speckle-filtered dB image and the pixels that are usable in it."""
    db = to_db(boxcar_power(power, valid))
    return db, valid.astype(bool) & np.isfinite(db)


def baseline_water(ds: xr.Dataset, t: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Otsu water mask of one acquisition, its usable pixels and the threshold (dB)."""
    hh_db, ok = scene_db(ds["HH"].values[t], ds["valid"].values[t])
    threshold = otsu_threshold_db(hh_db, ok)
    return water_mask(hh_db, ok, threshold), ok, threshold


def baseline_predictor(ds: xr.Dataset, t: int) -> tuple[np.ndarray, np.ndarray, dict]:
    pred, ok, threshold = baseline_water(ds, t)
    return pred, ok, {"threshold_db": round(threshold, 2)}


def unet_predictor(model_path: str | Path, threshold: float = 0.5) -> Predictor:
    """Predictor backed by a trained U-Net checkpoint (needs the cv extra: torch)."""
    from pipeline.cv.dataset import scene_arrays
    from pipeline.cv.predict import load_model, predict_scene

    model, mean, std, checkpoint = load_model(model_path)

    def predict(ds: xr.Dataset, t: int) -> tuple[np.ndarray, np.ndarray, dict]:
        x, _ = scene_arrays(ds, t)
        prob = predict_scene(model, x, mean, std, tile=checkpoint["config"]["tile"])
        ok = np.isfinite(prob)
        return ok & (prob >= threshold), ok, {}

    predict.checkpoint = checkpoint  # type: ignore[attr-defined]
    return predict


def dswx_files(entry: dict) -> list[Path]:
    """Label tiles of one index entry (paths may use either slash style)."""
    return [DSWX_RAW / Path(f.replace("\\", "/")) for f in entry.get("files") or []]


def water_vs_dswx(site: str, stack_id: str, predictor: Predictor = baseline_predictor,
                  region: np.ndarray | None = None) -> list[dict]:
    """Per-date scores of a predictor vs same-day DSWx-S1 open water, on dynamic water (and region)."""
    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    perm = permanent_water(ds, site)
    index = {(e["stack_id"], e["date"]): e
             for e in json.loads((DSWX_RAW / site / "index.json").read_text(encoding="utf-8"))}
    rows = []
    for day, t in date_index(ds).items():
        entry = index.get((stack_id, day))
        if not entry or not dswx_files(entry):
            continue
        row = {"site": site, "stack": stack_id, "date": day, "gap_h": entry["hours_from_nisar"]}
        if entry["hours_from_nisar"] is None or entry["hours_from_nisar"] > MAX_GAP_H:
            rows.append({**row, "skipped": f"label is {entry['hours_from_nisar']} h from NISAR"})
            continue
        dswx = dswx_on_grid(ds, dswx_files(entry))
        pred, ok, info = predictor(ds, t)
        scoring = ok & ~np.isin(dswx, DSWX_INVALID) & ~perm
        if region is not None:
            scoring &= region
        if not scoring.any():
            rows.append({**row, "skipped": "no usable pixels for this model on this date"})
            continue
        truth = dswx == DSWX_OPEN_WATER
        any_water = np.isin(dswx, (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG))  # what the U-Net is trained on
        veg = scoring & (dswx == DSWX_INUNDATED_VEG)
        rows.append({
            **row, **info, "pixels": int(scoring.sum()),
            **scores(confusion(pred, truth, scoring)),
            **{f"any_{k}": v for k, v in scores(confusion(pred, any_water, scoring)).items()},
            "label_open_water_ha": round(area_ha(truth & scoring), 1),
            "pred_water_ha": round(area_ha(pred & scoring), 1),
            "inundated_veg_ha": round(area_ha(veg), 1),
            "inundated_veg_found": round(float(pred[veg].mean()), 3) if veg.any() else None,
        })
    return rows


def flood_vs_emsr935(predictor: Predictor = baseline_predictor) -> dict:
    site, stack_id = FLOOD["site"], FLOOD["stack"]
    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    days = date_index(ds)
    water_before, ok_before, info_before = predictor(ds, days[FLOOD["before"]])
    water_after, ok_after, info_after = predictor(ds, days[FLOOD["after"]])
    perm = permanent_water(ds, site)

    outlines = gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_flood.geojson")
    flooded = rasterize_on(ds, outlines[outlines["class"] == "flooded_area"]).astype(bool)
    trace = rasterize_on(ds, outlines[outlines["class"] == "flood_trace"]).astype(bool)
    mapped = rasterize_on(ds, gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_aoi.geojson")).astype(bool)
    region = mapped & ok_before & ok_after & ~perm & ~trace

    out = {
        "site": site, "stack": stack_id, "before": FLOOD["before"], "after": FLOOD["after"],
        "label": "EMSR935 flooded_area, imagery 20 to 21 Oct 2026, inside the mapped AOIs",
        "region_px": int(region.sum()), "label_ha": round(area_ha(flooded & region), 1),
        "before_info": info_before, "after_info": info_after,
    }
    for name, pred in {
        "water_after": water_after,
        "water_gain": water_after & ~water_before,
        "control_water_before": water_before,
    }.items():
        out[name] = {**scores(confusion(pred, flooded, region)), "pred_ha": round(area_ha(pred & region), 1)}

    footprint = rasterize_on(ds, gpd.read_file(LABELS_DIR / "pego_oliva_generalitat_footprint.geojson")).astype(bool)
    in_footprint = footprint & ok_before & ok_after & ~perm
    if in_footprint.any():
        out["generalitat_footprint_water_share"] = {
            "before": round(float(water_before[in_footprint].mean()), 3),
            "after": round(float(water_after[in_footprint].mean()), 3),
        }
    return out


def burn_vs_effis() -> list[dict]:
    site = BURN["site"]
    effis = gpd.read_file(LABELS_DIR / "espada_effis_burnt_area.geojson")
    rows = []
    for stack_id in STACKS[site]:
        ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
        crs = ds["HH"].rio.crs
        perm = permanent_water(ds, site)
        truth = rasterize_on(ds, effis).astype(bool)
        band = gpd.GeoDataFrame(geometry=effis.to_crs(crs).buffer(BURN["band_m"]), crs=crs)
        region = rasterize_on(ds, band).astype(bool)
        days = date_index(ds)
        pre = max(d for d in days if d < BURN["ignition"])
        hv_pre, ok_pre = scene_db(ds["HV"].values[days[pre]], ds["valid"].values[days[pre]])
        for day, t in days.items():
            if day <= BURN["ignition"]:
                continue
            hv_post, ok_post = scene_db(ds["HV"].values[t], ds["valid"].values[t])
            if not ok_post.any():
                rows.append({"stack": stack_id, "pre": pre, "post": day, "skipped": "no HV on this date (HH only)"})
                continue
            scoring = region & ok_pre & ok_post & ~perm
            pred = burn_candidate(hv_pre, hv_post, scoring)
            rows.append({
                "stack": stack_id, "pre": pre, "post": day, "pixels": int(scoring.sum()),
                **scores(confusion(pred, truth, scoring)),
                "label_ha": round(area_ha(truth & scoring), 1), "pred_ha": round(area_ha(pred & scoring), 1),
            })
    return rows


def _median(rows: list[dict], key: str) -> float | None:
    values = [r[key] for r in rows if r.get(key) is not None]
    return round(float(np.median(values)), 3) if values else None


def baseline_report() -> dict:
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Otsu water threshold on 5x5 filtered HH (dB) per scene; burn = HV drop of "
                  f"{BURN_DROP_DB} dB or more; see pipeline/cv/evaluate.py for the scoring rules",
        "water_vs_dswx": [row for site in DSWX_LABEL_SITES for stack_id in STACKS[site]
                          for row in water_vs_dswx(site, stack_id)],
        "flood_vs_emsr935": flood_vs_emsr935(),
        "burn_vs_effis": burn_vs_effis(),
    }


def model_report(model_path: Path, threshold: float) -> dict:
    """U-Net and baseline on the same pixels: validation blocks on the training site, all of the test site."""
    from pipeline.cv.dataset import blocks_mask, validation_blocks
    from pipeline.stack import site_grid

    unet = unet_predictor(model_path, threshold)
    checkpoint = unet.checkpoint  # type: ignore[attr-defined]
    cfg = checkpoint["config"]
    rows = []
    for site in DSWX_LABEL_SITES:
        region, split = None, "test site, never seen in training"
        if site == cfg["site"]:
            g = site_grid(get_site(site))
            shape = (g.height, g.width)
            # The exact held-out blocks are stored in the checkpoint (older ones: rebuild the random draw).
            region = (blocks_mask(shape, checkpoint["val_blocks"], cfg["block"]) if "val_blocks" in checkpoint
                      else validation_blocks(shape, cfg["val_share"], cfg["seed"], cfg["block"]))
            split = "held-out validation blocks of the training site"
        for stack_id in STACKS[site]:
            for name, predictor in (("baseline", baseline_predictor), ("unet", unet)):
                rows += [{**row, "model": name, "split": split} for row in water_vs_dswx(site, stack_id, predictor, region)]
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": str(model_path).replace("\\", "/"), "checkpoint_epoch": unet.checkpoint["epoch"],  # type: ignore[attr-defined]
        "train_site": cfg["site"], "probability_threshold": threshold,
        "water_vs_dswx": rows,
        "flood_vs_emsr935": {"baseline": flood_vs_emsr935(baseline_predictor), "unet": flood_vs_emsr935(unet)},
    }


def print_baseline(report: dict) -> None:
    print("1) Water vs same-day Sentinel-1 (dynamic water only)")
    for site in DSWX_LABEL_SITES:
        for stack_id in STACKS[site]:
            rows = [r for r in report["water_vs_dswx"] if r["site"] == site and r["stack"] == stack_id]
            scored = [r for r in rows if "skipped" not in r]
            print(f"   {site} {stack_id}: {len(scored)} of {len(rows)} dates scored, median IoU {_median(scored, 'iou')}, "
                  f"F1 {_median(scored, 'f1')}, precision {_median(scored, 'precision')}, recall {_median(scored, 'recall')}, "
                  f"inundated vegetation found {_median(scored, 'inundated_veg_found')}")
    f = report["flood_vs_emsr935"]
    print(f"2) DANA flood vs EMSR935 ({f['label_ha']} ha labelled inside the mapped areas)")
    for name in ("water_after", "water_gain", "control_water_before"):
        s = f[name]
        print(f"   {name}: IoU {s['iou']}, F1 {s['f1']}, precision {s['precision']}, recall {s['recall']}, {s['pred_ha']} ha")
    print("3) Espadà burn vs EFFIS (2 km band)")
    for r in report["burn_vs_effis"]:
        if "skipped" in r:
            print(f"   {r['stack']} {r['pre']} -> {r['post']}: skipped, {r['skipped']}")
        else:
            print(f"   {r['stack']} {r['pre']} -> {r['post']}: IoU {r['iou']}, F1 {r['f1']}, "
                  f"precision {r['precision']}, recall {r['recall']}")


def print_comparison(report: dict) -> None:
    print("1) Water vs same-day Sentinel-1, dynamic water, same pixels for both (median over dates both scored)")
    keys = sorted({(r["site"], r["stack"], r["split"]) for r in report["water_vs_dswx"]})
    for site, stack_id, split in keys:
        pick = {m: {r["date"]: r for r in report["water_vs_dswx"]
                    if (r["site"], r["stack"], r["model"]) == (site, stack_id, m) and r.get("iou") is not None}
                for m in ("baseline", "unet")}
        dates = sorted(set(pick["baseline"]) & set(pick["unet"]))

        def line(keys: tuple[str, ...]) -> str:
            return ", ".join(f"{k} {_median([pick['baseline'][d] for d in dates], k)} -> "
                             f"{_median([pick['unet'][d] for d in dates], k)}" for k in keys)

        print(f"   {site} {stack_id} [{split}], {len(dates)} dates")
        print(f"      open water:          {line(('iou', 'f1', 'precision', 'recall'))}")
        print(f"      open + flooded veg.: {line(('any_iou', 'any_f1', 'any_precision', 'any_recall'))}")
    print("2) DANA flood vs EMSR935 (baseline -> U-Net)")
    flood = report["flood_vs_emsr935"]
    for name in ("water_after", "water_gain", "control_water_before"):
        b, u = flood["baseline"][name], flood["unet"][name]
        print(f"   {name}: " + ", ".join(f"{k} {b[k]} -> {u[k]}" for k in ("iou", "f1", "precision", "recall"))
              + f", {b['pred_ha']} -> {u['pred_ha']} ha (label {flood['unet']['label_ha']} ha)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, help="U-Net checkpoint to score against the baseline")
    parser.add_argument("--threshold", type=float, default=0.5, help="water probability threshold for the U-Net")
    args = parser.parse_args()
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    if args.model:
        report = model_report(args.model, args.threshold)
        path = METRICS_DIR / "cv_unet.json"
        print_comparison(report)
    else:
        report = baseline_report()
        path = METRICS_DIR / "cv_baseline.json"
        print_baseline(report)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
