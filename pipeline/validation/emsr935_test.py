"""Independent test of the flood-extent model against Copernicus EMSR935 (paper Section 4.5).

Run by L. Georgieski, not the model's author. The rules below were fixed before any score was looked at;
where the published EMSR935 data differ from what Section 4.5 assumed, the change is stated here and in
the paper.

Model under test
    Z. Stoimchev's spatial water-likelihood model (PR #33), variant ``base`` (the one behind every exported
    map), DANA replay ``replay_2026-10-22`` at Pego-Oliva: issued from the Sentinel-1 pass of 17 Oct, target
    22 Oct, with the rain that fell. The pass is two days after the EMSR935 imagery (20-21 Oct); the model
    has no map for 20 Oct. "Likely water" = ``water_likelihood`` >= the frozen threshold of the model's
    development check (``development_metrics.json`` thresholds.rain_and_state.water), never tuned here.
    Also reported, not part of the rule: ``forecast_2026-10-22`` (the same replay with the rain the IFS run of
    17 Oct forecast).

Reference
    EMSR935 AOI01 (Pego-Oliva marsh). Section 4.5 assumed an "observed" and a "modelled" layer and a
    "not analysed" mask. The published data (data/labels, ICV republication of the CEMS WFS) instead have
    ``flooded_area`` (semi-automatic extraction from the image) and ``flood_trace`` (photo-interpretation of
    where water had been), and no "not analysed" mask. So: main reference = ``flooded_area``; second
    reference = ``flooded_area`` + ``flood_trace``; scored area = the whole AOI01 inside the model grid.

Scored pixels (the same for every method)
    20 m model grid (UTM 30N); inside AOI01; land (not sea); not permanent water (JRC occurrence >= 90 %,
    the model's own evidence flag 1, context not flooding); valid in the NISAR pass of 16 Oct (so persistence
    can be scored). Main set: all such pixels, towns included. Second set: only pixels where the model learned
    (evidence 0).

Baselines (Section 4.5)
    (i) low terrain: the pixels with the lowest height above the nearest drainage (HAND, the model's own
        GLO-30 HAND), exactly as many as the model calls likely water in the same set;
    (ii) past water: JRC occurrence > 0;
    (iii) persistence: NISAR water on 16 Oct (track 066 D), 5x5-filtered HH < -15 dB (the paper's water rule);
          the scene's Otsu threshold is reported as a sensitivity.

Rule
    The model adds value if its F1 beats all three baselines; otherwise we say it does not. Uncertainty of each
    F1 difference: 1,000 bootstrap resamples of 1 km blocks (pixels close together are not independent).

    python -m pipeline.validation.emsr935_test --model-dir DIR [--data DIR]

DIR holds ``data/prediction/spatial`` of PR #33 (``git archive`` of the pinned commit). Writes
data/validation/emsr935/result.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from pipeline.config import DATA_DIR

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "validation" / "emsr935"
STACK = "pego_oliva_066_D_069.nc"
BEFORE = "2026-10-16"
NISAR_DB = -15.0
BLOCK_PX = 50          # 50 x 20 m = 1 km
REPS = 1000
SEED = 20261115
PIXEL_HA = 0.04
PR33_COMMIT = "b4c69d9af6e86ebcf8a61f7772056023f2ada290"


def _read(path: Path) -> tuple[np.ndarray, object]:
    import rasterio
    with rasterio.open(path) as r:
        return r.read(1), r


def _rasterize(features: list[dict], like) -> np.ndarray:
    import geopandas as gpd
    from rasterio.features import rasterize
    if not features:
        return np.zeros(like.shape, bool)
    g = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326").to_crs(like.crs)
    return rasterize(((geom, 1) for geom in g.geometry), out_shape=like.shape, transform=like.transform,
                     fill=0, dtype="uint8").astype(bool)


def scores(pred: np.ndarray, ref: np.ndarray) -> dict:
    tp = float(np.sum(pred & ref)); fp = float(np.sum(pred & ~ref)); fn = float(np.sum(~pred & ref))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    iou = tp / (tp + fp + fn) if tp + fp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3), "iou": round(iou, 3),
            "predicted_ha": round(float(pred.sum()) * PIXEL_HA, 1), "observed_ha": round(float(ref.sum()) * PIXEL_HA, 1)}


def _counts(pred, ref, blocks, nb):
    tp = np.bincount(blocks, weights=(pred & ref), minlength=nb)
    fp = np.bincount(blocks, weights=(pred & ~ref), minlength=nb)
    fn = np.bincount(blocks, weights=(~pred & ref), minlength=nb)
    return np.stack([tp, fp, fn])


def _f1(c):
    tp, fp, fn = c
    return np.where(2 * tp + fp + fn > 0, 2 * tp / np.maximum(2 * tp + fp + fn, 1e-9), 0.0)


def block_bootstrap(methods: dict, ref: np.ndarray, rows: np.ndarray, cols: np.ndarray, model: str) -> dict:
    """95 % interval of F1(model) - F1(baseline), resampling 1 km blocks with replacement."""
    bid = (rows // BLOCK_PX) * 10_000 + (cols // BLOCK_PX)
    _, blocks = np.unique(bid, return_inverse=True)
    nb = int(blocks.max()) + 1
    cnt = {k: _counts(v, ref, blocks, nb) for k, v in methods.items()}
    rng = np.random.default_rng(SEED)
    diffs = {k: [] for k in methods if k != model}
    for _ in range(REPS):
        w = np.bincount(rng.integers(0, nb, nb), minlength=nb)
        f = {k: float(_f1((c * w).sum(axis=1))) for k, c in cnt.items()}
        for k in diffs:
            diffs[k].append(f[model] - f[k])
    return {k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for k, v in diffs.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", type=Path, required=True, help="folder holding data/prediction/spatial of PR #33")
    ap.add_argument("--data", type=Path, default=DATA_DIR)
    a = ap.parse_args(argv)
    from pipeline.cv.data import open_stack
    from pipeline.prediction.nisar_check import scene_db

    sp = a.model_dir / "data" / "prediction" / "spatial"
    site = sp / "pego_oliva"
    dev = json.loads((sp / "development_metrics.json").read_text(encoding="utf-8"))
    thr = float(dev["thresholds"]["rain_and_state"]["water"])
    like_main, grid = _read(site / "replay_2026-10-22" / "water_likelihood_utm.tif")
    like_fc, _ = _read(site / "forecast_2026-10-22" / "water_likelihood_utm.tif")
    ev, _ = _read(site / "replay_2026-10-22" / "evidence_utm.tif")
    hand, _ = _read(site / "static" / "hand_m.tif")
    jrc, _ = _read(ROOT / "data" / "context" / "pego_oliva_jrc_occurrence_20m.tif")
    sea, _ = _read(ROOT / "data" / "context" / "pego_oliva_sea_20m.tif")
    meta = json.loads((site / "replay_2026-10-22" / "forecast.json").read_text(encoding="utf-8"))

    aoi = json.loads((ROOT / "data/labels/pego_oliva_emsr935_aoi.geojson").read_text(encoding="utf-8"))["features"]
    fl = json.loads((ROOT / "data/labels/pego_oliva_emsr935_flood.geojson").read_text(encoding="utf-8"))["features"]
    in_aoi = _rasterize([f for f in aoi if f["properties"]["aoi"] == "AOI01"], grid)
    ref_area = _rasterize([f for f in fl if f["properties"]["aoi"] == "AOI01" and f["properties"]["class"] == "flooded_area"], grid)
    ref_trace = _rasterize([f for f in fl if f["properties"]["aoi"] == "AOI01" and f["properties"]["class"] == "flood_trace"], grid)

    ds = open_stack(a.data / "stack" / STACK)
    days = [str(t)[:10] for t in ds["time"].values]
    hh, ok, otsu = scene_db(ds, days.index(BEFORE))

    base = in_aoi & (sea == 0) & (ev != 255) & (ev != 1) & ok & np.isfinite(like_main) & np.isfinite(hand) & (jrc != 255)
    sets = {"all_pixels": base, "model_learning_domain": base & (ev == 0)}
    out = {"model": {"pr": 33, "commit": PR33_COMMIT, "model_sha256_16": meta.get("model_sha256_16"), "variant": "base",
                     "scenario": "replay_2026-10-22", "issued_from_pass": meta.get("issued_from_pass"),
                     "target_pass": meta.get("target_pass"), "threshold_water_frozen": round(thr, 4)},
           "reference": "Copernicus EMSR935 AOI01, imagery 20-21 Oct 2026 (data/labels)",
           "nisar_before": {"date": BEFORE, "threshold_db": NISAR_DB, "otsu_db": round(float(otsu), 2)},
           "rule": "model F1 > F1 of each of baselines (i) low HAND, (ii) JRC > 0, (iii) NISAR 16 Oct persistence",
           "bootstrap": {"block_m": BLOCK_PX * 20, "reps": REPS, "seed": SEED}, "sets": {}}

    for sname, m in sets.items():
        rows, cols = np.nonzero(m)
        model = like_main[m] >= thr
        k = int(model.sum())
        # Fix after the first run (commit 1559091): about 38 % of the grid has HAND exactly 0, far more than the
        # model's area, so a plain sort filled the quota with tied pixels in raster order (top rows first).
        # Ties are now broken at random (fixed seed); the spread over 50 draws is reported, and "HAND = 0" as a
        # map of its own.
        rng = np.random.default_rng(SEED)
        hv = hand[m]

        def _low(gen):
            o = np.lexsort((gen.random(hv.size), hv))
            z = np.zeros(hv.size, bool); z[o[:k]] = True
            return z
        low_hand = _low(rng)
        draws = [scores(_low(np.random.default_rng(SEED + i)), ref_area[m])["f1"] for i in range(1, 51)]
        methods = {"model": model,
                   "model_forecast_rain": like_fc[m] >= thr,
                   "low_hand_same_area": low_hand,
                   "hand_zero_all": hv == 0,
                   "jrc_past_water": (jrc[m] > 0) & (jrc[m] != 255),
                   "nisar_16oct_persistence": hh[m] < NISAR_DB,
                   "nisar_16oct_persistence_otsu": hh[m] < otsu}
        res = {"pixels": int(m.sum()), "area_ha": round(float(m.sum()) * PIXEL_HA, 1),
               "hand_zero_share": round(float(np.mean(hv == 0)), 3),
               "low_hand_f1_over_50_tie_draws_flooded_area": [min(draws), round(float(np.mean(draws)), 3), max(draws)],
               "references": {}}
        for rname, ref2d in (("flooded_area", ref_area), ("flooded_area_plus_trace", ref_area | ref_trace)):
            ref = ref2d[m]
            sc = {name: scores(v, ref) for name, v in methods.items()}
            rule_bases = ("low_hand_same_area", "jrc_past_water", "nisar_16oct_persistence")
            boot = block_bootstrap({k2: methods[k2] for k2 in ("model",) + rule_bases}, ref, rows, cols, "model")
            res["references"][rname] = {
                "scores": sc,
                "f1_model_minus_baseline_ci95": boot,
                "model_beats_all_three": all(sc["model"]["f1"] > sc[b]["f1"] for b in rule_bases)}
        # Extra, not part of the rule (added after the first run): a score that does not depend on how much area a
        # method maps. Average precision of each method's ranking against the main reference.
        from sklearn.metrics import average_precision_score
        ranks = {"model": like_main[m], "model_forecast_rain": like_fc[m],
                 "low_hand": -hv + 1e-6 * np.random.default_rng(SEED).random(hv.size),
                 "jrc_occurrence": np.where(jrc[m] == 255, 0, jrc[m]).astype(float),
                 "nisar_16oct_darkness": -hh[m]}
        ref = ref_area[m]
        res["average_precision_flooded_area"] = {k2: round(float(average_precision_score(ref, v)), 3) for k2, v in ranks.items()}
        res["average_precision_flooded_area"]["base_rate"] = round(float(ref.mean()), 4)
        out["sets"][sname] = res
        r0 = res["references"]["flooded_area"]
        print(sname, res["area_ha"], "ha;", {k2: v["f1"] for k2, v in r0["scores"].items()}, "beats all:", r0["model_beats_all_three"])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote", OUT / "result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
