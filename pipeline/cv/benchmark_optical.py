"""CV benchmark against an independent optical answer key (pre-registered in docs/CV_BENCHMARK.md).

    python -m pipeline.cv.benchmark_optical --cache v1                # U-Net probabilities of a model set (GPU), once
    python -m pipeline.cv.benchmark_optical --count --sites albufera ebro camargue   # counts on training sites
    python -m pipeline.cv.benchmark_optical --select                  # free parameters, training-site blocks only
    python -m pipeline.cv.benchmark_optical --count                   # counts on every site (after all training)
    python -m pipeline.cv.benchmark_optical --score                   # tables, intervals, the DANA flood check

The answer key is OPERA DSWx-HLS (Landsat and Sentinel-2, 30 m) within 1 day of each NISAR date
(pipeline.cv.optical, data/optical): open water = class 1, no water = class 0, anything else is not
scored. Sentinel-1's own water map (OPERA DSWx-S1) is a competitor here, not the answer key.

Pixels: NISAR usable on the date (HH and HV), answer key clear, neither sea nor permanent water
(changing water, as in pipeline.cv.evaluate); on a training site only inside its held-out validation
blocks, on a test site everywhere. Dates: those with HV whose clear answer key covers at least
MIN_CLEAR_SHARE of those pixels. Two pixel sets: "all_dates" (every NISAR method) and
"with_sentinel1" (dates with a DSWx-S1 map at most MAX_GAP_H from the pass, its valid pixels, every
method plus Sentinel-1). Every method is scored on exactly the same pixels within a set.

Counts are kept per land type (ESA WorldCover): cropland; grass, shrub and herbaceous wetland; bare;
other. Optical cannot see water under plants, so in cropland and wetland a radar "false" water may be
real water the answer key misses; that is why the land types are reported apart.

Writes data/interim/cv_optical_counts.json (per date, method, pixel set and land type; regenerable),
data/metrics/cv_optical_select.json and data/metrics/cv_optical_benchmark.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

from pipeline.config import CV_LABEL_SITES, DATA_DIR, STACK_DIR, site_stacks
from pipeline.cv.benchmark import N_BOOT, SEED, bootstrap_weights, interval
from pipeline.cv.coherence import coherence_for, coherence_path
from pipeline.cv.data import open_stack
from pipeline.cv.dataset import optical_classes
from pipeline.cv.evaluate import (
    CONTEXT_DIR, DSWX_INUNDATED_VEG, DSWX_INVALID, DSWX_OPEN_WATER, EXTRA_TEST_STACKS, METRICS_DIR, _built,
    baseline_water, date_index, labelled_dates, load_predictor, permanent_water, scene_db,
    training_region,
)

M = DATA_DIR / "models"
MODEL_SETS: dict[str, list[Path]] = {
    "v1": [M / "cv_e2_aec_s0.pt", M / "cv_e2_aec_s1.pt", M / "cv_e2_aec_s2.pt", M / "cv_e4_aec_current_s0.pt",
           M / "cv_e5_aec_gap13_s0.pt"],
    "v2": [M / "cv_v2_e2_s0.pt", M / "cv_v2_e2_s1.pt", M / "cv_v2_e2_s2.pt", M / "cv_v2_e4_s0.pt",
           M / "cv_v2_e5_s0.pt"],
    # single seed 0 runs, to see what each change does on its own
    "abl_v1_s0": [M / "cv_e2_aec_s0.pt"],
    "abl_coh_s0": [M / "cv_v2a_coh_s0.pt"],
    "abl_clean_s0": [M / "cv_v2b_clean_s0.pt"],
    "abl_both_s0": [M / "cv_v2_e2_s0.pt"],
}
TRAINING_SITES = ("albufera", "ebro", "camargue")
TEST_SITES = ("pego_oliva", "donana")
CACHE_DIR = DATA_DIR / "interim" / "cv_prob"
COUNTS_PATH = DATA_DIR / "interim" / "cv_optical_counts.json"

MIN_CLEAR_SHARE = 0.10
DARK_DB = -15.0
# Grids of docs/CV_BENCHMARK.md section 7, each extended once downwards (section 11): on the training
# sites the best value was the lowest one of the first grid, for both.
C_GRID = (0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5)            # coherence cut of the dark-and-low-coherence rule
TH_GRID = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5)       # U-Net probability thresholds
H_GRID = (0.5, 0.6, 0.7)                               # spot filter: a water region needs one pixel this sure
V1_THRESHOLD = 0.3                                     # pre-registered in docs/CV_RESULTS.md
STRATA = ("cropland", "grass_shrub_wetland", "bare", "other")
PAIRS = [("v2", "v1"), ("v2", "sentinel1_dswx"), ("v1", "sentinel1_dswx"),
         ("nisar_dark_lowcoh", "nisar_threshold_15db"), ("v2_spot", "v2"),
         ("abl_coh_s0", "abl_v1_s0"), ("abl_clean_s0", "abl_v1_s0"), ("abl_both_s0", "abl_v1_s0")]


def _q(p: np.ndarray) -> np.ndarray:
    out = np.full(p.shape, 255, dtype="uint8")
    ok = np.isfinite(p)
    out[ok] = np.clip(np.rint(p[ok] * 250), 0, 250).astype("uint8")
    return out


def _dq(q: np.ndarray) -> np.ndarray:
    p = q.astype("float32") / 250
    p[q == 255] = np.nan
    return p


def stacks_of(site: str) -> list[str]:
    return [s for s in site_stacks(site) + EXTRA_TEST_STACKS.get(site, ()) if _built(site, s)]


def hv_dates(ds) -> dict[str, int]:
    return {d: t for d, t in date_index(ds).items() if not np.isnan(ds["HV"].values[t]).all()}


def cache_path(name: str, site: str, stack_id: str, day: str) -> Path:
    return CACHE_DIR / name / f"{site}_{stack_id}_{day}.npz"


def cache_set(name: str, sites: tuple[str, ...] = tuple(CV_LABEL_SITES)) -> None:
    """Open and any water probabilities of one model set on every date with HV (uint8, 255 = not usable)."""
    import torch

    unet = load_predictor(MODEL_SETS[name])
    # Every set must hold out the very blocks the benchmark scores on (v1's), or its training
    # pixels would be scored as held out.
    v1_blocks = torch.load(MODEL_SETS["v1"][0], map_location="cpu", weights_only=False)["val_blocks"]
    if unet.checkpoint.get("val_blocks") != v1_blocks:  # type: ignore[attr-defined]
        raise ValueError(f"{name}: its validation blocks differ from v1's; the benchmark would leak")
    files = []
    for site in sites:
        for stack_id in stacks_of(site):
            ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
            for day, t in hv_dates(ds).items():
                out = cache_path(name, site, stack_id, day)
                files.append(out.name)
                if out.exists():
                    continue
                p_open, p_any = unet.probabilities(ds, t)  # type: ignore[attr-defined]
                out.parent.mkdir(parents=True, exist_ok=True)
                tmp = out.with_name(out.stem + ".part.npz")  # a stopped run never leaves a half file behind
                np.savez_compressed(tmp, p_open=_q(p_open), p_any=_q(p_any))
                tmp.replace(out)
            print(f"{name}: {site} {stack_id} cached", flush=True)
    # The manifest ties the cache to the exact checkpoints; --count refuses a set without one or
    # whose checkpoints changed since (a model retrained or still training).
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sites": list(sites),
                "files": sorted(files), "models": [model_fingerprint(p) for p in MODEL_SETS[name]]}
    _save(CACHE_DIR / name / "manifest.json", manifest)


def model_fingerprint(path: Path) -> dict:
    import hashlib

    import torch

    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    epoch = torch.load(path, map_location="cpu", weights_only=False).get("epoch")
    return {"path": Path(path).as_posix(), "sha256": digest, "epoch": epoch}


def complete_sets(sites: list[str]) -> list[str]:
    """Model sets whose cache is complete for these sites and made from the checkpoints on disk now."""
    ok = []
    for name, paths in MODEL_SETS.items():
        path = CACHE_DIR / name / "manifest.json"
        if not path.exists():
            if (CACHE_DIR / name).exists():
                print(f"{name}: cache without a manifest (incomplete), not counted")
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if [m["sha256"] for m in manifest["models"]] != [model_fingerprint(p)["sha256"] for p in paths]:
            raise SystemExit(f"{name}: its checkpoints changed after caching; rerun --cache {name}")
        missing = [s for s in sites if s not in manifest["sites"]]
        if missing:
            raise SystemExit(f"{name}: not cached for {missing}; rerun --cache {name}")
        ok.append(name)
    return ok


def load_cached(name: str, site: str, stack_id: str, day: str) -> tuple[np.ndarray, np.ndarray] | None:
    path = cache_path(name, site, stack_id, day)
    if not path.exists():
        return None
    with np.load(path) as z:
        return _dq(z["p_open"]), _dq(z["p_any"])


def spot_filter(water: np.ndarray, sure: np.ndarray) -> np.ndarray:
    """Keep only the connected water regions (8-neighbour) that hold at least one sure pixel."""
    from scipy import ndimage

    lab, n = ndimage.label(water, structure=np.ones((3, 3), bool))
    if n == 0:
        return water
    keep = np.zeros(n + 1, bool)
    keep[np.unique(lab[sure & water])] = True
    keep[0] = False
    return keep[lab]


def regions_of(site: str) -> np.ndarray | None:
    """Validation blocks of a training site (the blocks every v1 and v2 model shares), else None."""
    if site not in TRAINING_SITES:
        return None
    import torch

    checkpoint = torch.load(MODEL_SETS["v1"][0], map_location="cpu", weights_only=False)
    return training_region(checkpoint, site)


def cover_strata(site: str) -> np.ndarray:
    with rasterio.open(CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif") as src:
        cover = src.read(1)
    return np.select([cover == 40, np.isin(cover, (20, 30, 90)), cover == 60], [0, 1, 2], 3).astype("int64")


def _methods(site: str, stack_id: str, day: str, ds, t: int, sets: list[str]) -> dict[str, np.ndarray]:
    hh_db, _ = scene_db(ds["HH"].values[t], ds["valid"].values[t])
    dark = hh_db < DARK_DB
    m = {"nisar_threshold_15db": dark, "nisar_otsu": baseline_water(ds, t)[0]}
    coh = coherence_for(site, stack_id, day, dark.shape)
    for c in C_GRID:
        m[f"nisar_dark_lowcoh@{c}"] = dark & ~(coh >= c)  # no pair: the darkness rule alone
    for name in sets:
        cached = load_cached(name, site, stack_id, day)
        if cached is None:  # complete_sets checked the manifest: a missing file is an error, not a skip
            raise SystemExit(f"{name}: no cached probabilities for {site} {stack_id} {day}")
        p_open = np.nan_to_num(cached[0], nan=0.0)
        for th in TH_GRID:
            m[f"{name}@{th}"] = p_open >= th
            if name == "v2":
                for h in H_GRID:
                    m[f"v2_spot@{th}+{h}"] = spot_filter(p_open >= th, p_open >= h)
    return m


def count_site(site: str, sets: list[str]) -> list[dict]:
    """Confusion counts of every method on every scored date of a site, per pixel set and land type."""
    region = regions_of(site)
    strata = cover_strata(site)
    rows = []
    for stack_id in stacks_of(site):
        dswx_by_day = {d: dswx for _, d, _, _, dswx, _ in labelled_dates(site, stack_id)}
        ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
        perm = permanent_water(ds, site)
        for day, t in hv_dates(ds).items():
            optical = optical_classes(site, stack_id, day)
            if optical is None:
                rows.append({"site": site, "stack": stack_id, "date": day, "skipped": "no optical image within 1 day"})
                continue
            valid = ds["valid"].values[t].astype(bool)
            _, ok_f = scene_db(ds["HH"].values[t], ds["valid"].values[t])
            usable = valid & np.isfinite(ds["HH"].values[t]) & np.isfinite(ds["HV"].values[t]) & ok_f
            base = usable & ~perm & (region if region is not None else True)
            scoring = base & np.isin(optical, (0, 1))
            share = float(scoring.sum() / max(base.sum(), 1))
            if share < MIN_CLEAR_SHARE:
                rows.append({"site": site, "stack": stack_id, "date": day, "skipped": f"answer key clear on {share:.1%}"})
                continue
            truth = (optical == 1).astype("int64")
            methods = _methods(site, stack_id, day, ds, t, sets)
            pixel_sets = {"all_dates": scoring}
            dswx = dswx_by_day.get(day)
            if dswx is not None:
                pixel_sets["with_sentinel1"] = scoring & ~np.isin(dswx, DSWX_INVALID)
                methods["sentinel1_dswx"] = dswx == DSWX_OPEN_WATER
            has_coh = coherence_path(site, stack_id, day) is not None
            for set_name, px in pixel_sets.items():
                st, tr = strata[px], truth[px]
                for name, pred in methods.items():
                    if name == "sentinel1_dswx" and set_name != "with_sentinel1":
                        continue
                    c = np.bincount(st * 4 + pred[px].astype("int64") * 2 + tr, minlength=16).reshape(4, 4)
                    # per land type: [tn, fn, fp, tp] (pred, truth) = (0,0), (0,1), (1,0), (1,1)
                    rows.append({"site": site, "stack": stack_id, "date": day, "set": set_name, "method": name,
                                 "clear_share": round(share, 3), "has_coherence": has_coh,
                                 "counts": {s: [int(v) for v in c[i]] for i, s in enumerate(STRATA)}})
            print(f"  {site} {stack_id} {day}: clear {share:.0%}, {len(methods)} methods", flush=True)
    return rows


def _sum(rows: list[dict], strata: tuple[str, ...]) -> np.ndarray:
    """(n rows, 4) [tn, fn, fp, tp] summed over the given land types."""
    return np.array([[sum(r["counts"][s][k] for s in strata) for k in range(4)] for r in rows], dtype="float64")


def pooled(c: np.ndarray) -> dict:
    tn, fn, fp, tp = c.sum(axis=0)
    return {"iou": round(tp / (tp + fp + fn), 4) if tp + fp + fn else None,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "false_water_share_of_dry": round(fp / (fp + tn), 5) if fp + tn else None,
            "water_ha": round(tp * 0.04 + fn * 0.04, 1), "dates": int(len(c))}


def select(rows: list[dict]) -> dict:
    """Every free parameter, by pooled IoU over the training sites' validation blocks (all dates)."""
    train = [r for r in rows if r.get("set") == "all_dates" and r["site"] in TRAINING_SITES]

    def iou(name: str) -> float:
        """Unrounded pooled IoU, so ties are judged on the exact counts; -1 when not counted."""
        sel = [r for r in train if r["method"] == name]
        if not sel:
            return -1.0
        tn, fn, fp, tp = _sum(sel, STRATA).sum(axis=0)
        return float(tp / (tp + fp + fn)) if tp + fp + fn else -1.0

    out: dict[str, dict] = {"rule": "highest pooled IoU of changing open water on the training sites' validation "
                                    "blocks against the optical answer key; ties to the value listed first"}
    def best(grid: list[dict]) -> dict:
        """The first entry with the highest exact IoU (grids run from the lowest value up), IoU rounded for the record."""
        top = max(grid, key=lambda d: d["iou"])
        return {**{k: (round(v, 4) if k == "iou" else v) for k, v in top.items()},
                "grid": [{**g, "iou": round(g["iou"], 4)} for g in grid]}

    out["nisar_dark_lowcoh"] = best([{"c": c, "iou": iou(f"nisar_dark_lowcoh@{c}")} for c in C_GRID])
    for name in MODEL_SETS:
        grid = [{"threshold": th, "iou": iou(f"{name}@{th}")} for th in TH_GRID]
        if max(g["iou"] for g in grid) < 0:
            continue  # not trained or not cached yet
        out[name] = best(grid)
    if "v2" in out:
        th = out["v2"]["threshold"]
        out["v2_spot"] = best([{"threshold": th, "sure": h, "iou": iou(f"v2_spot@{th}+{h}")} for h in H_GRID])
    return out


def chosen_methods(choice: dict) -> dict[str, str]:
    """Table name -> method key in the counts."""
    out = {"sentinel1_dswx": "sentinel1_dswx", "nisar_threshold_15db": "nisar_threshold_15db",
           "nisar_otsu": "nisar_otsu", "nisar_dark_lowcoh": f"nisar_dark_lowcoh@{choice['nisar_dark_lowcoh']['c']}",
           "v1_preregistered_0.3": f"v1@{V1_THRESHOLD}"}
    for name in MODEL_SETS:
        if name in choice:
            out[name] = f"{name}@{choice[name]['threshold']}"
    if "v2_spot" in choice:
        out["v2_spot"] = f"v2_spot@{choice['v2_spot']['threshold']}+{choice['v2_spot']['sure']}"
    return out


def score(rows: list[dict], choice: dict) -> list[dict]:
    """Per site group, pixel set and land type: every chosen method with 95 % intervals over dates
    (resampled within each stack) and the paired differences of PAIRS on the same draws."""
    names = chosen_methods(choice)
    groups = [("pego_oliva", ("pego_oliva",), None), ("donana", ("donana",), None),
              ("training_validation_blocks", TRAINING_SITES, None)]
    # the newest dates have no GUNW pair yet: the same sites split by whether the date has coherence
    groups += [(f"{s}, dates with coherence", (s,), True) for s in TEST_SITES]
    groups += [(f"{s}, dates without coherence", (s,), False) for s in TEST_SITES]
    out = []
    for group, sites, with_coh in groups:
        for set_name in ("all_dates", "with_sentinel1"):
            here = [r for r in rows if r.get("set") == set_name and r["site"] in sites
                    and (with_coh is None or r.get("has_coherence") == with_coh)]
            dates = sorted({(r["site"], r["stack"], r["date"]) for r in here})
            if not dates:
                continue
            strata_of = [f"{s} {k}" for s, k, _ in dates]
            # Dates are resampled within their stack; a stack with one date adds no spread, and when no
            # stack has two dates every draw is the point itself: then no interval and no "better" claim.
            w = bootstrap_weights(strata_of, N_BOOT, SEED) if max(map(strata_of.count, strata_of)) >= 2 else None
            for strata_name, strata in [("all", STRATA)] + [(s, (s,)) for s in STRATA]:
                per_method: dict[str, np.ndarray] = {}
                for table_name, key in names.items():
                    by_date = {(r["site"], r["stack"], r["date"]): r for r in here if r["method"] == key}
                    if len(by_date) != len(dates):
                        continue  # not scored on this set (Sentinel-1 on all_dates) or not trained yet
                    per_method[table_name] = _sum([by_date[d] for d in dates], strata)
                entry = {"group": group, "set": set_name, "land": strata_name, "dates": len(dates),
                         "stacks": len(set(strata_of)),
                         "intervals": "95 %, dates resampled within each stack" if w is not None
                                      else "not computed: no stack has two scored dates", "methods": {}}
                draws = {}
                for table_name, c in per_method.items():
                    entry["methods"][table_name] = pooled(c)
                    if w is None:
                        continue
                    tn, fn, fp, tp = (w @ c).T
                    with np.errstate(invalid="ignore", divide="ignore"):
                        draws[table_name] = tp / (tp + fp + fn)
                        entry["methods"][table_name].update({
                            "iou_95": interval(draws[table_name]), "precision_95": interval(tp / (tp + fp)),
                            "recall_95": interval(tp / (tp + fn)),
                            "false_water_share_of_dry_95": interval(fp / (fp + tn))})
                entry["paired_iou_difference_95"] = {
                    f"{a} - {b}": {"point": round(entry["methods"][a]["iou"] - entry["methods"][b]["iou"], 4)
                                   if entry["methods"][a]["iou"] is not None and entry["methods"][b]["iou"] is not None
                                   else None,
                                   "interval": interval(draws[a] - draws[b]) if a in draws and b in draws else None}
                    for a, b in PAIRS if a in entry["methods"] and b in entry["methods"]}
                out.append(entry)
    return out


def cached_predictor(name: str, threshold: float, sure: float | None = None):
    """A pipeline.cv.evaluate Predictor that reads the cached probabilities of a model set."""
    def predict(ds, t):
        site, stack_id = str(ds.attrs.get("site")), str(ds.attrs.get("stack_id"))
        day = str(ds["time"].values[t])[:10]
        p_open, p_any = load_cached(name, site, stack_id, day)
        ok = np.isfinite(p_open)
        p_open, p_any = np.nan_to_num(p_open, nan=0.0), np.nan_to_num(p_any, nan=0.0)
        water_open, water_any = p_open >= threshold, p_any >= threshold
        if sure is not None:
            water_open = spot_filter(water_open, p_open >= sure)
            water_any = spot_filter(water_any, p_any >= sure)
        return {"open": ok & water_open, "any": ok & water_any}, ok, {}
    return predict


def dark_lowcoh_predictor(c: float):
    def predict(ds, t):
        hh_db, ok = scene_db(ds["HH"].values[t], ds["valid"].values[t])
        day = str(ds["time"].values[t])[:10]
        coh = coherence_for(str(ds.attrs.get("site")), str(ds.attrs.get("stack_id")), day, hh_db.shape)
        return ok & (hh_db < DARK_DB) & ~(coh >= c), ok, {"coherence_cut": c}
    return predict


def threshold_predictor(ds, t):
    hh_db, ok = scene_db(ds["HH"].values[t], ds["valid"].values[t])
    return ok & (hh_db < DARK_DB), ok, {"threshold_db": DARK_DB}


def sentinel1_predictor(site: str, stack_id: str):
    maps = {d: dswx for _, d, _, _, dswx, _ in labelled_dates(site, stack_id)}

    def predict(ds, t):
        dswx = maps.get(str(ds["time"].values[t])[:10])
        if dswx is None:
            raise ValueError("no same-pass Sentinel-1 map on this date")
        ok = ~np.isin(dswx, DSWX_INVALID) & ds["valid"].values[t].astype(bool)
        return {"open": ok & (dswx == DSWX_OPEN_WATER),
                "any": ok & np.isin(dswx, (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG))}, ok, {}
    return predict


def withheld_predictor(name: str, threshold: float, sure: float | None = None):
    """A "+coh" model set run with coherence withheld on every date (the channel mean), so before and
    after a flood are built the same way when only one of the two dates has a pair."""
    unet = load_predictor(MODEL_SETS[name], use_coherence=False)

    def predict(ds, t):
        p_open, p_any = unet.probabilities(ds, t)  # type: ignore[attr-defined]
        ok = np.isfinite(p_open)
        p_open, p_any = np.nan_to_num(p_open, nan=0.0), np.nan_to_num(p_any, nan=0.0)
        water_open, water_any = p_open >= threshold, p_any >= threshold
        if sure is not None:
            water_open, water_any = spot_filter(water_open, p_open >= sure), spot_filter(water_any, p_any >= sure)
        return {"open": ok & water_open, "any": ok & water_any}, ok, {}
    return predict


def flood_table(choice: dict) -> dict:
    """The DANA flood (track 066 D, 16 to 28 Oct) against the human-drawn EMSR935 outline (imagery 20
    to 21 Oct), water = open water plus flooded vegetation, as in docs/CV_RESULTS.md, but every method
    on the same pixels: inside the mapped areas, not permanent water, not flood traces, and usable
    for every method on both dates. 16 Oct has a coherence pair and 28 Oct has none, so the coherence
    methods are also run with coherence withheld on both dates: only those rows compare fairly."""
    import geopandas as gpd

    from pipeline.cv.baseline import area_ha
    from pipeline.cv.data import rasterize_on
    from pipeline.cv.evaluate import FLOOD, LABELS_DIR, baseline_predictor, masks
    from pipeline.cv.metrics import confusion, scores

    site, stack_id = FLOOD["site"], FLOOD["stack"]
    preds = {"sentinel1_dswx": sentinel1_predictor(site, stack_id),
             "nisar_threshold_15db": threshold_predictor, "nisar_otsu": baseline_predictor,
             "nisar_dark_lowcoh, coherence as available (16 Oct only)":
                 dark_lowcoh_predictor(choice["nisar_dark_lowcoh"]["c"]),
             "v1_preregistered_0.3": cached_predictor("v1", V1_THRESHOLD)}
    if "v1" in choice:
        preds["v1"] = cached_predictor("v1", choice["v1"]["threshold"])
    if "v2" in choice:
        th = choice["v2"]["threshold"]
        preds["v2, coherence as available (16 Oct only)"] = cached_predictor("v2", th)
        preds["v2, coherence withheld on both dates"] = withheld_predictor("v2", th)
    if "v2_spot" in choice:
        th, sure = choice["v2_spot"]["threshold"], choice["v2_spot"]["sure"]
        preds["v2_spot, coherence as available (16 Oct only)"] = cached_predictor("v2", th, sure)
        preds["v2_spot, coherence withheld on both dates"] = withheld_predictor("v2", th, sure)

    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    days = date_index(ds)
    maps = {}
    for name, p in preds.items():
        before, ok_before, _ = p(ds, days[FLOOD["before"]])
        after, ok_after, _ = p(ds, days[FLOOD["after"]])
        maps[name] = (masks(before)[1], masks(after)[1], ok_before & ok_after)
    outlines = gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_flood.geojson")
    flooded = rasterize_on(ds, outlines[outlines["class"] == "flooded_area"]).astype(bool)
    trace = rasterize_on(ds, outlines[outlines["class"] == "flood_trace"]).astype(bool)
    mapped = rasterize_on(ds, gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_aoi.geojson")).astype(bool)
    region = mapped & ~permanent_water(ds, site) & ~trace
    for _, _, ok in maps.values():
        region &= ok
    out = {"site": site, "stack": stack_id, "before": FLOOD["before"], "after": FLOOD["after"],
           "label": "EMSR935 flooded_area, imagery 20 to 21 Oct 2026, inside the mapped AOIs",
           "region_ha": round(area_ha(region), 1), "label_ha": round(area_ha(flooded & region), 1),
           "note": ("thresholds chosen for open water are applied to any water here; the dark and low "
                    "coherence rule with coherence withheld on both dates is the NISAR threshold itself"),
           "methods": {}}
    for name, (before, after, _) in maps.items():
        out["methods"][name] = {k: {**scores(confusion(m, flooded, region)), "pred_ha": round(area_ha(m & region), 1)}
                                for k, m in {"water_gain": after & ~before, "water_after": after,
                                             "control_water_before": before}.items()}
    return out


def _save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    print(f"-> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", nargs="+", choices=list(MODEL_SETS), help="cache these model sets' probabilities")
    parser.add_argument("--count", action="store_true", help="count every method on the answer key")
    parser.add_argument("--select", action="store_true", help="choose the free parameters (training sites only)")
    parser.add_argument("--score", action="store_true", help="benchmark tables and the DANA flood check")
    parser.add_argument("--sites", nargs="+", default=list(CV_LABEL_SITES))
    args = parser.parse_args()
    if args.cache:
        for name in args.cache:
            cache_set(name, tuple(args.sites))
    if args.count:
        sets = complete_sets(args.sites)
        print(f"model sets with complete caches from the current checkpoints: {sets}")
        rows = [r for site in args.sites for r in count_site(site, sets)]
        _save(COUNTS_PATH, {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "sites": args.sites, "model_sets": sets, "rows": rows})
    if args.select:
        rows = json.loads(COUNTS_PATH.read_text(encoding="utf-8"))["rows"]
        choice = select(rows)
        _save(METRICS_DIR / "cv_optical_select.json", choice)
    if args.score:
        counts = json.loads(COUNTS_PATH.read_text(encoding="utf-8"))
        missing = [s for s in TEST_SITES if s not in counts["sites"]]
        if missing:
            raise SystemExit(f"counts lack the test sites {missing}: run --count on every site first")
        choice = json.loads((METRICS_DIR / "cv_optical_select.json").read_text(encoding="utf-8"))
        result = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "protocol": "docs/CV_BENCHMARK.md", "choice": choice, "methods": chosen_methods(choice),
                  "skipped_dates": [r for r in counts["rows"] if "skipped" in r],
                  "tables": score(counts["rows"], choice), "dana_flood_emsr935": flood_table(choice)}
        _save(METRICS_DIR / "cv_optical_benchmark.json", result)


if __name__ == "__main__":
    main()
