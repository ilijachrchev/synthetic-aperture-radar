"""Score CV water and burn maps on real data, against labels the models never see.

    python -m pipeline.cv.evaluate                                         # baseline -> data/metrics/cv_baseline.json
    python -m pipeline.cv.evaluate --model data/models/cv_unet.pt          # U-Net vs baseline -> data/metrics/cv_unet.json
    python -m pipeline.cv.evaluate --model data/models/X.pt --val-only     # training-site validation blocks only
    python -m pipeline.cv.evaluate --model data/models/X.pt --sweep 0.3,0.4,0.5  # pick the threshold on them
    python -m pipeline.cv.evaluate --model X.pt --sites pego_oliva donana  # score these sites too

Checks:

1. Water, per acquisition, vs the same-day Sentinel-1 water map (OPERA DSWx-S1),
   only where that map is at most MAX_GAP_H hours from the NISAR pass. Scored
   twice: against open water only, and against open water plus inundated
   vegetation (keys prefixed any_). Scored on dynamic water: the sea and
   permanent water (WorldCover water, or JRC occurrence of 90 % or more) are left
   out, because they are easy and would inflate the score. Also reported: how
   much of the map's "inundated vegetation" a model finds (L-band sees flooded
   vegetation bright, not dark).
2. The DANA "Adam" flood at Pego-Oliva vs the Copernicus EMS EMSR935 outline
   (imagery 20 to 21 Oct), scored inside the official mapped areas, with flood
   traces (no water left to see) and permanent water left out. Two NISAR pairs
   (FLOODS): track 066 D, 16 Oct before and 28 Oct after (7 days after the
   imagery, so the label is an upper bound on the water still there), and track
   167 D, 11 Oct before and 23 Oct after (2 to 3 days after the imagery; that
   frame covers about 63 % of the site box, so it is an extra test stack only).
3. Baseline only: the Serra d'Espadà burn, HV drop from the last date before
   ignition (25 Jul) to each later date vs the EFFIS burnt area, in a 2 km band.

With --model, the U-Net and the baseline are scored on exactly the same pixels:
on each training site only inside its held-out validation blocks, on every other
site everywhere (a test site; the model never saw it). Model variants are chosen
with --val-only and --sweep, which never touch a test site.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr

from pipeline.config import DATA_DIR, DSWX_LABEL_SITES, RAW_DIR, STACK_DIR, get_site, site_stacks
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

FLOODS = [
    {"site": "pego_oliva", "stack": "066_D_069", "before": "2026-10-16", "after": "2026-10-28"},
    {"site": "pego_oliva", "stack": "167_D_069", "before": "2026-10-11", "after": "2026-10-23"},
]
FLOOD = FLOODS[0]
# Test-site stacks that cover only part of the site box (not shared STACKS); scored when built.
EXTRA_TEST_STACKS = {"pego_oliva": ("167_D_069",)}
BURN = {"site": "espada", "ignition": "2026-07-25", "band_m": 2000.0}

# A predictor maps (stack, time index) to (water mask, usable pixels, extra info for the report).
# The mask is one array, or {"open": ..., "any": ...} for models that tell flooded vegetation apart.
Predictor = Callable[[xr.Dataset, int], tuple[np.ndarray | dict[str, np.ndarray], np.ndarray, dict]]


def date_index(ds: xr.Dataset) -> dict[str, int]:
    """YYYY-MM-DD of each acquisition -> its position in the stack."""
    return {str(t)[:10]: i for i, t in enumerate(ds["time"].values)}


def _permanent_on(site: str, transform, shape: tuple[int, int]) -> np.ndarray:
    out = None
    for name in (f"{site}_worldcover_2021_20m.tif", f"{site}_jrc_occurrence_20m.tif"):
        with rasterio.open(CONTEXT_DIR / name) as src:
            if src.transform != transform or (src.height, src.width) != shape:
                raise ValueError(f"{name} is not on the stack grid: rerun python -m pipeline.context")
            band = src.read(1)
        part = band == WORLDCOVER_WATER if "worldcover" in name else (band >= PERMANENT_OCCURRENCE) & (band != 255)
        out = part if out is None else out | part
    return out


def permanent_water(ds: xr.Dataset, site: str) -> np.ndarray:
    """Sea and permanent water on the stack grid (from the committed 20 m context layers)."""
    return _permanent_on(site, ds["HH"].rio.transform(), (ds.sizes["y"], ds.sizes["x"]))


def site_permanent_water(site: str) -> np.ndarray:
    """permanent_water on the site grid, without opening a stack."""
    from pipeline.stack import site_grid

    g = site_grid(get_site(site))
    return _permanent_on(site, g.transform, (g.height, g.width))


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


def unet_predictor(model_path: str | Path, threshold: float = 0.5, use_coherence: bool = True) -> Predictor:
    """Predictor backed by a trained U-Net checkpoint (needs the cv extra: torch).

    The returned function also carries .checkpoint and .probabilities(ds, t),
    which gives the (open water, any water) probability maps. use_coherence=False
    withholds coherence from a "+coh" model, as on a date with no pair.
    """
    from pipeline.cv.coherence import coherence_for
    from pipeline.cv.dataset import reference_db, scene_arrays, uses_coherence, uses_reference
    from pipeline.cv.predict import load_model, model_spec, predict_scene, water_probabilities

    model, mean, std, checkpoint = load_model(model_path)
    inputs = model_spec(checkpoint["config"])[0]
    references: dict[tuple[str, str], np.ndarray] = {}

    def probabilities(ds: xr.Dataset, t: int) -> tuple[np.ndarray, np.ndarray]:
        reference, coherence = None, None
        key = (str(ds.attrs.get("site")), str(ds.attrs.get("stack_id")))
        if uses_reference(inputs):
            if key not in references:
                references[key] = reference_db(ds)
            reference = references[key]
        if uses_coherence(inputs):
            shape = (ds.sizes["y"], ds.sizes["x"])
            coherence = (coherence_for(key[0], key[1], str(ds["time"].values[t])[:10], shape) if use_coherence
                         else np.full(shape, np.nan, dtype="float32"))
        x, _ = scene_arrays(ds, t, reference=reference, coherence=coherence)
        return water_probabilities(predict_scene(model, x, mean, std, tile=checkpoint["config"]["tile"]))

    def predict(ds: xr.Dataset, t: int) -> tuple[dict[str, np.ndarray], np.ndarray, dict]:
        p_open, p_any = probabilities(ds, t)
        ok = np.isfinite(p_open)
        return {"open": ok & (p_open >= threshold), "any": ok & (p_any >= threshold)}, ok, {}

    predict.checkpoint = checkpoint  # type: ignore[attr-defined]
    predict.probabilities = probabilities  # type: ignore[attr-defined]
    return predict


def ensemble_predictor(model_paths: list[Path], threshold: float = 0.5, use_coherence: bool = True) -> Predictor:
    """Mean of several U-Nets' (open, any) water probabilities.

    All members must come from the same training site and validation blocks,
    otherwise one member's training pixels would be scored as held out.
    """
    members = [unet_predictor(p, threshold, use_coherence) for p in model_paths]
    first = members[0].checkpoint  # type: ignore[attr-defined]
    for member, path in zip(members[1:], model_paths[1:]):
        other = member.checkpoint  # type: ignore[attr-defined]
        if train_sites_of(other) != train_sites_of(first) or other.get("val_blocks") != first.get("val_blocks"):
            raise ValueError(f"{path} was validated on other blocks than {model_paths[0]}; the scores would leak")

    def probabilities(ds: xr.Dataset, t: int) -> tuple[np.ndarray, np.ndarray]:
        parts = [m.probabilities(ds, t) for m in members]  # type: ignore[attr-defined]
        return np.mean([p[0] for p in parts], axis=0), np.mean([p[1] for p in parts], axis=0)

    def predict(ds: xr.Dataset, t: int) -> tuple[dict[str, np.ndarray], np.ndarray, dict]:
        p_open, p_any = probabilities(ds, t)
        ok = np.isfinite(p_open)
        return {"open": ok & (p_open >= threshold), "any": ok & (p_any >= threshold)}, ok, {}

    predict.checkpoint = first  # type: ignore[attr-defined]
    predict.probabilities = probabilities  # type: ignore[attr-defined]
    predict.members = [str(p).replace("\\", "/") for p in model_paths]  # type: ignore[attr-defined]
    return predict


def load_predictor(model_paths: list[Path], threshold: float = 0.5, use_coherence: bool = True) -> Predictor:
    """One checkpoint, or the ensemble of several."""
    if len(model_paths) == 1:
        return unet_predictor(model_paths[0], threshold, use_coherence)
    return ensemble_predictor(model_paths, threshold, use_coherence)


def masks(pred: np.ndarray | dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """(open water, any water) masks of a prediction; a single mask counts for both."""
    return (pred["open"], pred["any"]) if isinstance(pred, dict) else (pred, pred)


def dswx_files(entry: dict) -> list[Path]:
    """Label tiles of one index entry (paths may use either slash style)."""
    return [DSWX_RAW / Path(f.replace("\\", "/")) for f in entry.get("files") or []]


def labelled_dates(site: str, stack_id: str) -> Iterator[tuple[xr.Dataset, str, int, dict, np.ndarray | None, np.ndarray]]:
    """(stack, date, time index, index entry, same-day DSWx on the grid or None if too far in time, permanent water)."""
    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    perm = permanent_water(ds, site)
    index = {(e["stack_id"], e["date"]): e
             for e in json.loads((DSWX_RAW / site / "index.json").read_text(encoding="utf-8"))}
    for day, t in date_index(ds).items():
        entry = index.get((stack_id, day))
        if not entry or not dswx_files(entry):
            continue
        close = entry["hours_from_nisar"] is not None and entry["hours_from_nisar"] <= MAX_GAP_H
        yield ds, day, t, entry, (dswx_on_grid(ds, dswx_files(entry)) if close else None), perm


def water_vs_dswx(site: str, stack_id: str, predictor: Predictor = baseline_predictor,
                  region: np.ndarray | None = None) -> list[dict]:
    """Per-date scores of a predictor vs same-day DSWx-S1 open water, on dynamic water (and region)."""
    rows = []
    for ds, day, t, entry, dswx, perm in labelled_dates(site, stack_id):
        row = {"site": site, "stack": stack_id, "date": day, "gap_h": entry["hours_from_nisar"]}
        if dswx is None:
            rows.append({**row, "skipped": f"label is {entry['hours_from_nisar']} h from NISAR"})
            continue
        pred, ok, info = predictor(ds, t)
        pred_open, pred_any = masks(pred)
        scoring = ok & ~np.isin(dswx, DSWX_INVALID) & ~perm
        if region is not None:
            scoring &= region
        if not scoring.any():
            rows.append({**row, "skipped": "no usable pixels for this model on this date"})
            continue
        truth = dswx == DSWX_OPEN_WATER
        any_water = np.isin(dswx, (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG))
        veg = scoring & (dswx == DSWX_INUNDATED_VEG)
        c_open, c_any = confusion(pred_open, truth, scoring), confusion(pred_any, any_water, scoring)
        rows.append({
            **row, **info, "pixels": int(scoring.sum()),
            **scores(c_open),
            **{f"any_{k}": v for k, v in scores(c_any).items()},
            # counts, so dates can be pooled and resampled later
            "tp": c_open["tp"], "fp": c_open["fp"], "fn": c_open["fn"],
            "any_tp": c_any["tp"], "any_fp": c_any["fp"], "any_fn": c_any["fn"],
            "label_open_water_ha": round(area_ha(truth & scoring), 1),
            "pred_water_ha": round(area_ha(pred_open & scoring), 1),
            "inundated_veg_ha": round(area_ha(veg), 1),
            "inundated_veg_found": round(float(pred_any[veg].mean()), 3) if veg.any() else None,
        })
    return rows


def flood_vs_emsr935(predictor: Predictor = baseline_predictor, check: dict = FLOOD) -> dict:
    """One NISAR before/after pair vs the EMSR935 flood outline; water = open water plus flooded vegetation."""
    site, stack_id = check["site"], check["stack"]
    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    days = date_index(ds)
    pred_before, ok_before, info_before = predictor(ds, days[check["before"]])
    pred_after, ok_after, info_after = predictor(ds, days[check["after"]])
    water_before, water_after = masks(pred_before)[1], masks(pred_after)[1]
    perm = permanent_water(ds, site)

    outlines = gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_flood.geojson")
    flooded = rasterize_on(ds, outlines[outlines["class"] == "flooded_area"]).astype(bool)
    trace = rasterize_on(ds, outlines[outlines["class"] == "flood_trace"]).astype(bool)
    mapped = rasterize_on(ds, gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_aoi.geojson")).astype(bool)
    region = mapped & ok_before & ok_after & ~perm & ~trace

    out = {
        "site": site, "stack": stack_id, "before": check["before"], "after": check["after"],
        "label": "EMSR935 flooded_area, imagery 20 to 21 Oct 2026, inside the mapped AOIs",
        "region_px": int(region.sum()), "label_ha": round(area_ha(flooded & region), 1),
        "label_ha_in_mapped_areas": round(area_ha(flooded & mapped & ~perm & ~trace), 1),
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
    for stack_id in site_stacks(site):
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
        "water_vs_dswx": [row for site in DSWX_LABEL_SITES for stack_id in site_stacks(site)
                          for row in water_vs_dswx(site, stack_id)],
        "flood_vs_emsr935": flood_vs_emsr935(),
        "burn_vs_effis": burn_vs_effis(),
    }


def train_sites_of(checkpoint: dict) -> list[str]:
    """Training sites of a checkpoint (older ones: the single config site)."""
    cfg = checkpoint["config"]
    return list(checkpoint.get("train_sites") or cfg.get("sites") or [cfg["site"]])


def training_region(checkpoint: dict, site: str | None = None) -> np.ndarray:
    """The held-out validation blocks of one training site of a checkpoint (default: its first)."""
    from pipeline.cv.dataset import blocks_mask, validation_blocks
    from pipeline.stack import site_grid

    cfg = checkpoint["config"]
    site = site or train_sites_of(checkpoint)[0]
    g = site_grid(get_site(site))
    shape = (g.height, g.width)
    # The exact held-out blocks are stored in the checkpoint (older ones: rebuild the random draw);
    # several training sites store one list of blocks per site.
    blocks = checkpoint.get("val_blocks")
    if isinstance(blocks, dict):
        return blocks_mask(shape, blocks[site], cfg["block"])
    if blocks is not None:
        return blocks_mask(shape, blocks, cfg["block"])
    return validation_blocks(shape, cfg["val_share"], cfg["seed"], cfg["block"])


def _built(site: str, stack_id: str) -> bool:
    return (STACK_DIR / f"{site}_{stack_id}.nc").exists()


def model_report(model_paths: list[Path], threshold: float, val_only: bool = False,
                 sites: tuple[str, ...] = DSWX_LABEL_SITES) -> dict:
    """U-Net (or ensemble) and baseline on the same pixels: validation blocks of each training
    site, and (unless val_only) all of every other site in `sites` plus the DANA flood checks."""
    unet = load_predictor(model_paths, threshold)
    checkpoint = unet.checkpoint  # type: ignore[attr-defined]
    cfg = checkpoint["config"]
    trained_on = train_sites_of(checkpoint)
    rows = []
    for site in dict.fromkeys(trained_on + list(sites)):
        if site in trained_on:
            region, split, stacks = training_region(checkpoint, site), "held-out validation blocks of a training site", site_stacks(site)
        elif val_only:
            continue
        else:
            region, split = None, "test site, never seen in training"
            stacks = site_stacks(site) + tuple(s for s in EXTRA_TEST_STACKS.get(site, ()) if _built(site, s))
        for stack_id in stacks:
            if not _built(site, stack_id):
                print(f"   {site} {stack_id}: no stack built, not scored")
                continue
            for name, predictor in (("baseline", baseline_predictor), ("unet", unet)):
                rows += [{**row, "model": name, "split": split} for row in water_vs_dswx(site, stack_id, predictor, region)]
    floods = [] if val_only else [
        {**check, "baseline": flood_vs_emsr935(baseline_predictor, check), "unet": flood_vs_emsr935(unet, check)}
        for check in FLOODS if _built(check["site"], check["stack"]) and check["site"] not in trained_on]
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": [str(p).replace("\\", "/") for p in model_paths], "checkpoint_epoch": checkpoint["epoch"],
        "train_site": cfg["site"], "train_sites": trained_on,
        "inputs": cfg.get("inputs", "current"), "label_mode": cfg.get("label_mode", "water13"),
        "probability_threshold": threshold, "val_only": val_only,
        "water_vs_dswx": rows, "flood_vs_emsr935": floods,
    }


def threshold_sweep(model_paths: list[Path], thresholds: list[float]) -> dict:
    """Open and any water IoU per probability threshold, on the training sites' validation blocks only."""
    unet = load_predictor(model_paths)
    checkpoint = unet.checkpoint  # type: ignore[attr-defined]
    trained_on = train_sites_of(checkpoint)
    per_date: dict[float, dict[str, list[float]]] = {thr: {"open": [], "any": []} for thr in thresholds}
    pooled = {thr: {"open": np.zeros(3), "any": np.zeros(3)} for thr in thresholds}
    for site, stack_id in ((site, stack_id) for site in trained_on for stack_id in site_stacks(site)):
        region = training_region(checkpoint, site)
        for ds, _, t, _, dswx, perm in labelled_dates(site, stack_id):
            if dswx is None:
                continue
            p_open, p_any = unet.probabilities(ds, t)  # type: ignore[attr-defined]
            scoring = np.isfinite(p_open) & ~np.isin(dswx, DSWX_INVALID) & ~perm & region
            if not scoring.any():
                continue
            truths = {"open": dswx == DSWX_OPEN_WATER, "any": np.isin(dswx, (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG))}
            probs = {"open": p_open, "any": p_any}
            for thr in thresholds:
                for k in ("open", "any"):
                    pred, truth = (probs[k] >= thr) & scoring, truths[k] & scoring
                    tp, fp, fn = int((pred & truth).sum()), int((pred & ~truth).sum()), int((~pred & truth).sum())
                    pooled[thr][k] += (tp, fp, fn)
                    if tp + fp + fn:
                        per_date[thr][k].append(tp / (tp + fp + fn))
    out = {"model": [str(p).replace("\\", "/") for p in model_paths], "site": ", ".join(trained_on),
           "split": "held-out validation blocks", "rows": []}
    for thr in thresholds:
        row = {"threshold": thr}
        for k in ("open", "any"):
            tp, fp, fn = pooled[thr][k]
            row[f"{k}_median_iou"] = round(float(np.median(per_date[thr][k])), 4) if per_date[thr][k] else None
            row[f"{k}_pooled_iou"] = round(tp / (tp + fp + fn), 4) if tp + fp + fn else None
        out["rows"].append(row)
    return out


def print_baseline(report: dict) -> None:
    print("1) Water vs same-day Sentinel-1 (dynamic water only)")
    for site in DSWX_LABEL_SITES:
        for stack_id in site_stacks(site):
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
    for flood in report["flood_vs_emsr935"]:
        print(f"2) DANA flood vs EMSR935, {flood['stack']} {flood['before']} -> {flood['after']} "
              f"(baseline -> U-Net; label {flood['unet']['label_ha']} ha in the scored region)")
        for name in ("water_after", "water_gain", "control_water_before"):
            b, u = flood["baseline"][name], flood["unet"][name]
            print(f"   {name}: " + ", ".join(f"{k} {b[k]} -> {u[k]}" for k in ("iou", "f1", "precision", "recall"))
                  + f", {b['pred_ha']} -> {u['pred_ha']} ha")


def print_sweep(sweep: dict) -> None:
    print(f"threshold sweep on {sweep['site']} {sweep['split']} ({sweep['model']})")
    print("   threshold | open water: median IoU, pooled IoU | any water: median IoU, pooled IoU")
    for r in sweep["rows"]:
        print(f"   {r['threshold']:9.2f} | {r['open_median_iou']}, {r['open_pooled_iou']} | "
              f"{r['any_median_iou']}, {r['any_pooled_iou']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, nargs="+",
                        help="U-Net checkpoint to score against the baseline; several = their ensemble")
    parser.add_argument("--name", help="output file stem (default: the model's stem, or cv_ensemble)")
    parser.add_argument("--threshold", type=float, default=0.5, help="water probability threshold for the U-Net")
    parser.add_argument("--val-only", action="store_true", help="only the training site's validation blocks")
    parser.add_argument("--sweep", help="comma-separated thresholds to try on the validation blocks")
    parser.add_argument("--sites", nargs="+", default=list(DSWX_LABEL_SITES),
                        help="sites to score besides the training sites (default: %(default)s)")
    args = parser.parse_args()
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    name = args.name or (args.model[0].stem if args.model and len(args.model) == 1 else "cv_ensemble")
    if args.model and args.sweep:
        report = threshold_sweep(args.model, [float(v) for v in args.sweep.split(",")])
        path = METRICS_DIR / f"{name}_sweep.json"
        print_sweep(report)
    elif args.model:
        report = model_report(args.model, args.threshold, args.val_only, tuple(args.sites))
        path = METRICS_DIR / f"{name}{'_val' if args.val_only else ''}.json"
        print_comparison(report)
    else:
        report = baseline_report()
        path = METRICS_DIR / "cv_baseline.json"
        print_baseline(report)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
