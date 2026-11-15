"""Variants of the spatial model and their scores, as planned in docs/MODEL_IMPROVE.md.

    python -m pipeline.prediction.spatial.improve train VARIANT [VARIANT ...]    development check and final fit, no held-out pass
    python -m pipeline.prediction.spatial.improve select                        the plan's rule on development scores only
    python -m pipeline.prediction.spatial.improve holdout VARIANT [VARIANT ...]  the held-out window, once, at 20 m and 250 m
    python -m pipeline.prediction.spatial.improve table                         every held-out score side by side
    python -m pipeline.prediction.spatial.improve export CANDIDATE              the candidate's maps in the PR #33 layout
    python -m pipeline.prediction.spatial.improve nisar CANDIDATE [...]         the NISAR 28 Oct check (chosen candidate only)

A candidate is a variant (its own LightGBM model) or VARIANT+blend (its rank averaged with the terrain-only rank).
Everything is written to data/prediction/spatial/improve/ except the maps and files that export replaces.
`base` must be trained first: its terrain-only model is the one every variant is compared and blended with.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date

import lightgbm as lgb
import numpy as np
from sklearn.metrics import average_precision_score

from pipeline.config import DATA_DIR, get_site
from pipeline.ml.split import split_blocks
from pipeline.stack import site_grid

from . import HOLDOUT_END, HOLDOUT_START, SITES, export, features as F, labels, model as M, terrain
from .__main__ import (FORECAST_TARGET, MANIFEST, NISAR_AFTER, NISAR_BEFORE, NISAR_EXPORT_STACK, OUT, POOL_SIZE,
                       PRE_STORM, REPLAY_DATES, SCENARIO_LEAD_DAYS, SCENARIO_MM, SCORE_SAMPLE, STORM_DATES,
                       _cv_on_grid, _forecast_rain, _json, _site, _write_index)
from .. import manifest as manifest_mod

IMP = OUT / "improve"
VARIANTS = {
    "base": {"labels": "s1"},
    "mono": {"labels": "s1", "mono": True},
    "storm": {"labels": "s1", "storm": True},
    "neigh": {"labels": "s1", "neigh": True},
    "nisar_flag": {"labels": "s1+nisar", "sensor": True},
    "mono_storm": {"labels": "s1", "mono": True, "storm": True},
    "mono_neigh": {"labels": "s1", "mono": True, "neigh": True},
    "mono_storm_neigh": {"labels": "s1", "mono": True, "storm": True, "neigh": True},
}
MONO = ("rain_prior_7d_mm", "rain_prior_30d_mm", "rain_between_mm", "rain_between_max1d_mm")
MONO_METHOD = "intermediate"
STORM_MM, STORM_CAP = 25.0, 10.0      # a target pass counts 1 + rain_between_mm / 25 times, at most 10
BLEND_W = 0.5                         # weight of the variant's rank; the terrain-only rank gets the rest
QUANTILES = 4001                      # points of the reference distribution behind a rank
CELL_M = 250.0
STORM_MM_DEV = 60.0                   # development targets after this much rain are reported apart (not used to choose)
MONO_TOLERANCE = 0.01
METHODS = ("rain_and_state", "blend", "terrain_only", "past_wet_share")
U = np.linspace(0.0, 1.0, QUANTILES)


def _names(variant):
    o = VARIANTS[variant]
    return F.FEATURES + (F.SENSOR if o.get("sensor") else ()) + (F.NEIGH if o.get("neigh") else ())


def _params(variant):
    if not VARIANTS[variant].get("mono"):
        return None
    return {"monotone_constraints": [1 if n in MONO else 0 for n in _names(variant)],
            "monotone_constraints_method": MONO_METHOD}


def _storm_weight(X):
    r = np.nan_to_num(X[:, F.ALL.index("rain_between_mm")].astype("float64"), nan=0.0)
    return np.clip(1.0 + r / STORM_MM, 1.0, STORM_CAP)


def _sha16(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _parse(candidate):
    variant, _, extra = candidate.partition("+")
    if variant not in VARIANTS or extra not in ("", "blend"):
        raise ValueError(candidate)
    return variant, ("blend" if extra else "rain_and_state")


# ---------------------------------------------------------------- blend with the terrain-only model

def reference(score, w):
    """Weighted quantiles of a score at U: the scale a rank is read from (mid-rank of each sample)."""
    o = np.argsort(score, kind="stable")
    s, ww = score[o].astype("float64"), w[o].astype("float64")
    c = np.cumsum(ww)
    c = (c - 0.5 * ww) / c[-1]
    q = np.maximum.accumulate(np.interp(U, c, s))
    return q + np.arange(U.size) * 1e-12          # strictly increasing, so the ranks below are well defined


def blend(pm, pt, ref):
    """Average of the two ranks, read back on the variant's own likelihood scale (keeps the order of the average)."""
    u = BLEND_W * np.interp(pm, ref["model"], U) + (1.0 - BLEND_W) * np.interp(pt, ref["terrain"], U)
    return np.interp(u, U, ref["model"])


def _load_ref(path):
    with np.load(path) as z:
        return {"model": z["model"], "terrain": z["terrain"]}


# ---------------------------------------------------------------- neighbourhood of the issue-time water map

def _neigh_full(s, j):
    """(len(NEIGH), pixels of the grid) for issue pass j, from the same composite prev_state gives a pixel."""
    g = s["grid"]
    n = g.height * g.width
    state, _ = F.prev_state(lambda k: labels.to_water(np.asarray(s["stack"][k]).ravel()), s["times"], j, s["times"][j], n)
    return F.neighbourhood(state.reshape(g.height, g.width)).reshape(len(F.NEIGH), n)


def _neigh_reader(s, pixels, key):
    """neigh(j) -> (pixels, len(NEIGH)), cached on disk per site, label set and pixel pool."""
    h = hashlib.sha256(np.ascontiguousarray(pixels).tobytes()).hexdigest()[:12]
    path = terrain.static_dir(s["name"]) / f"neigh_{key.replace('+', '_')}_{h}.npz"
    mem = dict(np.load(path)) if path.exists() else {}
    n0 = len(mem)

    def get(j):
        k = f"j{j}"
        if k not in mem:
            mem[k] = np.ascontiguousarray(_neigh_full(s, j)[:, pixels].T)
        return mem[k]

    get.save = lambda: np.savez(path, **mem) if len(mem) > n0 else None
    return get


# ---------------------------------------------------------------- train (development data only)

def train(variant):
    o, names, out, params = VARIANTS[variant], _names(variant), IMP / variant, _params(variant)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(M.SEED)
    parts, manifest = [], {}
    for name in SITES:
        s = _site(name, o["labels"])
        domain = F.train_domain(s["static"])
        pool, pool_w = F.pick_pool(domain, s["wet"], s["obs"], POOL_SIZE, rng, n_fit=int(s["fit"].sum()))
        pool_water = np.stack([labels.to_water(np.asarray(s["stack"][k]).ravel()[pool]) for k in range(len(s["passes"]))])
        nb = _neigh_reader(s, pool, o["labels"]) if o.get("neigh") else None
        tab = F.build_table(pool_water, s["times"], s["days"], F.static_columns(s["static"], pool), pool_w, s["rain"], rng,
                            is_nisar=s["is_nisar"], neigh=nb)
        if nb is not None:
            nb.save()
        train_blocks, val_blocks = split_blocks(domain.shape)
        late = np.array([d >= M.DEV_SPLIT for d in s["days"]])[tab["t"]]
        nisar_target = s["is_nisar"][tab["t"]]
        tab["dev_train"] = ~late & train_blocks.ravel()[pool][tab["p"]]
        tab["dev_val"] = late & val_blocks.ravel()[pool][tab["p"]] & ~nisar_target   # checked on Sentinel-1 targets only
        tab["site"] = np.full(tab["y"].size, SITES.index(name), "int8")
        parts.append(tab)
        used = sorted(set(tab["t"].tolist()))
        between = [F.rain_features(s["rain"], date.fromisoformat(s["days"][F.issue_index(s["times"], t)]).toordinal(),
                                   date.fromisoformat(s["days"][t]).toordinal())["rain_between_mm"] for t in used]
        manifest[name] = {
            "passes_in_index": len(s["passes"]), "target_passes_used": len(used),
            "nisar_target_passes": int(sum(s["passes"][t].get("platform") == "NISAR" for t in used)),
            "first_target": s["days"][used[0]], "last_target": s["days"][used[-1]],
            "held_out_passes": int((~s["fit"]).sum()), "pool_pixels": int(pool.size), "samples": int(tab["y"].size),
            "wet_samples": int(tab["y"].sum()),
            "rain_between_mm": {"max": round(float(np.nanmax(between)), 1), "p99": round(float(np.nanpercentile(between, 99)), 1),
                                "p90": round(float(np.nanpercentile(between, 90)), 1),
                                "targets_over_100mm": int(np.sum(np.array(between) >= 100))},
            "label_granules_sha256": hashlib.sha256("\n".join(g for p in s["passes"] for g in p.get("granules", [])).encode()).hexdigest(),
        }
        print(variant, name, manifest[name], flush=True)
    T = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    X, y, w = T["X"], T["y"], T["w"]
    wfit = (w * _storm_weight(X)).astype("float32") if o.get("storm") else w
    tr, va = T["dev_train"], T["dev_val"]
    new_cand = X[:, F.ALL.index("prev_water")] == 0

    if variant == "base":     # the terrain-only comparison, trained once and shared by every variant
        t_dev = M.fit(X[tr], y[tr], w[tr], F.TERRAIN_ONLY, valid=(X[va], y[va], w[va]))
        t_rounds = int(t_dev.best_iteration)
        t_final = M.fit(X, y, w, F.TERRAIN_ONLY, rounds=t_rounds)
        t_dev.save_model(str(out / "dev_model_terrain_only.txt"))
        t_final.save_model(str(out / "model_terrain_only.txt"))
    else:
        t_dev = lgb.Booster(model_file=str(IMP / "base" / "dev_model_terrain_only.txt"))
        t_final = lgb.Booster(model_file=str(IMP / "base" / "model_terrain_only.txt"))
        t_rounds = json.loads((IMP / "base" / "training_manifest.json").read_text(encoding="utf-8"))["rounds"]["terrain_only"]

    b_dev = M.fit(X[tr], y[tr], wfit[tr], names, valid=(X[va], y[va], wfit[va]), params=params)
    rounds = int(b_dev.best_iteration)
    pm, pt = M.predict(b_dev, X[va], names), M.predict(t_dev, X[va], F.TERRAIN_ONLY)
    ref_dev = {"model": reference(M.predict(b_dev, X[tr], names), w[tr]),
               "terrain": reference(M.predict(t_dev, X[tr], F.TERRAIN_ONLY), w[tr])}
    scores = {**M.baselines(X[va]), "terrain_only": pt, "rain_and_state": pm, "blend": blend(pm, pt, ref_dev)}
    nc = new_cand[va]
    thresholds = {k: {"water": M.best_threshold(y[va], v, w[va]), "new_water": M.best_threshold(y[va][nc], v[nc], w[va][nc])}
                  for k, v in scores.items() if k != "persistence"}
    dev = {"both_sites": M.score_all(y[va], w[va], scores, nc, thresholds)}
    storm_va = np.nan_to_num(X[va][:, F.ALL.index("rain_between_mm")], nan=0.0) >= STORM_MM_DEV
    dev_storm = {}
    for i, name in enumerate(SITES):
        m = T["site"][va] == i
        dev[name] = M.score_all(y[va][m], w[va][m], {k: v[m] for k, v in scores.items()}, nc[m], thresholds)
        ms = m & storm_va
        dev_storm[name] = {"targets": int(len(set(T["t"][va][ms].tolist()))),
                           **M.score_all(y[va][ms], w[va][ms], {k: v[ms] for k, v in scores.items()}, nc[ms], thresholds)}
    selection_score = {k: round(float(np.mean([dev[n]["methods"][k]["new_water_ap"] for n in SITES])), 4)
                       for k in ("rain_and_state", "blend", "terrain_only", "past_wet_share")}

    b = M.fit(X, y, wfit, names, rounds=rounds, params=params)
    b.save_model(str(out / "model.txt"))
    b_dev.save_model(str(out / "dev_model.txt"))
    ref = {"model": reference(M.predict(b, X, names), w), "terrain": reference(M.predict(t_final, X, F.TERRAIN_ONLY), w)}
    np.savez(out / "blend_reference.npz", **ref)
    np.savez(out / "blend_reference_dev.npz", **ref_dev)
    gain = b.feature_importance("gain")
    importance = {n: round(float(g / gain.sum()), 4) for n, g in sorted(zip(names, gain), key=lambda x: -x[1])}

    _json({"variant": variant, "options": o, "features": list(names), "terrain_only_features": list(F.TERRAIN_ONLY),
           "categorical": list(F.CATEGORICAL), "units": {k: F.UNITS[k] for k in names if k in F.UNITS},
           "monotone": {"features": list(MONO), "method": MONO_METHOD} if o.get("mono") else None,
           "storm_weight": f"1 + rain_between_mm / {STORM_MM:g}, at most {STORM_CAP:g}" if o.get("storm") else None,
           "neighbourhood_windows_px": list(F.NEIGH_SIZES) if o.get("neigh") else None,
           "target": "water (DSWx-S1 class 1 or 3) at the target pass; 0 = class 0; other classes are not used",
           "timing": {"min_lead_days": F.MIN_LEAD_DAYS, "max_lead_days": F.MAX_LEAD_DAYS, "max_observation_age_days": F.MAX_OBS_AGE_DAYS},
           "grid": "pipeline.stack.site_grid, EPSG:32630, 20 m"}, out / "feature_schema.json")
    _json({"variant": variant, "options": o, "holdout": {"start": HOLDOUT_START, "end": HOLDOUT_END, "sites": list(SITES)},
           "labels": "OPERA DSWx-S1 B01_WTR, newest reprocessing per tile, data/raw/dswx_history"
                     + ("; plus the team's NISAR water labels, data/labels_nisar" if o["labels"] != "s1" else ""),
           "params": {**M.PARAMS, **(params or {})}, "rounds": {"terrain_only": t_rounds, "rain_and_state": rounds},
           "sites": manifest}, out / "training_manifest.json")
    _json({"variant": variant,
           "split": {"train": f"targets before {M.DEV_SPLIT} on training blocks",
                     "check": f"Sentinel-1 targets from {M.DEV_SPLIT} to the held-out window on held-back 1 km blocks",
                     "n_train": int(tr.sum()), "n_check": int(va.sum())},
           "reading": "water_ap / new_water_ap = weighted average precision; new water = samples dry at the issue pass. "
                      "rain_and_state = this variant's model; blend = its rank averaged with the terrain-only rank (weight 0.5); "
                      "terrain_only = the base terrain-only model. selection_score = mean over the two sites of new_water_ap.",
           "selection_score": selection_score, "thresholds": thresholds, "scores": dev,
           "development_storm_targets": {"rule": f"development check targets with rain_between_mm >= {STORM_MM_DEV:g}, reported only",
                                         **dev_storm},
           "importance_gain_share": importance}, out / "development_metrics.json")
    print(variant, "rounds", rounds, "selection score", selection_score, flush=True)
    for k, v in dev["both_sites"]["methods"].items():
        print(f"  dev {k:16s} water AP {v['water_ap']}  new-water AP {v['new_water_ap']}")


# ---------------------------------------------------------------- select (development scores only)

def select(_variants):
    rows = []
    for variant in VARIANTS:
        path = IMP / variant / "development_metrics.json"
        if not path.exists():
            continue
        sc = json.loads(path.read_text(encoding="utf-8"))["selection_score"]
        for key, suffix in (("rain_and_state", ""), ("blend", "+blend")):
            rows.append({"candidate": variant + suffix, "development_score": sc[key], "monotone_rain": bool(VARIANTS[variant].get("mono")),
                         "changes": sum(bool(VARIANTS[variant].get(k)) for k in ("mono", "storm", "neigh", "sensor")) + bool(suffix)})
    best = max(r["development_score"] for r in rows)
    order = lambda r: (r["development_score"], -r["changes"])   # noqa: E731
    mono = [r for r in rows if r["monotone_rain"] and r["development_score"] >= best - MONO_TOLERANCE]
    chosen = max(mono, key=order) if mono else max(rows, key=order)
    doc = {"rule": "docs/MODEL_IMPROVE.md, selection rule: mean over the two sites of the development-check new-water average "
                   f"precision at 20 m; a monotone-rain candidate within {MONO_TOLERANCE} of the best wins; ties to fewer changes",
           "best_development_score": best, "chosen": chosen["candidate"],
           "trained_variants": sorted({r["candidate"].split("+")[0] for r in rows}),
           "candidates": sorted(rows, key=lambda r: -r["development_score"]),
           "held_out_scored_before_this_file": False}
    _json(doc, IMP / "selection.json")
    for r in doc["candidates"]:
        print(f"{r['candidate']:24s} {r['development_score']:.4f}{'  monotone' if r['monotone_rain'] else ''}")
    print("chosen:", chosen["candidate"])


# ---------------------------------------------------------------- held-out window (scored once)

def _models(variant):
    d = IMP / variant
    return {"variant": variant, "names": _names(variant), "neigh": bool(VARIANTS[variant].get("neigh")),
            "model": lgb.Booster(model_file=str(d / "model.txt")),
            "terrain": lgb.Booster(model_file=str(IMP / "base" / "model_terrain_only.txt")),
            "ref": _load_ref(d / "blend_reference.npz")}


def _cells(grid, idx):
    """250 m cell of every pixel of idx: the square of the lattice from the grid corner that holds its centre."""
    k = CELL_M / abs(grid.transform.a)
    r, c = np.divmod(idx, grid.width)
    ncol = int(np.floor((grid.width - 0.5) / k)) + 1
    return (np.floor((r + 0.5) / k).astype("int64") * ncol + np.floor((c + 0.5) / k).astype("int64"))


def _context(s, rng):
    st, grid = s["static"], s["grid"]
    idx = np.flatnonzero((st["land"] & np.isfinite(st["hand_m"])).ravel())
    scoring = F.train_domain(st).ravel()[idx]
    sample = np.zeros(idx.size, bool)
    sample[rng.choice(np.flatnonzero(scoring), size=min(SCORE_SAMPLE, int(scoring.sum())), replace=False)] = True
    return {"idx": idx, "static_cols": F.static_columns(st, idx), "freq": F.wet_frequency(s["wet"].ravel()[idx], s["obs"].ravel()[idx]),
            "scoring": scoring, "sample": sample, "cell": _cells(grid, idx), "shape": (grid.height, grid.width)}


def _scores(s, ctx, models, j, target_time, target_day, lead, rf, target_nisar=False):
    idx = ctx["idx"]
    src = np.empty(idx.size, dtype="int64")
    state, age = F.prev_state(lambda k: labels.to_water(np.asarray(s["stack"][k]).ravel()[idx]), s["times"], j, target_time,
                              idx.size, source=src)
    prev_nisar = np.where(src >= 0, s["is_nisar"][np.maximum(src, 0)], False)
    nb = np.ascontiguousarray(_neigh_full(s, j)[:, idx].T) if models["neigh"] else None
    X = F.assemble(ctx["static_cols"], ctx["freq"], target_day, lead, rf, state, age, target_nisar=target_nisar,
                   prev_nisar=prev_nisar, neigh=nb)
    pm = M.predict(models["model"], X, models["names"])
    pt = M.predict(models["terrain"], X, F.TERRAIN_ONLY)
    return {"rain_and_state": pm, "blend": blend(pm, pt, models["ref"]), "terrain_only": pt, **M.baselines(X)}, state


def _cell_pass(cell, cand, lab, scores, thresholds, methods=METHODS):
    """Per 250 m cell with candidates: candidates, new water, mean score and marked candidates of every method."""
    cc = cell[cand]
    n = np.bincount(cc).astype("float64")
    keep = n > 0
    out = {"n": n[keep], "new": np.bincount(cc, weights=(lab[cand] == 1).astype("float64"))[keep], "mean": {}, "marked": {}}
    for k in methods:
        v = scores[k][cand].astype("float64")
        out["mean"][k] = np.bincount(cc, weights=v)[keep] / n[keep]
        out["marked"][k] = np.bincount(cc, weights=(v >= thresholds[k]["new_water"]).astype("float64"))[keep]
    return out


def _cell_scores(n, new, mean, marked):
    """Average precision with every pixel at its cell's mean score; hit rate and false alarms from min(marked, observed)."""
    neg = n - new
    yy = np.r_[np.ones(new.size), np.zeros(neg.size)]
    ss, ww = np.r_[mean, mean], np.r_[new, neg]
    m = ww > 0
    ap = None if new.sum() == 0 or neg.sum() == 0 else round(float(average_precision_score(yy[m], ss[m], sample_weight=ww[m])), 4)
    found = float(np.minimum(marked, new).sum())
    prec = found / marked.sum() if marked.sum() else None
    return {"new_water_ap": ap, "hit_rate": round(found / new.sum(), 4) if new.sum() else None,
            "precision": None if prec is None else round(prec, 4),
            "false_alarm_ratio": None if prec is None else round(1.0 - prec, 4),
            "cells": int(n.size), "observed_new_water_ha": round(float(new.sum()) * export.PIXEL_HA, 1),
            "marked_ha": round(float(marked.sum()) * export.PIXEL_HA, 1)}


def _counts_at_threshold(y, new, s, thr):
    pred = s >= thr
    return np.array([(pred & (y == 1) & new).sum(), (pred & (y == 0) & new).sum(), (~pred & (y == 1) & new).sum()], "float64")


def _scenario_area(st, ctx, score, state, thr):
    ev = export.evidence(st, ctx["freq"], state, ctx["idx"], ctx["shape"]).ravel()[ctx["idx"]]
    trusted = ev == 0
    return {"likely_water": round(float((score[trusted] >= thr["water"]).sum()) * export.PIXEL_HA, 1),
            "likely_new_water": round(float((score[trusted & (state == 0)] >= thr["new_water"]).sum()) * export.PIXEL_HA, 1)}


def holdout(variant):
    models, vdir = _models(variant), IMP / variant
    thresholds = json.loads((vdir / "development_metrics.json").read_text(encoding="utf-8"))["thresholds"]
    rng = np.random.default_rng(M.SEED + 1)
    report = {}
    for name in SITES:
        s = _site(name, VARIANTS[variant]["labels"])
        ctx = _context(s, rng)
        per_pass, pooled = [], {"y": [], "new": [], "s": {}}
        cells = {"n": [], "new": [], "mean": {k: [] for k in METHODS}, "marked": {k: [] for k in METHODS}}
        counts = {k: np.zeros(3) for k in METHODS}
        for t in np.flatnonzero(~s["fit"]):
            j = F.issue_index(s["times"], t)
            if j is None or s["passes"][t].get("platform") == "NISAR":
                continue
            target_day = date.fromisoformat(s["days"][t]).toordinal()
            rf = F.rain_features(s["rain"], date.fromisoformat(s["days"][j]).toordinal(), target_day)
            lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
            sc, state = _scores(s, ctx, models, j, s["times"][t], target_day, lead, rf)
            lab = labels.to_water(np.asarray(s["stack"][t]).ravel()[ctx["idx"]])
            ok = ctx["scoring"] & (lab != labels.UNKNOWN)
            y, new = lab[ok], state[ok] == 0
            row = {"pass_id": s["passes"][t]["pass_id"], "date": s["days"][t], "issue_pass": s["passes"][j]["pass_id"],
                   "lead_days": round(lead, 2), **{k: round(v, 1) for k, v in rf.items()},
                   "observed_new_water_ha": round(float((new & (y == 1)).sum()) * export.PIXEL_HA, 1),
                   **M.score_all(y, np.ones(y.size, "float32"), {k: v[ok] for k, v in sc.items()}, new, thresholds)}
            c = _cell_pass(ctx["cell"], ok & (state == 0), lab, sc, thresholds)
            row["cells_250m"] = {k: _cell_scores(c["n"], c["new"], c["mean"][k], c["marked"][k]) for k in METHODS}
            per_pass.append(row)
            cells["n"].append(c["n"]); cells["new"].append(c["new"])
            for k in METHODS:
                cells["mean"][k].append(c["mean"][k]); cells["marked"][k].append(c["marked"][k])
                counts[k] += _counts_at_threshold(y, new, sc[k][ok], thresholds[k]["new_water"])
            m = ok & ctx["sample"]
            pooled["y"].append(lab[m]); pooled["new"].append(state[m] == 0)
            for k, v in sc.items():
                pooled["s"].setdefault(k, []).append(v[m].astype("float32"))
            print(variant, name, row["date"], row["pass_id"][-3:], "rain", row["rain_between_mm"], "new-water AP",
                  {k: row["methods"][k]["new_water_ap"] for k in METHODS}, flush=True)
        yp, newp = np.concatenate(pooled["y"]), np.concatenate(pooled["new"])
        n_all, new_all = np.concatenate(cells["n"]), np.concatenate(cells["new"])
        report[name] = {
            "pooled_over_held_out_passes": M.score_all(yp, np.ones(yp.size, "float32"),
                                                       {k: np.concatenate(v) for k, v in pooled["s"].items()}, newp, thresholds),
            "pooled_note": f"a fixed random sample of {int(ctx['sample'].sum())} domain pixels per pass (the PR #33 sample)",
            "pooled_250m_cells": {k: _cell_scores(n_all, new_all, np.concatenate(cells["mean"][k]), np.concatenate(cells["marked"][k]))
                                  for k in METHODS},
            "all_pixels_at_threshold_20m": {k: {"hit_rate": round(v[0] / (v[0] + v[2]), 4) if v[0] + v[2] else None,
                                                "false_alarm_ratio": round(v[1] / (v[0] + v[1]), 4) if v[0] + v[1] else None,
                                                "marked_ha": round((v[0] + v[1]) * export.PIXEL_HA, 1),
                                                "observed_new_water_ha": round((v[0] + v[2]) * export.PIXEL_HA, 1)}
                                            for k, v in counts.items()},
            "storm_passes": [p["pass_id"] for p in per_pass if p["date"] in STORM_DATES],
            "passes": per_pass}

        # the 22 Oct storm with the rain the ECMWF IFS run of the issue day forecast (cached in ifs_runs.json)
        t = next(i for i, d in enumerate(s["days"]) if d == FORECAST_TARGET)
        j = F.issue_index(s["times"], t)
        issue_day, target_day = (date.fromisoformat(s["days"][k]).toordinal() for k in (j, t))
        run = _forecast_rain(name, date.fromordinal(issue_day), target_day - issue_day)
        rain_fc = dict(s["rain"])
        rain_fc.update({date.fromisoformat(d).toordinal(): (0.0 if v is None else v) for d, v in zip(run["dates"], run["max_mm"])})
        rf = F.rain_features(rain_fc, issue_day, target_day)
        lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
        sc, state = _scores(s, ctx, models, j, s["times"][t], target_day, lead, rf)
        lab = labels.to_water(np.asarray(s["stack"][t]).ravel()[ctx["idx"]])
        ok = ctx["scoring"] & (lab != labels.UNKNOWN)
        c = _cell_pass(ctx["cell"], ok & (state == 0), lab, sc, thresholds)
        report[name]["forecast_replay"] = {
            "target_pass": s["passes"][t]["pass_id"], "issue_pass": s["passes"][j]["pass_id"], "ifs_run": run["run"],
            "forecast_rain_between_mm": round(rf["rain_between_mm"], 1),
            **M.score_all(lab[ok], np.ones(int(ok.sum()), "float32"), {k: v[ok] for k, v in sc.items()}, state[ok] == 0, thresholds),
            "cells_250m": {k: _cell_scores(c["n"], c["new"], c["mean"][k], c["marked"][k]) for k in METHODS}}

        # rain scenarios from the latest water map: does the likely new water grow with the rain?
        j = len(s["passes"]) - 1
        issue_day = date.fromisoformat(s["days"][j]).toordinal()
        target_day, target_time = issue_day + SCENARIO_LEAD_DAYS, s["times"][j] + np.timedelta64(SCENARIO_LEAD_DAYS, "D")
        prior = F.rain_features(s["rain"], issue_day, issue_day)
        scen = {k: {} for k in ("rain_and_state", "blend")}
        for mm in SCENARIO_MM:
            rf = {**prior, "rain_between_mm": float(mm), "rain_between_max1d_mm": mm * 0.6, "days_since_rain_peak": 2.0}
            sc, state = _scores(s, ctx, models, j, target_time, target_day, float(SCENARIO_LEAD_DAYS), rf)
            for k in scen:
                scen[k][f"{mm:03d}mm"] = _scenario_area(s["static"], ctx, sc[k], state, thresholds[k])
        report[name]["scenarios"] = {k: {**v, "new_water_grows_with_rain": bool(np.all(np.diff(
            [v[f"{mm:03d}mm"]["likely_new_water"] for mm in SCENARIO_MM]) >= 0))} for k, v in scen.items()}
        print(variant, name, "pooled new-water AP 20 m",
              {k: report[name]["pooled_over_held_out_passes"]["methods"][k]["new_water_ap"] for k in METHODS},
              "250 m", {k: report[name]["pooled_250m_cells"][k]["new_water_ap"] for k in METHODS},
              "scenarios", {k: [v[f"{mm:03d}mm"]["likely_new_water"] for mm in SCENARIO_MM] for k, v in scen.items()}, flush=True)
    _json({"reading": "Held-out Sentinel-1 passes of 15 Oct to 15 Nov 2026, scored once after the choice of "
                      "improve/selection.json, against the Sentinel-1 map of the same pass, on the training domain. "
                      "New water = pixels dry at the issue pass. 250 m cells: every pixel takes its cell's mean score; "
                      "hit rate and false alarms count min(marked, observed) per cell.",
           "variant": variant, "thresholds_frozen_from": f"improve/{variant}/development_metrics.json", "sites": report},
          vdir / "holdout_s1_metrics.json")


# ---------------------------------------------------------------- results table

def table(_variants):
    rows = []
    sel = json.loads((IMP / "selection.json").read_text(encoding="utf-8"))
    devs = {c["candidate"]: c["development_score"] for c in sel["candidates"]}
    for variant in VARIANTS:
        path = IMP / variant / "holdout_s1_metrics.json"
        if not path.exists():
            continue
        sites = json.loads(path.read_text(encoding="utf-8"))["sites"]
        keys = (("rain_and_state", variant), ("blend", variant + "+blend"))
        if variant == "base":
            keys += (("terrain_only", "terrain only (baseline)"), ("past_wet_share", "past wet share (baseline)"))
        for key, label in keys:
            row = {"candidate": label, "development_score": devs.get(label), "sites": {}}
            for name, r in sites.items():
                p20 = r["pooled_over_held_out_passes"]["methods"][key]
                t20 = p20["new_water_at_threshold"]
                c250 = r["pooled_250m_cells"][key]
                storm = [p["methods"][key]["new_water_ap"] for p in r["passes"] if p["date"] in STORM_DATES]
                row["sites"][name] = {
                    "ap_20m": p20["new_water_ap"], "hit_20m": t20["recall"],
                    "false_alarms_20m": None if t20["precision"] is None else round(1 - t20["precision"], 4),
                    "ap_250m": c250["new_water_ap"], "hit_250m": c250["hit_rate"], "false_alarms_250m": c250["false_alarm_ratio"],
                    "storm_passes_ap_20m_mean": round(float(np.mean(storm)), 4) if storm else None,
                    "dana_22oct_ap_20m": next((p["methods"][key]["new_water_ap"] for p in r["passes"] if p["date"] == "2026-10-22"), None),
                    "forecast_22oct_ap_20m": r["forecast_replay"]["methods"][key]["new_water_ap"],
                    "scenarios_new_water_ha": [r["scenarios"][key][f"{mm:03d}mm"]["likely_new_water"] for mm in SCENARIO_MM]
                    if key in r.get("scenarios", {}) else None}
            rows.append(row)
    _json({"reading": "Held-out window 15 Oct to 15 Nov 2026, new water, against Sentinel-1 DSWx-S1. ap = average precision, "
                      "hit = share of the new water marked at the frozen threshold, false_alarms = share of the marked area "
                      "that stayed dry. 20 m: the PR #33 sample of 200,000 domain pixels per pass, pooled over the 18 passes. "
                      "250 m: all candidate pixels, every pixel at its cell's mean score. development_score chose the variant.",
           "chosen": sel["chosen"], "rows": rows}, IMP / "results.json")
    (IMP / "results.md").write_text(_markdown(rows, sel["chosen"]), encoding="utf-8")
    for r in rows:
        a, p = r["sites"].get("albufera", {}), r["sites"].get("pego_oliva", {})
        print(f"{r['candidate']:28s} dev {r['development_score'] if r['development_score'] is not None else '':<7} "
              f"Alb 20m {a.get('ap_20m')} hit {a.get('hit_20m')} fa {a.get('false_alarms_20m')} | 250m {a.get('ap_250m')} "
              f"hit {a.get('hit_250m')} fa {a.get('false_alarms_250m')} || Pego 20m {p.get('ap_20m')} hit {p.get('hit_20m')} "
              f"fa {p.get('false_alarms_20m')} | 250m {p.get('ap_250m')} hit {p.get('hit_250m')} fa {p.get('false_alarms_250m')}")


def _markdown(rows, chosen):
    f3 = lambda v: "" if v is None else f"{v:.3f}"         # noqa: E731
    pc = lambda v: "" if v is None else f"{100 * v:.0f} %"  # noqa: E731
    name = lambda r: f"**{r['candidate']}** (chosen)" if r["candidate"] == chosen else r["candidate"]   # noqa: E731
    out = []
    for scale, title in (("20m", "20 m pixels"), ("250m", "250 m cells")):
        out += [f"**Held-out new water, {title}** (AP = average precision; hit and false alarms at the frozen threshold)", "",
                "| candidate | development score | Albufera AP | hit | false alarms | Pego-Oliva AP | hit | false alarms |",
                "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            a, p = r["sites"]["albufera"], r["sites"]["pego_oliva"]
            out.append(f"| {name(r)} | {f3(r['development_score'])} | {f3(a['ap_' + scale])} | {pc(a['hit_' + scale])} | "
                       f"{pc(a['false_alarms_' + scale])} | {f3(p['ap_' + scale])} | {pc(p['hit_' + scale])} | {pc(p['false_alarms_' + scale])} |")
        out.append("")
    out += ["**The storm, 20 m** (22 Oct = first Sentinel-1 pass after the DANA rain; forecast = the same pass with the rain the "
            "IFS run of the issue day forecast; scenarios = likely new water in ha at 0, 50, 100 and 200 mm)", "",
            "| candidate | Albufera 22 Oct | Albufera forecast | Albufera scenarios | Pego-Oliva 22 Oct | Pego-Oliva forecast | Pego-Oliva scenarios |",
            "|---|---|---|---|---|---|---|"]
    for r in rows:
        a, p = r["sites"]["albufera"], r["sites"]["pego_oliva"]
        sc = lambda v: "" if v is None else " / ".join(f"{x:,.0f}" for x in v)   # noqa: E731
        out.append(f"| {name(r)} | {f3(a['dana_22oct_ap_20m'])} | {f3(a['forecast_22oct_ap_20m'])} | {sc(a['scenarios_new_water_ha'])} | "
                   f"{f3(p['dana_22oct_ap_20m'])} | {f3(p['forecast_22oct_ap_20m'])} | {sc(p['scenarios_new_water_ha'])} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- export the chosen candidate (PR #33 layout)

def _nisar_targets(name):
    """(stack, target time, NISAR 'after' entry, NISAR 'before' entry) of the 28 Oct NISAR passes in data/cv."""
    cv = {(e["site"], e["stack"], e["date"]): e for e in manifest_mod.read(MANIFEST) if e.get("model") == "cv" and e.get("layer") == "water"}
    out = []
    for (site, stack, day), entry in sorted(cv.items()):
        before = cv.get((name, stack, NISAR_BEFORE))
        if site != name or day != NISAR_AFTER or before is None:
            continue
        stamp = entry["source"]["granule_ur"].split("_")[-7]
        out.append((stack, np.datetime64(f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:11]}:{stamp[11:13]}:{stamp[13:15]}"), entry, before))
    return out


def _models_in(variant, d):
    t = d / "model_terrain_only.txt"
    return {"variant": variant, "names": _names(variant), "neigh": bool(VARIANTS[variant].get("neigh")),
            "model": lgb.Booster(model_file=str(d / "model.txt")),
            "terrain": lgb.Booster(model_file=str(t if t.exists() else IMP / "base" / "model_terrain_only.txt")),
            "ref": _load_ref(d / "blend_reference.npz")}


def _mmu_chosen():
    path = IMP / "mmu_selection.json"
    chosen = json.loads(path.read_text(encoding="utf-8"))["chosen"] if path.exists() else None
    return None if not chosen else (int(chosen[0]), bool(chosen[1]))


def export_maps(candidate, root=None, sites=SITES, model_dir=None, setting="auto", label=None, status=None):
    """The candidate's maps in the PR #33 layout: in data/prediction/spatial (root None, with index.json and the
    manifest) or in another folder (its own index.json). setting = the minimum mapping unit (auto: the one of
    improve/mmu_selection.json, if any)."""
    variant, key = _parse(candidate)
    vdir = IMP / variant
    mdir = vdir if model_dir is None else model_dir
    models = _models(variant) if model_dir is None else _models_in(variant, mdir)
    thresholds = json.loads((vdir / "development_metrics.json").read_text(encoding="utf-8"))["thresholds"]
    thr = thresholds[key]
    setting = _mmu_chosen() if setting == "auto" else setting
    out_root = OUT if root is None else root
    model_sha = _sha16(mdir / "model.txt")
    held = json.loads((mdir / "holdout_s1_metrics.json").read_text(encoding="utf-8"))["sites"]
    rng = np.random.default_rng(M.SEED + 1)
    index = []
    mmu_rule = None if setting is None else {
        "min_patch_px": setting[0], "majority_3x3": setting[1], "chosen_in": "data/prediction/spatial/improve/mmu_selection.json",
        "rule": f"likely new water patches (8-connected, dry on the issue map) smaller than {setting[0]} pixels"
                + (", after a 3 x 3 majority test," if setting[1] else "")
                + f" are set {MMU_BELOW} under the new-water threshold in both likelihood maps"}
    for name in SITES:
        if name not in sites:
            continue
        s = _site(name, VARIANTS[variant]["labels"])
        st, grid = s["static"], s["grid"]
        ctx = _context(s, rng)
        perm = st["permanent"].ravel()[ctx["idx"]]
        common = {"site": name, "model": "spatial water likelihood (LightGBM)", "variant": label or candidate, "exported_score": key,
                  "model_sha256_16": model_sha,
                  "rain_source": "Open-Meteo, ECMWF IFS 9 km, wettest lattice point of the site per day",
                  "holdout": {"start": HOLDOUT_START, "end": HOLDOUT_END},
                  "validation_status": status or ("retrospective check on the held-out October 2026 window against Sentinel-1 maps "
                                                  "(data/prediction/spatial/improve); not yet scored against Copernicus EMSR935")}

        def write(sid, sc, state, meta, entry):
            score, drop = _mmu_apply(sc[key], state, perm, ctx["idx"], ctx["shape"], thr["new_water"], setting)
            extra = {} if mmu_rule is None else {"minimum_mapping_unit": {**mmu_rule, "dropped_ha": round(float(drop.sum()) * export.PIXEL_HA, 1)}}
            ev = export.evidence(st, ctx["freq"], state, ctx["idx"], ctx["shape"])
            doc = export.write(out_root / name / sid, grid, score, state, ev, ctx["idx"], {**common, "scenario_id": sid, **meta, **extra}, thr)
            index.append({"site": name, "scenario_id": sid, **entry, "dir": f"data/prediction/spatial/{name}/{sid}", "area_ha": doc["area_ha"]})
            print(name, sid, doc["area_ha"], extra.get("minimum_mapping_unit", {}).get("dropped_ha"), flush=True)

        def check(row_methods):
            return {k: row_methods[k] for k in ("rain_and_state", "blend", "terrain_only", "past_wet_share")}

        done = set()
        for t in np.flatnonzero(~s["fit"]):
            j = F.issue_index(s["times"], t)
            if j is None or s["passes"][t].get("platform") == "NISAR" or s["days"][t] not in REPLAY_DATES or s["days"][t] in done:
                continue
            done.add(s["days"][t])
            target_day = date.fromisoformat(s["days"][t]).toordinal()
            rf = F.rain_features(s["rain"], date.fromisoformat(s["days"][j]).toordinal(), target_day)
            lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
            sc, state = _scores(s, ctx, models, j, s["times"][t], target_day, lead, rf)
            row = next(p for p in held[name]["passes"] if p["pass_id"] == s["passes"][t]["pass_id"])
            sid = f"replay_{s['days'][t]}"
            write(sid, sc, state, {"mode": "reconstruction",
                                   "mode_note": "rain between issue and target is the rain that fell (IFS archive), not a forecast",
                                   "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                                   "target_pass": s["passes"][t]["pass_id"], "target_time_utc": s["passes"][t]["begin_utc"],
                                   "lead_days": round(lead, 2), "rain": rf, "check_against_sentinel1": check(row["methods"])},
                  {"mode": "reconstruction", "target_date": s["days"][t]})

        t = next(i for i, d in enumerate(s["days"]) if d == FORECAST_TARGET)
        j = F.issue_index(s["times"], t)
        issue_day, target_day = (date.fromisoformat(s["days"][k]).toordinal() for k in (j, t))
        run = _forecast_rain(name, date.fromordinal(issue_day), target_day - issue_day)
        rain_fc = dict(s["rain"])
        rain_fc.update({date.fromisoformat(d).toordinal(): (0.0 if v is None else v) for d, v in zip(run["dates"], run["max_mm"])})
        rf_real, rf = F.rain_features(s["rain"], issue_day, target_day), F.rain_features(rain_fc, issue_day, target_day)
        lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
        sc, state = _scores(s, ctx, models, j, s["times"][t], target_day, lead, rf)
        sid = f"forecast_{FORECAST_TARGET}"
        write(sid, sc, state, {"mode": "forecast",
                               "mode_note": "rain between issue and target is what the ECMWF IFS run of the issue day (00 UTC) forecast, "
                                            "not what fell; the rain before the issue day and the water map are observations. "
                                            "The run has no daily total for its own first day, which counts as 0 mm",
                               "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                               "target_pass": s["passes"][t]["pass_id"], "target_time_utc": s["passes"][t]["begin_utc"],
                               "lead_days": round(lead, 2), "rain": rf, "ifs_run": run, "rain_that_fell": rf_real,
                               "check_against_sentinel1": check(held[name]["forecast_replay"]["methods"])},
              {"mode": "forecast", "target_date": FORECAST_TARGET})

        j = len(s["passes"]) - 1
        issue_day = date.fromisoformat(s["days"][j]).toordinal()
        target_day, target_time = issue_day + SCENARIO_LEAD_DAYS, s["times"][j] + np.timedelta64(SCENARIO_LEAD_DAYS, "D")
        prior = F.rain_features(s["rain"], issue_day, issue_day)
        top = json.loads((mdir / "training_manifest.json").read_text(encoding="utf-8"))["sites"][name]["rain_between_mm"]
        for mm in SCENARIO_MM:
            rf = {**prior, "rain_between_mm": float(mm), "rain_between_max1d_mm": mm * 0.6, "days_since_rain_peak": 2.0}
            sc, state = _scores(s, ctx, models, j, target_time, target_day, float(SCENARIO_LEAD_DAYS), rf)
            write(f"scenario_{mm:03d}mm", sc, state,
                  {"mode": "scenario",
                   "mode_note": f"hypothetical: {mm} mm at the wettest point of the site over the {SCENARIO_LEAD_DAYS} days after the "
                                "latest water map, 60 % of it on one day, two days before the target",
                   "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                   "target_time_utc": str(target_time) + "Z", "lead_days": float(SCENARIO_LEAD_DAYS), "rain": rf,
                   "rain_seen_in_training": {**top, "inside_training_range": bool(mm <= top["max"])}},
                  {"mode": "scenario", "rain_mm": mm})

        for stack, target_time, entry, _before in _nisar_targets(name):
            if stack != NISAR_EXPORT_STACK:
                continue
            j = F.issue_before(s["times"], target_time, not_after=PRE_STORM)
            target_day = date.fromisoformat(NISAR_AFTER).toordinal()
            rf = F.rain_features(s["rain"], date.fromisoformat(s["days"][j]).toordinal(), target_day)
            lead = float((target_time - s["times"][j]) / np.timedelta64(1, "D"))
            sc, state = _scores(s, ctx, models, j, target_time, target_day, lead, rf, target_nisar=bool(VARIANTS[variant].get("sensor")))
            write(f"replay_{NISAR_AFTER}_prestorm", sc, state,
                  {"mode": "reconstruction",
                   "mode_note": "issued from the last Sentinel-1 map before the rain of 18 and 19 Oct, for the NISAR "
                                "pass of 28 Oct; the rain in between is the rain that fell (IFS archive), not a forecast",
                   "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                   "target_time_utc": str(target_time) + "Z", "target_nisar_granule": entry["source"]["granule_ur"],
                   "lead_days": round(lead, 2), "rain": rf,
                   "validation_status": "checked against the NISAR water map of the target pass, see nisar_check.json"},
                  {"mode": "reconstruction", "target_date": NISAR_AFTER})

    out_root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mdir / "model.txt", out_root / "model.txt")
    t_src = mdir / "model_terrain_only.txt"
    shutil.copyfile(t_src if t_src.exists() else IMP / "base" / "model_terrain_only.txt", out_root / "model_terrain_only.txt")
    for fname in ("feature_schema.json", "training_manifest.json", "holdout_s1_metrics.json"):
        shutil.copyfile(mdir / fname if (mdir / fname).exists() else vdir / fname, out_root / fname)
    dev = json.loads((vdir / "development_metrics.json").read_text(encoding="utf-8"))
    dev["thresholds"] = {**thresholds, "rain_and_state": thr, "model_alone": thresholds["rain_and_state"]}
    dev["exported"] = {"candidate": label or candidate, "score": key, "thresholds": thr, "minimum_mapping_unit": mmu_rule,
                       "models_from": mdir.relative_to(DATA_DIR.parent).as_posix(),
                       "note": f"The exported maps hold the '{key}' score of {candidate}. thresholds.rain_and_state holds that score's "
                               "frozen thresholds (as in PR #33, where it named the model behind the maps); thresholds.model_alone "
                               f"are those of the {variant} model on its own. In scores, methods.rain_and_state is the model on its own "
                               "and methods.blend the blend."}
    _json(dev, out_root / "development_metrics.json")
    if root is None:
        _write_index(index, lambda e: True)
    else:
        _json({"model_sha256_16": model_sha, "candidate": label or candidate, "scenarios": index}, out_root / "index.json")


# ---------------------------------------------------------------- the NISAR 28 Oct check (chosen candidate only)

def nisar(candidate):
    """Score the pre-storm replay for the NISAR pass of 28 Oct against two NISAR water maps, after the choice was made.

    1. the team's NISAR change layer of PR #35 (data/labels_nisar/<site>_066_D_069/dana_2026-10-16_2026-10-28.tif:
       2 new open water, 0 dry on both dates; 1, 3, 4 and 255 are not candidates), on the model's domain;
    2. the data/cv water maps of PR #33's nisar step (dry on 16 Oct, water on 28 Oct).
    The exported map (export) must have been written first; the 2026-10-28 prestorm map of data/prediction/spatial is read.
    """
    variant, key = _parse(candidate)
    models, sensor = _models(variant), bool(VARIANTS[variant].get("sensor"))
    thresholds = json.loads((IMP / variant / "development_metrics.json").read_text(encoding="utf-8"))["thresholds"]
    report_cv = {}
    for name in SITES:   # 2. the PR #33 check against the data/cv maps, for the exported model
        s = _site(name, VARIANTS[variant]["labels"])
        ctx = _context(s, np.random.default_rng(M.SEED + 1))
        for stack, target_time, entry, before in _nisar_targets(name):
            after_map = _cv_on_grid(DATA_DIR.parent / entry["file"], s["grid"]).ravel()[ctx["idx"]]
            before_map = _cv_on_grid(DATA_DIR.parent / before["file"], s["grid"]).ravel()[ctx["idx"]]
            ok = ctx["scoring"] & (after_map != 255) & (before_map != 255)
            y, dry_before = after_map[ok], before_map[ok] == 0
            target_day = date.fromisoformat(NISAR_AFTER).toordinal()
            runs = {}
            for label, not_after in (("issued_before_storm", PRE_STORM), ("issued_after_storm", None)):
                j = F.issue_before(s["times"], target_time, not_after=not_after)
                if j is None:
                    continue
                rf = F.rain_features(s["rain"], date.fromisoformat(s["days"][j]).toordinal(), target_day)
                lead = float((target_time - s["times"][j]) / np.timedelta64(1, "D"))
                sc, _state = _scores(s, ctx, models, j, target_time, target_day, lead, rf, target_nisar=sensor)
                runs[label] = {"issue_pass": s["passes"][j]["pass_id"], "lead_days": round(lead, 2), **{k: round(v, 1) for k, v in rf.items()},
                               **M.score_all(y, np.ones(y.size, "float32"), {k: v[ok] for k, v in sc.items()}, dry_before, thresholds)}
                print(name, stack, label, {k: (v["water_ap"], v["new_water_ap"]) for k, v in runs[label]["methods"].items()}, flush=True)
            report_cv.setdefault(name, {})[stack] = {
                "nisar_after": entry["file"], "nisar_before": before["file"], "target_time_utc": str(target_time) + "Z",
                "scored_ha": round(float(ok.sum()) * export.PIXEL_HA, 1), "nisar_water_ha": round(float(y.sum()) * export.PIXEL_HA, 1),
                "nisar_new_water_ha": round(float((y[dry_before] == 1).sum()) * export.PIXEL_HA, 1), **runs}
    _json({"reading": "The model never saw a NISAR map. Here its replays for the NISAR pass of 28 Oct 2026 are scored against the "
                      "team's NISAR water map of that pass (data/cv). 'New water' = dry in the NISAR map of 16 Oct, water on 28 Oct. "
                      "issued_before_storm starts from the last Sentinel-1 map before the rain; issued_after_storm from a map 3 to 5 "
                      "days before the target, when the flood was already visible. (water_ap, new_water_ap) = average precision. "
                      f"The exported score is '{key}' of candidate {candidate}; computed after the choice of improve/selection.json.",
           "caution": "The NISAR map comes from a model trained with Sentinel-1 labels at Albufera, so Albufera is not an independent "
                      "check. Pego-Oliva was a test site of that model.",
           "variant": candidate, "thresholds_frozen_from": "development_metrics.json", "sites": report_cv}, OUT / "nisar_check.json")

    out = {"candidate": candidate, "reading": DANA_READING, "sites": {}}
    for name in SITES:   # 1. the PR #35 change layer, read from the exported pre-storm map
        out["sites"][name] = dana_check(name, OUT / name / f"replay_{NISAR_AFTER}_prestorm")
        print(name, json.dumps(out["sites"][name]), flush=True)
    _json(out, IMP / f"nisar_check_{candidate.replace('+', '_')}.json")


DANA_READING = ("hit_rate = share of NISAR's new open water (PR #35 change layer, code 2) that the map marks at its frozen "
                "new-water threshold; precision = share of the marked pixels that NISAR saw as new open water. Pixels: the "
                "model's domain where the pre-storm map has a new-water likelihood (dry on the issue map). all_assessed = "
                "NISAR codes 0 to 3 (everything NISAR compared except permanent water: water on both dates and water gone "
                "count as misses of 'new'), the protocol of the team's first check (b4c69d9: 26 % and 15 %); "
                "dry_before = codes 0 and 2 only (NISAR also dry on 16 Oct)")


def dana_check(name, folder):
    """The pre-storm replay in folder against the PR #35 NISAR change layer of 16 to 28 Oct (track 066 D)."""
    import rasterio
    doc = json.loads((folder / "forecast.json").read_text(encoding="utf-8"))
    with rasterio.open(folder / "new_water_likelihood_utm.tif") as src:
        new = src.read(1)
    with rasterio.open(folder / "evidence_utm.tif") as src:
        ev = src.read(1)
    dom = F.train_domain(F.load_static(name))
    thr = doc["thresholds"]["new_water"]
    res = {"map": folder.as_posix(), "threshold_new_water": thr,
           "evidence_0_share_of_scored": round(float((ev[dom & np.isfinite(new)] == 0).mean()), 4)}
    dana = DATA_DIR / "labels_nisar" / f"{name}_{NISAR_EXPORT_STACK}" / f"dana_{NISAR_BEFORE}_{NISAR_AFTER}.tif"
    with rasterio.open(dana) as src:
        code = src.read(1)
    for label, codes in (("all_assessed", (0, 1, 2, 3)), ("dry_before", (0, 2))):
        cand = dom & np.isin(code, codes) & np.isfinite(new)
        obs, pred = code[cand] == 2, new[cand] >= thr
        tp = float((obs & pred).sum())
        yv = obs.astype("uint8")
        res[label] = {"candidates_ha": round(float(cand.sum()) * export.PIXEL_HA, 1),
                      "nisar_new_water_ha": round(float(obs.sum()) * export.PIXEL_HA, 1),
                      "marked_ha": round(float(pred.sum()) * export.PIXEL_HA, 1),
                      "hit_rate": round(tp / obs.sum(), 4) if obs.sum() else None,
                      "precision": round(tp / pred.sum(), 4) if pred.sum() else None,
                      "new_water_ap": round(float(average_precision_score(yv, new[cand])), 4) if 0 < yv.sum() < yv.size else None}
    return res


# ---------------------------------------------------------------- amendment: variant 6, minimum mapping unit

MMU_SIZES = (0, 3, 5, 10, 25)
MMU_BELOW = 0.005           # a dropped pixel is set this far under the new-water threshold


def _mmu_settings():
    return [(n, m) for m in (False, True) for n in MMU_SIZES]


def _mmu_name(setting):
    return "none" if setting is None else f"min{setting[0]}px" + ("_majority" if setting[1] else "")


def mmu_keep(marked, size, majority):
    """Marked pixels that stay: an optional 3 x 3 majority test (at least 5 of 9 marked; it never adds a pixel), then
    8-connected patches of at least `size` pixels (size 0 or 1 keeps every patch)."""
    from scipy import ndimage
    m = marked
    if majority:
        m = m & (ndimage.convolve(m.astype("uint8"), np.ones((3, 3), "uint8"), mode="constant", cval=0) >= 5)
    if size > 1 and m.any():
        lab, _n = ndimage.label(m, structure=np.ones((3, 3), bool))
        ok = np.bincount(lab.ravel()) >= size
        ok[0] = False
        m = ok[lab]
    return m


def _mmu_apply(score, state, perm, idx, shape, thr, setting):
    """(score with the dropped pixels set MMU_BELOW under thr, drop mask). Marked = dry on the issue map, not
    permanent water, score at or above the new-water threshold."""
    drop = np.zeros(score.size, bool)
    if setting is None or (setting[0] <= 1 and not setting[1]):
        return score, drop
    marked = (state == 0) & ~perm & (score >= thr)
    grid = np.zeros(shape[0] * shape[1], bool)
    grid[idx[marked]] = True
    keep = mmu_keep(grid.reshape(shape), *setting).ravel()[idx]
    drop = marked & ~keep
    out = score.copy()
    out[drop] = np.minimum(out[drop], thr - MMU_BELOW)
    return out, drop


def _freq_up_to(s, idx, needed, passes_mask):
    """Past wet share at idx counting the passes of passes_mask up to and including each needed issue pass."""
    wet, obs, out = np.zeros(idx.size, "int32"), np.zeros(idx.size, "int32"), {}
    need = set(needed)
    for k in range(max(need) + 1):
        if passes_mask[k]:
            w = labels.to_water(np.asarray(s["stack"][k]).ravel()[idx])
            wet += w == 1
            obs += w != labels.UNKNOWN
        if k in need:
            out[k] = F.wet_frequency(wet, obs)
    return out


def _kept_all_settings(score, state, perm, idx, shape, thr):
    """{setting: kept mask at idx} for every setting of the grid, with one labelling per majority option."""
    from scipy import ndimage
    marked = (state == 0) & ~perm & (score >= thr)
    grid = np.zeros(shape[0] * shape[1], bool)
    grid[idx[marked]] = True
    grid = grid.reshape(shape)
    out = {}
    for majority in (False, True):
        m = grid & (ndimage.convolve(grid.astype("uint8"), np.ones((3, 3), "uint8"), mode="constant", cval=0) >= 5) if majority else grid
        lab, _n = ndimage.label(m, structure=np.ones((3, 3), bool))
        at = lab.ravel()[idx]
        size = np.bincount(lab.ravel())[at]
        for n in MMU_SIZES:
            out[(n, majority)] = (at > 0) & (size >= max(n, 1))
    return out


def mmu_dev(arg):
    """Choose the minimum mapping unit on development maps only (docs/MODEL_IMPROVE.md, amendment). arg =
    CANDIDATE:SITE writes improve/mmu_dev_<site>.json; mmu_select merges the two sites."""
    candidate, _, only = arg.partition(":")
    variant, key = _parse(candidate)
    vdir = IMP / variant
    thr = json.loads((vdir / "development_metrics.json").read_text(encoding="utf-8"))["thresholds"][key]["new_water"]
    models = {"variant": variant, "names": _names(variant), "neigh": bool(VARIANTS[variant].get("neigh")),
              "model": lgb.Booster(model_file=str(vdir / "dev_model.txt")),
              "terrain": lgb.Booster(model_file=str(IMP / "base" / "dev_model_terrain_only.txt")),
              "ref": _load_ref(vdir / "blend_reference_dev.npz")}
    settings = _mmu_settings()
    for name in SITES:
        if only and name != only:
            continue
        s = _site(name, VARIANTS[variant]["labels"])
        st, grid = s["static"], s["grid"]
        shape = (grid.height, grid.width)
        idx = np.flatnonzero((st["land"] & np.isfinite(st["hand_m"])).ravel())
        domain = F.train_domain(st)
        _train_blocks, val_blocks = split_blocks(domain.shape)
        counted = domain.ravel()[idx] & val_blocks.ravel()[idx]
        perm = st["permanent"].ravel()[idx]
        static_cols = F.static_columns(st, idx)
        targets = [t for t in range(len(s["passes"])) if s["fit"][t] and s["days"][t] >= M.DEV_SPLIT
                   and s["passes"][t].get("platform") != "NISAR" and F.issue_index(s["times"], t) is not None]
        freq_at = _freq_up_to(s, idx, [F.issue_index(s["times"], t) for t in targets], s["fit"])
        counts = {st_: np.zeros(4) for st_ in settings}       # tp, fp, fn, marked pixels anywhere
        for n_done, t in enumerate(targets):
            j = F.issue_index(s["times"], t)
            target_day = date.fromisoformat(s["days"][t]).toordinal()
            rf = F.rain_features(s["rain"], date.fromisoformat(s["days"][j]).toordinal(), target_day)
            lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
            sc, state = _scores(s, {"idx": idx, "static_cols": static_cols, "freq": freq_at[j]}, models, j, s["times"][t],
                                target_day, lead, rf)
            lab = labels.to_water(np.asarray(s["stack"][t]).ravel()[idx])
            ok = counted & (state == 0) & (lab != labels.UNKNOWN)
            y = lab == 1
            for setting, kept in _kept_all_settings(sc[key], state, perm, idx, shape, thr).items():
                counts[setting] += [(kept & ok & y).sum(), (kept & ok & ~y).sum(), (~kept & ok & y).sum(), kept.sum()]
            if n_done % 25 == 0:
                print(name, n_done, "of", len(targets), s["days"][t], flush=True)
        report = {"site": name, "candidate": candidate, "threshold_new_water": thr, "targets": len(targets), "settings": {}}
        for setting, (tp, fp, fn, mk) in counts.items():
            report["settings"][_mmu_name(setting)] = {
                "min_patch_px": setting[0], "majority_3x3": setting[1],
                "f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp + fp + fn else None,
                "hit_rate": round(tp / (tp + fn), 4) if tp + fn else None,
                "false_alarm_ratio": round(fp / (tp + fp), 4) if tp + fp else None,
                "tp": int(tp), "fp": int(fp), "fn": int(fn), "marked_ha_all_blocks": round(mk * export.PIXEL_HA, 1)}
        _json(report, IMP / f"mmu_dev_{name}.json")
        print(name, json.dumps(report["settings"]), flush=True)


def mmu_select(candidate):
    reports = {n: json.loads((IMP / f"mmu_dev_{n}.json").read_text(encoding="utf-8")) for n in SITES}
    rows = []
    for setting in _mmu_settings():
        nm = _mmu_name(setting)
        rows.append({"setting": nm, "min_patch_px": setting[0], "majority_3x3": setting[1],
                     "development_f1": round(float(np.mean([reports[n]["settings"][nm]["f1"] for n in SITES])), 4),
                     **{f"{n}_f1": reports[n]["settings"][nm]["f1"] for n in SITES}})
    best = max(rows, key=lambda r: (r["development_f1"], -r["min_patch_px"], -int(r["majority_3x3"])))
    chosen = None if (best["min_patch_px"] <= 1 and not best["majority_3x3"]) else [best["min_patch_px"], best["majority_3x3"]]
    _json({"rule": "docs/MODEL_IMPROVE.md, amendment, variant 6: mean over the two sites of the development new-water F1 "
                   "at 20 m on full maps of the development check targets, counted on the held-back 1 km blocks; ties to "
                   "the smaller patch size and no majority test",
           "candidate": candidate, "chosen_setting": best["setting"], "chosen": chosen,
           "settings": sorted(rows, key=lambda r: -r["development_f1"]), "sites": reports,
           "held_out_scored_before_this_file": False}, IMP / "mmu_selection.json")
    for r in sorted(rows, key=lambda r: -r["development_f1"]):
        print(f"{r['setting']:20s} {r['development_f1']:.4f}  " + "  ".join(f"{n} {r[n + '_f1']}" for n in SITES))
    print("chosen:", best["setting"])


def _six(block, method):
    """(AP, hit, false alarms) at 20 m and in 250 m cells of one method in a pooled block (or a single pass row)."""
    m20 = (block.get("pooled_over_held_out_passes") or block)["methods"][method]
    c = (block.get("pooled_250m_cells") or block.get("cells_250m"))[method]
    th = m20["new_water_at_threshold"]
    return (m20["new_water_ap"], th["recall"], None if th["precision"] is None else round(1 - th["precision"], 4),
            c["new_water_ap"], c["hit_rate"], c["false_alarm_ratio"])


def amend_table(_args):
    f3 = lambda v: "" if v is None else f"{v:.3f}"         # noqa: E731
    pc = lambda v: "" if v is None else f"{100 * v:.0f} %"  # noqa: E731
    line = lambda label, v: f"| {label} | {f3(v[0])} | {pc(v[1])} | {pc(v[2])} | {f3(v[3])} | {pc(v[4])} | {pc(v[5])} |"   # noqa: E731
    head = ["| | AP 20 m | hit | false alarms | AP 250 m | hit | false alarms |", "|---|---|---|---|---|---|---|"]
    sel = json.loads((IMP / "mmu_selection.json").read_text(encoding="utf-8"))
    out, doc = [], {"mmu_selection": sel["chosen_setting"]}
    out += ["**Variant 6, development check** (new-water F1 at 20 m on the held-back blocks of every development target, "
            "frozen threshold; the setting is chosen on the mean of the two sites)", "",
            "| setting | mean F1 | Albufera F1 | hit | false alarms | Pego-Oliva F1 | hit | false alarms |",
            "|---|---|---|---|---|---|---|---|"]
    for r in sel["settings"]:
        a, g = (sel["sites"][n]["settings"][r["setting"]] for n in SITES)
        mark = " (chosen)" if r["setting"] == sel["chosen_setting"] else ""
        out.append(f"| {r['setting']}{mark} | {r['development_f1']:.4f} | {a['f1']:.4f} | {pc(a['hit_rate'])} | {pc(a['false_alarm_ratio'])} | "
                   f"{g['f1']:.4f} | {pc(g['hit_rate'])} | {pc(g['false_alarm_ratio'])} |")
    out.append("")
    hold = json.loads((IMP / "mmu_holdout_mono_neigh_blend.json").read_text(encoding="utf-8"))
    fit = json.loads((IMP / FIT_NAME / "holdout_s1_metrics.json").read_text(encoding="utf-8"))
    setting = sel["chosen_setting"]          # the setting the maps use ('min0px' = no filter)
    with_label = f"with {hold['setting']}" + (" (not chosen, information only)" if hold.get("information_only") else "")
    out += [f"**Variant 6 on the held-out window** (`mono_neigh+blend`; {with_label}; scored once)", ""]
    for name, site in (("albufera", "Albufera"), ("pego_oliva", "Pego-Oliva")):
        h = hold["sites"][name]
        out += [f"*{site}*", ""] + head
        for blk_label, blk in (("whole window", h), ("DANA passes, 22 and 23 Oct", h["dana_passes"]),
                               ("22 Oct, forecast rain of 17 Oct", h["forecast_replay"])):
            out.append(line(f"{blk_label}: without the filter", _six(blk, "blend")))
            out.append(line(f"{blk_label}: {with_label}", _six(blk, "blend_mmu")))
            doc[f"mmu_{name}_{blk_label}"] = {"without": _six(blk, "blend"), "with": _six(blk, "blend_mmu")}
        out.append("")
    out += ["**Fit, then test** (the fit version learned from Albufera's held-out passes; Pego-Oliva never entered a fit or a "
            "choice; terrain only is the fit version's own terrain half; frozen = the chosen `mono_neigh+blend` without the "
            "October passes)", ""] + head
    cases = (("(a) Albufera, DANA passes, fitted", "albufera", "dana_passes"), ("(a) Albufera, whole window, fitted", "albufera", None),
             ("(b) Pego-Oliva, DANA passes, test", "pego_oliva", "dana_passes"), ("(b) Pego-Oliva, whole window, test", "pego_oliva", None),
             ("(c) Pego-Oliva, 22 Oct, forecast rain, test", "pego_oliva", "forecast_replay"))
    for label, name, part in cases:
        fb, hb = (fit["sites"][name] if part is None else fit["sites"][name][part]), (hold["sites"][name] if part is None else hold["sites"][name][part])
        filt = "blend_mmu" if setting != "min0px" else "blend"
        rows = [("fit version", fb, filt), ("terrain only", fb, "terrain_only"),
                ("past wet share", fb, "past_wet_share"), ("frozen, no October", hb, "blend" if setting == "min0px" or hold.get("information_only") else "blend_mmu")]
        for i, (who, blk, meth) in enumerate(rows):
            out.append(line(f"{label if i == 0 else ''} {who}".strip() if i == 0 else who, _six(blk, meth)))
            doc[f"fit_{label}_{who}"] = _six(blk, meth)
    out.append("")
    (IMP / "amendment_results.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    _json({"reading": "amend_table: (AP 20 m, hit 20 m, false alarms 20 m, AP 250 m, hit 250 m, false alarms 250 m)", **doc},
          IMP / "amendment_results.json")
    print("\n".join(out))


# ---------------------------------------------------------------- amendment: held-out check of variant 6, fit then test

WINDOW_METHODS = ("rain_and_state", "blend", "terrain_only", "past_wet_share")
FIT_NAME = "fit_albufera_oct"
FIT_SITES = ("albufera",)            # sites whose held-out passes the fit version learns from
EXPORTS = IMP / "exports"


def _window(s, ctx, models, thresholds, key, setting, perm, targets, freq_at=None, rain=None):
    """Scores on the target passes of the model alone, the blend, terrain only, past wet share and the exported score
    after the minimum mapping unit ('<key>_mmu'): per pass, pooled on the PR #33 sample (20 m), at the threshold on all
    pixels (20 m) and in 250 m cells. freq_at: past wet share per issue pass (in-sample fits); rain: other daily rain."""
    mkey = f"{key}_mmu"
    methods = WINDOW_METHODS + (mkey,)
    thr = {**thresholds, mkey: thresholds[key]}
    per_pass, pooled = [], {"y": [], "new": [], "s": {}}
    cells = {"n": [], "new": [], "mean": {k: [] for k in methods}, "marked": {k: [] for k in methods}}
    counts = {k: np.zeros(3) for k in methods}
    for t in targets:
        j = F.issue_index(s["times"], t)
        c = ctx if freq_at is None else {**ctx, "freq": freq_at[j]}
        target_day = date.fromisoformat(s["days"][t]).toordinal()
        rf = F.rain_features(s["rain"] if rain is None else rain, date.fromisoformat(s["days"][j]).toordinal(), target_day)
        lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
        sc, state = _scores(s, c, models, j, s["times"][t], target_day, lead, rf)
        sc[mkey], drop = _mmu_apply(sc[key], state, perm, ctx["idx"], ctx["shape"], thr[key]["new_water"], setting)
        lab = labels.to_water(np.asarray(s["stack"][t]).ravel()[ctx["idx"]])
        ok = ctx["scoring"] & (lab != labels.UNKNOWN)
        y, new = lab[ok], state[ok] == 0
        row = {"pass_id": s["passes"][t]["pass_id"], "date": s["days"][t], "issue_pass": s["passes"][j]["pass_id"],
               "lead_days": round(lead, 2), **{k: round(v, 1) for k, v in rf.items()},
               "observed_new_water_ha": round(float((new & (y == 1)).sum()) * export.PIXEL_HA, 1),
               "dropped_by_mmu_ha": round(float(drop.sum()) * export.PIXEL_HA, 1),
               **M.score_all(y, np.ones(y.size, "float32"), {k: sc[k][ok] for k in methods}, new, thr)}
        cp = _cell_pass(ctx["cell"], ok & (state == 0), lab, sc, thr, methods)
        row["cells_250m"] = {k: _cell_scores(cp["n"], cp["new"], cp["mean"][k], cp["marked"][k]) for k in methods}
        per_pass.append(row)
        cells["n"].append(cp["n"]); cells["new"].append(cp["new"])
        for k in methods:
            cells["mean"][k].append(cp["mean"][k]); cells["marked"][k].append(cp["marked"][k])
            counts[k] += _counts_at_threshold(y, new, sc[k][ok], thr[k]["new_water"])
        m = ok & ctx["sample"]
        pooled["y"].append(lab[m]); pooled["new"].append(state[m] == 0)
        for k in methods:
            pooled["s"].setdefault(k, []).append(sc[k][m].astype("float32"))
        print(s["name"], row["date"], row["pass_id"][-3:], "rain", row["rain_between_mm"], "new-water AP",
              {k: row["methods"][k]["new_water_ap"] for k in methods}, flush=True)
    yp, newp = np.concatenate(pooled["y"]), np.concatenate(pooled["new"])
    n_all, new_all = np.concatenate(cells["n"]), np.concatenate(cells["new"])
    return {"pooled_over_held_out_passes": M.score_all(yp, np.ones(yp.size, "float32"),
                                                       {k: np.concatenate(v) for k, v in pooled["s"].items()}, newp, thr),
            "pooled_250m_cells": {k: _cell_scores(n_all, new_all, np.concatenate(cells["mean"][k]), np.concatenate(cells["marked"][k]))
                                  for k in methods},
            "all_pixels_at_threshold_20m": {k: {"hit_rate": round(v[0] / (v[0] + v[2]), 4) if v[0] + v[2] else None,
                                                "false_alarm_ratio": round(v[1] / (v[0] + v[1]), 4) if v[0] + v[1] else None,
                                                "f1": round(2 * v[0] / (2 * v[0] + v[1] + v[2]), 4) if v.sum() else None,
                                                "marked_ha": round((v[0] + v[1]) * export.PIXEL_HA, 1),
                                                "observed_new_water_ha": round((v[0] + v[2]) * export.PIXEL_HA, 1)}
                                            for k, v in counts.items()},
            "passes": per_pass}


def _held_out_targets(s):
    return [t for t in np.flatnonzero(~s["fit"]) if F.issue_index(s["times"], t) is not None
            and s["passes"][t].get("platform") != "NISAR"]


def _forecast_rain_of(s, name):
    t = next(i for i, d in enumerate(s["days"]) if d == FORECAST_TARGET)
    j = F.issue_index(s["times"], t)
    issue_day, target_day = (date.fromisoformat(s["days"][k]).toordinal() for k in (j, t))
    run = _forecast_rain(name, date.fromordinal(issue_day), target_day - issue_day)
    rain_fc = dict(s["rain"])
    rain_fc.update({date.fromisoformat(d).toordinal(): (0.0 if v is None else v) for d, v in zip(run["dates"], run["max_mm"])})
    return t, run, rain_fc


def _window_site(s, models, thresholds, key, setting, rng, freq_mode=None):
    ctx = _context(s, rng)
    perm = s["static"]["permanent"].ravel()[ctx["idx"]]
    targets = _held_out_targets(s)
    freq_at = None
    if freq_mode == "all_passes":    # in-sample fit: the past wet share counts every pass up to the issue pass
        t_fc = next(i for i, d in enumerate(s["days"]) if d == FORECAST_TARGET)
        freq_at = _freq_up_to(s, ctx["idx"], [F.issue_index(s["times"], t) for t in targets + [t_fc]], np.ones(len(s["days"]), bool))
    r = _window(s, ctx, models, thresholds, key, setting, perm, targets, freq_at=freq_at)
    storm = [t for t in targets if s["days"][t] in STORM_DATES]
    dana = _window(s, ctx, models, thresholds, key, setting, perm, storm, freq_at=freq_at)
    r["dana_passes"] = {k: dana[k] for k in ("pooled_over_held_out_passes", "pooled_250m_cells", "all_pixels_at_threshold_20m")}
    r["dana_passes"]["passes"] = [p["pass_id"] for p in dana["passes"]]
    t, run, rain_fc = _forecast_rain_of(s, s["name"])
    fr = _window(s, ctx, models, thresholds, key, setting, perm, [t], freq_at=freq_at, rain=rain_fc)
    r["forecast_replay"] = {**fr["passes"][0], "ifs_run": run["run"], "all_pixels_at_threshold_20m": fr["all_pixels_at_threshold_20m"]}
    return r


def mmu_holdout(candidate):
    """The chosen minimum mapping unit on the held-out window, once, next to the same map without it."""
    variant, key = _parse(candidate)
    setting, info_only = _mmu_chosen(), False
    if setting is None:   # no filter chosen: score the best real filter of the development check, for information only
        sel = json.loads((IMP / "mmu_selection.json").read_text(encoding="utf-8"))
        best = next(r for r in sel["settings"] if r["min_patch_px"] > 1 or r["majority_3x3"])
        setting, info_only = (best["min_patch_px"], best["majority_3x3"]), True
    thresholds = json.loads((IMP / variant / "development_metrics.json").read_text(encoding="utf-8"))["thresholds"]
    models, rng, report = _models(variant), np.random.default_rng(M.SEED + 1), {}
    for name in SITES:
        report[name] = _window_site(_site(name, VARIANTS[variant]["labels"]), models, thresholds, key, setting, rng)
    _json({"reading": "Variant 6 (amendment): the held-out window scored once with the minimum mapping unit chosen on development "
                      f"maps (improve/mmu_selection.json: {_mmu_name(setting)}). '{key}_mmu' = the exported score after it; '{key}' = "
                      "the same map without it. Same passes, sample and cells as holdout_s1_metrics.json.",
           "candidate": candidate, "setting": _mmu_name(setting), "information_only": info_only,
           "note": ("the development rule chose no filter (improve/mmu_selection.json), so the exported maps have none; this is the "
                    "best real filter of the development check, scored once for information") if info_only else None,
           "sites": report}, IMP / f"mmu_holdout_{candidate.replace('+', '_')}.json")


def fit_train(variant):
    """The fit version: the variant refitted with the held-out passes of FIT_SITES added (frozen trees and settings)."""
    o, names, params = VARIANTS[variant], _names(variant), _params(variant)
    out = IMP / FIT_NAME
    out.mkdir(parents=True, exist_ok=True)
    rounds = json.loads((IMP / variant / "training_manifest.json").read_text(encoding="utf-8"))["rounds"]
    rng = np.random.default_rng(M.SEED)
    parts, manifest = [], {}
    for name in SITES:
        s = _site(name, o["labels"])
        domain = F.train_domain(s["static"])
        pool, pool_w = F.pick_pool(domain, s["wet"], s["obs"], POOL_SIZE, rng, n_fit=int(s["fit"].sum()))
        pool_water = np.stack([labels.to_water(np.asarray(s["stack"][k]).ravel()[pool]) for k in range(len(s["passes"]))])
        nb = _neigh_reader(s, pool, o["labels"]) if o.get("neigh") else None
        cols = F.static_columns(s["static"], pool)
        tab = F.build_table(pool_water, s["times"], s["days"], cols, pool_w, s["rain"], rng, is_nisar=s["is_nisar"], neigh=nb)
        tabs = [tab]
        if name in FIT_SITES:    # the same samples as the variant, plus the held-out targets of this site (own random draws)
            tabs.append(F.build_table(pool_water, s["times"], s["days"], cols, pool_w, s["rain"], np.random.default_rng(M.SEED + 7),
                                      is_nisar=s["is_nisar"], neigh=nb, fit=np.ones(len(s["days"]), bool),
                                      only=~s["fit"] & ~s["is_nisar"]))
        if nb is not None:
            nb.save()
        for tb in tabs:
            tb["site"] = np.full(tb["y"].size, SITES.index(name), "int8")
        parts += tabs
        used = sorted(set(np.concatenate([tb["t"] for tb in tabs]).tolist()))
        between = [F.rain_features(s["rain"], date.fromisoformat(s["days"][F.issue_index(s["times"], t)]).toordinal(),
                                   date.fromisoformat(s["days"][t]).toordinal())["rain_between_mm"] for t in used]
        added = sorted(set(tabs[1]["t"].tolist())) if len(tabs) > 1 else []
        manifest[name] = {"target_passes_used": len(used), "samples": int(sum(tb["y"].size for tb in tabs)),
                          "added_held_out_targets": [s["passes"][t]["pass_id"] for t in added],
                          "added_samples": int(tabs[1]["y"].size) if len(tabs) > 1 else 0,
                          "rain_between_mm": {"max": round(float(np.nanmax(between)), 1), "p99": round(float(np.nanpercentile(between, 99)), 1),
                                              "p90": round(float(np.nanpercentile(between, 90)), 1),
                                              "targets_over_100mm": int(np.sum(np.array(between) >= 100))}}
        print(FIT_NAME, name, {k: v for k, v in manifest[name].items() if k != "added_held_out_targets"}, len(added), "added targets", flush=True)
    T = {k: np.concatenate([p_[k] for p_ in parts]) for k in ("X", "y", "w")}
    X, y, w = T["X"], T["y"], T["w"]
    t_final = M.fit(X, y, w, F.TERRAIN_ONLY, rounds=rounds["terrain_only"])
    b = M.fit(X, y, w, names, rounds=rounds["rain_and_state"], params=params)
    t_final.save_model(str(out / "model_terrain_only.txt"))
    b.save_model(str(out / "model.txt"))
    np.savez(out / "blend_reference.npz", model=reference(M.predict(b, X, names), w), terrain=reference(M.predict(t_final, X, F.TERRAIN_ONLY), w))
    _json({"variant": variant, "fit_version": FIT_NAME,
           "reading": f"{variant} and the terrain-only model refitted with the held-out passes of {', '.join(FIT_SITES)} added "
                      "(15 Oct to 15 Nov 2026); trees, settings and thresholds frozen from the development check of the variant. "
                      "The other site's held-out passes are in nothing.",
           "params": {**M.PARAMS, **(params or {})}, "rounds": rounds, "sites": manifest}, out / "training_manifest.json")


def fit_test(candidate):
    """(a) fitted at FIT_SITES, (b) test elsewhere, (c) the test with the 17 Oct forecast rain."""
    variant, key = _parse(candidate)
    thresholds = json.loads((IMP / variant / "development_metrics.json").read_text(encoding="utf-8"))["thresholds"]
    models, setting = _models_in(variant, IMP / FIT_NAME), _mmu_chosen()
    rng, report = np.random.default_rng(M.SEED + 1), {}
    for name in SITES:
        fitted = name in FIT_SITES
        report[name] = {"label": "fitted (in sample: the model learned from these passes)" if fitted
                        else "test (out of sample: never used for training or choosing)",
                        **_window_site(_site(name, VARIANTS[variant]["labels"]), models, thresholds, key, setting, rng,
                                       freq_mode="all_passes" if fitted else None)}
    _json({"reading": f"Fit, then test (amendment): {candidate} refitted with the held-out passes of {', '.join(FIT_SITES)} "
                      "(improve/fit_albufera_oct), frozen trees and thresholds. Scores against the Sentinel-1 maps of the held-out "
                      "window; dana_passes = 22 and 23 Oct; forecast_replay = the pass of 22 Oct with the rain of the IFS run of the "
                      f"issue day. '{key}_mmu' = after the minimum mapping unit ({_mmu_name(setting)}). Same storm at both sites.",
           "candidate": candidate, "setting": _mmu_name(setting), "sites": report}, IMP / FIT_NAME / "holdout_s1_metrics.json")


def export_extra(which):
    """The two more exports for the EMSR935 test, Pego-Oliva only, in folders that --model-dir reads."""
    if which == "nisar":
        root = EXPORTS / "nisar_labels" / "data" / "prediction" / "spatial"
        export_maps("nisar_flag+blend", root=root, sites=("pego_oliva",), label="nisar_flag+blend",
                    status="NISAR-label candidate (Sentinel-1 and NISAR water labels), best of its kind on development data; "
                           "held-out check in data/prediction/spatial/improve/nisar_flag; not yet scored against EMSR935")
    elif which == "fit":
        root = EXPORTS / FIT_NAME / "data" / "prediction" / "spatial"
        export_maps("mono_neigh+blend", root=root, sites=("pego_oliva",), model_dir=IMP / FIT_NAME,
                    label="mono_neigh+blend fitted with Albufera's 15 Oct to 15 Nov 2026 passes",
                    status="fit version: learned from Albufera's DANA passes, never from Pego-Oliva's; at Pego-Oliva out of "
                           "sample; check in data/prediction/spatial/improve/fit_albufera_oct; not yet scored against EMSR935")
    else:
        raise ValueError(which)


def main():
    parser = argparse.ArgumentParser(prog="python -m pipeline.prediction.spatial.improve")
    parser.add_argument("cmd", choices=("train", "select", "holdout", "table", "export", "nisar", "mmu_dev", "mmu_holdout",
                                        "fit_train", "fit_test", "export_extra", "mmu_select", "amend_table"))
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    if args.cmd in ("select", "table", "amend_table"):
        {"select": select, "table": table, "amend_table": amend_table}[args.cmd](args.names)
        return
    for n in args.names:
        {"train": train, "holdout": holdout, "export": export_maps, "nisar": nisar, "mmu_dev": mmu_dev,
         "mmu_holdout": lambda c: mmu_holdout(c), "fit_train": lambda v: fit_train(v), "fit_test": lambda c: fit_test(c),
         "export_extra": lambda c: export_extra(c), "mmu_select": mmu_select}[args.cmd](n)


if __name__ == "__main__":
    main()
