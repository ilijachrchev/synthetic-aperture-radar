"""Versioned experiments for the ML model, scored without fooling ourselves.

Three sets, never mixed (see the spatial-ml-experiments notes in LOG.md):

1. test blocks       split_blocks(seed=SEED) on all labels; looked at once per finalist
2. validation blocks split_blocks(seed=s) on the training-area labels, for s in VAL_SEEDS;
                     every choice (features, settings, tree count, rules) is made here
3. training pixels   the rest of the training area (2 px gap around the other blocks)

    python -m pipeline.ml.experiment val  --version v2a --parent v2 --change "..." --config '{"lr": 0.03}'
    python -m pipeline.ml.experiment test --version v3 --config '{...}'   # finalists only

Each run appends one line to data/ml/experiments/registry.jsonl. Scores are
agreement with the label maps (WorldCover, JRC, CORINE, EFFIS, drawn fields),
not ground-truth accuracy.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

from pipeline.config import REPO_ROOT

from . import config, data, features, labels, split, train

EXP_DIR = config.ML_OUT_DIR / "experiments"
REGISTRY = EXP_DIR / "registry.jsonl"
VAL_SEEDS = (43, 44, 45)   # 43 = SEED + 1, the split __main__ uses for early stopping
FAR_FROM_FIRE_M = 2000.0   # "burned" this far from the EFFIS outline is almost surely wrong
SITES = {"albufera": ("066_D_069", "058_A_021"), "espada": ("058_A_022", "167_D_068")}
BENCHMARK = ("albufera", "pego_oliva")   # train on the first, predict the second (never seen)


@dataclass
class Config:
    """Everything that defines a version. Defaults = v2 (this branch)."""
    tracks: int = 2                    # 1 = first stack of the site only, 2 = both tracks per pixel
    max_per_class: int = config.MAX_TRAIN_PER_CLASS
    num_leaves: int = config.NUM_LEAVES
    min_child: int = config.MIN_CHILD_SAMPLES
    trees: int = 0                     # 0 = early stopping on the validation blocks
    learning_rate: float = 0.05
    colsample: float = 0.8
    subsample: float = 0.8
    reg_lambda: float = 0.0
    burned_min_hv_drop: float = 1.0    # 0 = no rule
    feature_set: str = "base"          # see features.FEATURE_SETS
    orchard_shrink_m: float = 0.0
    forest_shrink_m: float = 0.0
    orchard_rule: str = "trees"        # labels.ORCHARD_RULES; training labels only
    filter_px: int = data.FILTER_PX

    def lgbm_extra(self) -> dict:
        return dict(learning_rate=self.learning_rate, colsample_bytree=self.colsample,
                    subsample=self.subsample, reg_lambda=self.reg_lambda)


V1 = Config(tracks=1, max_per_class=20_000, num_leaves=31, min_child=40, trees=400)


@dataclass
class Prepared:
    site: str
    stacks: tuple[str, ...]
    shape: tuple[int, int]
    X: np.ndarray
    names: list[str]
    usable: np.ndarray          # (n,) bool
    y_map: np.ndarray           # (h, w) int16 labels, UNLABELED where none or unusable
    dates: list[str] = field(default_factory=list)
    sources: dict = field(default_factory=dict)
    effis_far: np.ndarray | None = None   # (n,) bool: more than FAR_FROM_FIRE_M from EFFIS
    y_train: np.ndarray | None = None     # training labels if they differ (e.g. shrunk CORINE); scores
                                          # always use y_map, so a label change cannot move the goalposts

    @property
    def y_fit(self) -> np.ndarray:
        return (self.y_map if self.y_train is None else self.y_train).ravel()


def _features_cached(site: str, stack: str, stack_dir: Path, cfg: Config, cache: Path | None):
    key = f"{site}_{stack}_f{cfg.filter_px}_{cfg.feature_set}.npz"
    if cache is not None and (cache / key).exists():
        z = np.load(cache / key, allow_pickle=False)
        return z["X"], z["usable"], list(z["names"]), list(z["dates"]), (int(z["h"]), int(z["w"]))
    st = data.load(data.stack_path(site, stack, stack_dir), filter_px=cfg.filter_px)
    dark, _ = features.water_threshold(st.hh_db)
    X, usable, names = features.feature_set(cfg.feature_set, st.hh_db, st.hv_db, st.times, dark)
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        np.savez(cache / key, X=X, usable=usable, names=np.array(names), dates=np.array(st.dates),
                 h=st.shape[0], w=st.shape[1])
    return X, usable, names, st.dates, st.shape


def prepare(site: str, cfg: Config, stack_dir: Path, cache: Path | None = None,
            stacks: tuple[str, ...] | None = None) -> Prepared:
    from pipeline.config import get_site
    from pipeline.stack import site_grid

    stacks = (stacks or SITES[site])[: cfg.tracks]
    Xs, names, dates, usable, shape = [], [], [], None, None
    for i, s in enumerate(stacks):
        X, u, n, d, shape = _features_cached(site, s, stack_dir, cfg, cache)
        Xs.append(X)
        names += n if i == 0 else [f"{x}@{s}" for x in n]
        dates += d
        usable = u if usable is None else (usable & u)
    grid = site_grid(get_site(site))
    found = labels.default_sources(site)
    y_map, sea = labels.build_labels(grid, **found)
    usable = usable & ~sea.ravel()
    y_map = np.where(usable.reshape(shape), y_map, config.UNLABELED).astype(np.int16)
    y_train = None
    if cfg.orchard_shrink_m or cfg.forest_shrink_m or cfg.orchard_rule != "trees":
        y_train, _ = labels.build_labels(grid, **found, orchard_shrink_m=cfg.orchard_shrink_m,
                                         forest_shrink_m=cfg.forest_shrink_m, orchard_rule=cfg.orchard_rule)
        y_train = np.where(usable.reshape(shape), y_train, config.UNLABELED).astype(np.int16)
    far = None
    if found["effis"] is not None:
        fire = labels.rasterize_polygons(found["effis"], grid, class_name="burned") != config.UNLABELED
        far = (distance_transform_edt(~fire) * config.PIXEL_SIZE_M > FAR_FROM_FIRE_M).ravel()
    return Prepared(site, stacks, shape, np.hstack(Xs), names, usable, y_map, dates,
                    {k: (str(v.relative_to(REPO_ROOT).as_posix()) if v else None) for k, v in found.items()},
                    far, y_train)


def _forbid(cfg: Config, p: Prepared) -> dict:
    return train.burned_rule(p.X, cfg.burned_min_hv_drop if cfg.burned_min_hv_drop > 0 else None, p.names)


def _brief(m: dict) -> dict:
    return {"accuracy": round(m["overall_accuracy"], 4), "macro_f1": round(m["macro_f1"], 4),
            "per_class_f1": {k: round(v["f1"], 4) for k, v in m["per_class"].items() if v["support"] > 0},
            "burned_precision": round(m["per_class"]["burned"]["precision"], 4)
            if m["per_class"]["burned"]["support"] > 0 else None}


def test_split(p: Prepared) -> tuple[np.ndarray, np.ndarray]:
    return split.split_blocks(p.shape, seed=config.SEED, labels=p.y_map)


def val_split(p: Prepared, train_mask: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    lab_train = np.where(train_mask, p.y_map, config.UNLABELED)
    fit_m, val_m = split.split_blocks(p.shape, seed=seed, labels=lab_train)
    return fit_m & train_mask, val_m & train_mask


def run_val(cfg: Config, p: Prepared, seed: int, full_map: bool = False,
            rules: tuple[float, ...] | None = None) -> dict:
    """Train on the fit area, early-stop and score on one set of validation blocks.

    rules: also score these burned-rule thresholds (0 = no rule) with the same
    trained model; the rule acts after the model, so no retraining is needed.
    Returned under "rules", keyed by threshold."""
    t0 = time.time()
    y = p.y_map.ravel()
    labelled = y != config.UNLABELED
    train_mask, _ = test_split(p)
    fit_m, val_m = val_split(p, train_mask, seed)
    yf = p.y_fit
    fit_rows = train.sample_per_class(yf, (yf != config.UNLABELED) & fit_m.ravel(), cfg.max_per_class, seed)
    val_rows = np.flatnonzero(labelled & val_m.ravel())
    kw = dict(seed=seed, num_leaves=cfg.num_leaves, min_child_samples=cfg.min_child, **cfg.lgbm_extra())
    if cfg.trees > 0:
        model, n_trees = train.fit(p.X[fit_rows], yf[fit_rows], n_estimators=cfg.trees, **kw), cfg.trees
    else:
        n_trees, model = train.best_tree_count(p.X[fit_rows], yf[fit_rows], p.X[val_rows], y[val_rows],
                                               return_model=True, **kw)
    forbid = _forbid(cfg, p)
    m = train.evaluate(model, p.X[val_rows], y[val_rows], forbid={c: f[val_rows] for c, f in forbid.items()})
    out = {"seed": seed, "trees": n_trees, "val_pixels": int(val_rows.size), **_brief(m)}
    if p.y_train is not None:
        # Secondary only: the same validation blocks scored against the changed labels.
        own = np.flatnonzero((yf != config.UNLABELED) & val_m.ravel())
        out["on_own_labels"] = _brief(train.evaluate(
            model, p.X[own], yf[own], forbid={c: f[own] for c, f in forbid.items()}))
    if full_map and p.effis_far is not None:
        class_map, _ = train.predict_map(model, p.X, p.usable, p.shape, forbid=forbid)
        out.update(_burned_area(class_map, p))
    if rules:
        out["rules"] = {}
        idx = np.flatnonzero(p.usable)
        proba = train.predict_proba_full(model, p.X[idx])          # once; each rule only masks it
        pos = np.full(p.X.shape[0], -1)
        pos[idx] = np.arange(idx.size)
        burned = config.CLASS_INDEX["burned"]
        for thr in rules:
            pr = proba.copy()
            if thr > 0:
                pr[train.burned_rule(p.X[idx], thr, p.names)[burned], burned] = 0.0
            pred = np.argmax(pr, axis=1)
            r = _brief(train.evaluate(None, None, y[val_rows], pred=pred[pos[val_rows]]))
            if p.effis_far is not None:
                cm = np.full(p.X.shape[0], config.NODATA_U8, np.uint8)
                cm[idx] = pred
                r.update(_burned_area(cm, p))
            out["rules"][str(thr)] = r
    out["seconds"] = round(time.time() - t0, 1)
    return out


def _burned_area(class_map: np.ndarray, p: Prepared) -> dict:
    burned = (class_map == config.CLASS_INDEX["burned"]).ravel()
    return {"burned_ha_total": round(float(burned.sum()) * config.PIXEL_HA, 1),
            "burned_ha_far_from_effis": round(float((burned & p.effis_far).sum()) * config.PIXEL_HA, 1)}


def _summary(runs: list[dict]) -> dict:
    """Mean and spread (max - min) over seeds."""
    def ms(vals):
        v = np.array([x for x in vals if x is not None], float)
        return {"mean": round(float(v.mean()), 4), "spread": round(float(v.max() - v.min()), 4)} if v.size else None
    classes = sorted({c for r in runs for c in r["per_class_f1"]})
    s = {"macro_f1": ms(r["macro_f1"] for r in runs), "accuracy": ms(r["accuracy"] for r in runs),
         "per_class_f1": {c: ms(r["per_class_f1"].get(c) for r in runs) for c in classes},
         "burned_precision": ms(r["burned_precision"] for r in runs)}
    if "on_own_labels" in runs[0]:
        s["on_own_labels"] = {"macro_f1": ms(r["on_own_labels"]["macro_f1"] for r in runs),
                              "per_class_f1": {c: ms(r["on_own_labels"]["per_class_f1"].get(c) for r in runs)
                                               for c in classes}}
    if "burned_ha_far_from_effis" in runs[0]:
        s["burned_ha_far_from_effis"] = ms(r["burned_ha_far_from_effis"] for r in runs)
        s["burned_ha_total"] = ms(r["burned_ha_total"] for r in runs)
    return s


def fit_final(cfg: Config, p: Prepared):
    """Tree count by early stopping on validation seed 43, then refit on the whole training area."""
    y = p.y_map.ravel()
    labelled = y != config.UNLABELED
    train_mask, test_mask = test_split(p)
    kw = dict(seed=config.SEED, num_leaves=cfg.num_leaves, min_child_samples=cfg.min_child, **cfg.lgbm_extra())
    n_trees = cfg.trees
    if n_trees <= 0:
        fit_m, val_m = val_split(p, train_mask, config.SEED + 1)
        yf = p.y_fit
        fr = train.sample_per_class(yf, (yf != config.UNLABELED) & fit_m.ravel(), cfg.max_per_class, config.SEED)
        vr = np.flatnonzero(labelled & val_m.ravel())
        n_trees = train.best_tree_count(p.X[fr], yf[fr], p.X[vr], y[vr], **kw)
    yf = p.y_fit
    tr = train.sample_per_class(yf, (yf != config.UNLABELED) & train_mask.ravel(), cfg.max_per_class, config.SEED)
    model = train.fit(p.X[tr], yf[tr], n_estimators=n_trees, **kw)
    return model, n_trees, test_mask


def final_map(model, cfg: Config, p: Prepared, majority: int = 3, min_patch_px: int = 5):
    forbid = _forbid(cfg, p)
    class_map, conf = train.predict_map(model, p.X, p.usable, p.shape, forbid=forbid)
    class_map = train.sieve_small_patches(train.majority_filter(class_map, size=majority), min_patch_px)
    return class_map, conf


def run_test(cfg: Config, p: Prepared) -> tuple[dict, object, np.ndarray, np.ndarray]:
    model, n_trees, test_mask = fit_final(cfg, p)
    class_map, conf = final_map(model, cfg, p)
    y = p.y_map.ravel()
    te = np.flatnonzero((y != config.UNLABELED) & test_mask.ravel())
    m = train.evaluate(None, None, y[te], pred=class_map.ravel()[te])
    out = {"trees": n_trees, "test_pixels": int(te.size), **_brief(m),
           "per_class": m["per_class"], "confusion_matrix": m["confusion_matrix"]}
    if p.effis_far is not None:
        out.update(_burned_area(class_map, p))
    return out, model, class_map, conf


def run_benchmark(cfg: Config, train_p: Prepared, test_p: Prepared, model=None) -> dict:
    """The finalist model of the training site, applied to a site it never saw; scored on all its labels."""
    if [n.split("@")[0] for n in train_p.names] != [n.split("@")[0] for n in test_p.names]:
        raise ValueError("benchmark site must have the same features (same tracks)")
    if model is None:
        model, _, _ = fit_final(cfg, train_p)
    class_map, _ = final_map(model, cfg, test_p)
    y = test_p.y_map.ravel()
    rows = np.flatnonzero(y != config.UNLABELED)
    m = train.evaluate(None, None, y[rows], pred=class_map.ravel()[rows])
    return {"train_site": train_p.site, "site": test_p.site, "stacks": list(test_p.stacks),
            "label_sources": test_p.sources, "pixels": int(rows.size), **_brief(m), "per_class": m["per_class"]}


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=REPO_ROOT, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def append_registry(entry: dict, path: Path = REGISTRY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def validate(version: str, parent: str | None, change: str, cfg: Config, stack_dir: Path,
             cache: Path | None, sites=tuple(SITES), seeds=VAL_SEEDS, record: bool = True,
             rules: tuple[float, ...] | None = None) -> dict:
    t0 = time.time()
    entry = {"version": version, "parent": parent, "change": change, "stage": "validation",
             "config": asdict(cfg), "seeds": list(seeds), "sites": {}}
    for site in sites:
        p = prepare(site, cfg, stack_dir, cache)
        runs = [run_val(cfg, p, s, full_map=p.effis_far is not None, rules=rules) for s in seeds]
        entry["sites"][site] = {"stacks": list(p.stacks), "dates": p.dates, "label_sources": p.sources,
                                "n_features": len(p.names), "runs": runs, "summary": _summary(runs)}
        sm = entry["sites"][site]["summary"]
        print(f"{version} {site}: val macro F1 {sm['macro_f1']['mean']:.4f} "
              f"(spread {sm['macro_f1']['spread']:.4f}) "
              + " ".join(f"{c}={v['mean']:.3f}" for c, v in sm["per_class_f1"].items()), flush=True)
    entry.update(seconds=round(time.time() - t0), git_commit=_git_commit(),
                 created_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    if record:
        append_registry(entry)
    return entry


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m pipeline.ml.experiment")
    ap.add_argument("stage", choices=["val"])
    ap.add_argument("--version", required=True)
    ap.add_argument("--parent")
    ap.add_argument("--change", default="")
    ap.add_argument("--config", default="{}", help="JSON overrides of Config (defaults = v2)")
    ap.add_argument("--base", default="v2", choices=["v1", "v2"])
    ap.add_argument("--stack-dir", default=str(config.STACK_DIR))
    ap.add_argument("--cache", help="folder for cached features (speeds up repeated runs)")
    ap.add_argument("--sites", default=",".join(SITES))
    ap.add_argument("--rules", help="comma list of burned-rule thresholds to also score (0 = none)")
    a = ap.parse_args(argv)
    base = asdict(V1 if a.base == "v1" else Config())
    cfg = Config(**{**base, **json.loads(a.config)})
    validate(a.version, a.parent, a.change, cfg, Path(a.stack_dir), Path(a.cache) if a.cache else None,
             sites=tuple(a.sites.split(",")),
             rules=tuple(float(x) for x in a.rules.split(",")) if a.rules else None)


if __name__ == "__main__":
    main()
