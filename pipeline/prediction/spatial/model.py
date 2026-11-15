"""Fit and score the water-likelihood model (a small LightGBM classifier) and its simple comparisons.

Development split: learn from passes before DEV_SPLIT on the training blocks,
check on later passes on the held-back 1 km blocks (new time and new ground).
The number of trees and the map threshold come from that check; the final model
is then refitted on every pass outside the held-out window with both fixed.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve

from .features import ALL as FEATURES, CATEGORICAL

DEV_SPLIT = "2025-09-01"
SEED = 0
PARAMS = {
    "objective": "binary", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 200,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "max_cat_to_onehot": 16, "verbose": -1, "seed": SEED, "num_threads": 8,
}
MAX_ROUNDS = 600
EARLY_STOP = 40


def _dataset(X, y, w, names):
    cols = [FEATURES.index(n) for n in names]
    cat = [i for i, n in enumerate(names) if n in CATEGORICAL]
    return lgb.Dataset(X[:, cols], label=y, weight=w, feature_name=list(names), categorical_feature=cat, free_raw_data=False)


def fit(X, y, w, names, rounds: int | None = None, valid=None, params: dict | None = None) -> lgb.Booster:
    """params: extra LightGBM settings on top of PARAMS (for example monotone constraints)."""
    p = PARAMS if not params else {**PARAMS, **params}
    train = _dataset(X, y, w, names)
    if valid is None:
        return lgb.train(p, train, num_boost_round=rounds or MAX_ROUNDS)
    val = _dataset(*valid, names)
    return lgb.train(p, train, num_boost_round=MAX_ROUNDS, valid_sets=[val],
                     callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)])


def predict(booster: lgb.Booster, X: np.ndarray, names) -> np.ndarray:
    return booster.predict(X[:, [FEATURES.index(n) for n in names]])


def baselines(X: np.ndarray) -> dict[str, np.ndarray]:
    """Scores of the two no-model comparisons, from the feature columns."""
    freq = np.nan_to_num(X[:, FEATURES.index("s1_wet_freq")], nan=0.0)
    prev = X[:, FEATURES.index("prev_water")]
    return {"persistence": np.where(np.isnan(prev), freq, prev), "past_wet_share": freq}


def ranking(y, score, w) -> float | None:
    """Weighted average precision (area under the precision-recall curve); None without both classes."""
    if y.size == 0 or y.min() == y.max():
        return None
    return round(float(average_precision_score(y, score, sample_weight=w)), 4)


def best_threshold(y, score, w) -> float:
    p, r, thr = precision_recall_curve(y, score, sample_weight=w)
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    return float(thr[int(np.argmax(f1))])


def at_threshold(y, score, w, thr: float) -> dict:
    pred = score >= thr
    tp = float(w[pred & (y == 1)].sum()); fp = float(w[pred & (y == 0)].sum()); fn = float(w[~pred & (y == 1)].sum())
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"precision": None if prec is None else round(prec, 4), "recall": None if rec is None else round(rec, 4),
            "f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp + fp + fn else None,
            "iou": round(tp / (tp + fp + fn), 4) if tp + fp + fn else None,
            "predicted_w": round(tp + fp, 1), "observed_w": round(tp + fn, 1)}


def score_all(y, w, scores: dict[str, np.ndarray], new_candidates: np.ndarray, thresholds: dict | None = None) -> dict:
    """Ranking of every method on all samples and on the 'was dry before' samples; plus threshold scores if given."""
    out = {"n": int(y.size), "weighted_wet_share": round(float((w * y).sum() / w.sum()), 5) if y.size else None,
           "n_new_candidates": int(new_candidates.sum()),
           "weighted_new_water_share": round(float((w * y)[new_candidates].sum() / max(w[new_candidates].sum(), 1e-9)), 5),
           "methods": {}}
    for name, s in scores.items():
        m = {"water_ap": ranking(y, s, w), "new_water_ap": ranking(y[new_candidates], s[new_candidates], w[new_candidates])}
        if thresholds and name in thresholds:
            m["water_at_threshold"] = at_threshold(y, s, w, thresholds[name]["water"])
            m["new_water_at_threshold"] = at_threshold(y[new_candidates], s[new_candidates], w[new_candidates],
                                                       thresholds[name]["new_water"])
        out["methods"][name] = m
    return out
