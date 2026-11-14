"""Train LightGBM on block-separated pixels, score it and predict the full map.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix, precision_recall_fscore_support

from . import config
from .features import FEATURE_NAMES


def sample_per_class(
    y: np.ndarray, candidates: np.ndarray, max_per_class: int, seed: int
) -> np.ndarray:
    """Indices of candidate pixels, at most max_per_class from each class."""
    rng = np.random.default_rng(seed)
    picked = []
    for c in range(len(config.CLASSES)):
        idx = np.flatnonzero(candidates & (y == c))
        if idx.size > max_per_class:
            idx = rng.choice(idx, size=max_per_class, replace=False)
        picked.append(idx)
    return np.sort(np.concatenate(picked))


def fit(X: np.ndarray, y: np.ndarray, seed: int = config.SEED) -> LGBMClassifier:
    model = LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=40,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        class_weight="balanced",
        random_state=seed,
        verbose=-1,
    )
    model.fit(X, y)
    return model


def predict_proba_full(model: LGBMClassifier, X: np.ndarray) -> np.ndarray:
    """Probabilities with one column per config.CLASSES entry (0 for unseen classes)."""
    proba = np.zeros((X.shape[0], len(config.CLASSES)), dtype=np.float32)
    proba[:, model.classes_.astype(int)] = model.predict_proba(X)
    return proba


def evaluate(model: LGBMClassifier, X: np.ndarray, y: np.ndarray,
             forbid: dict[int, np.ndarray] | None = None) -> dict:
    """Scores on held-out rows. forbid: the same rules the map uses, indexed like X."""
    proba = _apply_rules(predict_proba_full(model, X), forbid, np.arange(X.shape[0]))
    pred = np.argmax(proba, axis=1)
    all_classes = list(range(len(config.CLASSES)))
    p, r, f1, support = precision_recall_fscore_support(
        y, pred, labels=all_classes, zero_division=0
    )
    present = support > 0
    return {
        "n_test_pixels": int(y.size),
        "overall_accuracy": float(accuracy_score(y, pred)),
        "kappa": float(cohen_kappa_score(y, pred)),
        "macro_f1": float(f1[present].mean()) if present.any() else None,
        "per_class": {
            name: {
                "precision": float(p[i]),
                "recall": float(r[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i, name in enumerate(config.CLASSES)
        },
        "confusion_matrix": {
            "labels": config.CLASSES,
            "rows_are": "reference",
            "matrix": confusion_matrix(y, pred, labels=all_classes).tolist(),
        },
        "classes_missing_from_test": [n for i, n in enumerate(config.CLASSES) if not present[i]],
    }


def feature_importance(model: LGBMClassifier) -> list[dict]:
    gain = model.booster_.feature_importance(importance_type="gain")
    share = gain / gain.sum() if gain.sum() > 0 else gain
    order = np.argsort(-share)
    return [{"feature": FEATURE_NAMES[i], "gain_share": float(share[i])} for i in order]


def burned_rule(X: np.ndarray, min_hv_drop_db: float | None) -> dict[int, np.ndarray]:
    """Rows where "burned" is not allowed: HV did not drop by min_hv_drop_db and stay down.

    The CV baseline rule (HV step drop >= 1.5 dB) agrees with EFFIS at precision
    0.94 to 0.99 (Ilija, PR #7). Without it the model learned burned as a static
    kind of forest and over-predicted it by 70 % at Espadà.
    """
    if min_hv_drop_db is None:
        return {}
    drop = X[:, FEATURE_NAMES.index("hv_step_drop")]
    return {config.CLASS_INDEX["burned"]: ~(np.nan_to_num(drop, nan=0.0) >= min_hv_drop_db)}


def _apply_rules(proba: np.ndarray, forbid: dict[int, np.ndarray] | None, rows: np.ndarray) -> np.ndarray:
    """Zero a class where a rule forbids it; the next most likely class wins.
    Probabilities are not renormalized, so confidence drops where a rule fired."""
    if forbid:
        proba = proba.copy()
        for c, mask in forbid.items():
            proba[mask[rows], c] = 0.0
    return proba


def predict_map(
    model: LGBMClassifier, X: np.ndarray, usable: np.ndarray, shape: tuple[int, int],
    chunk: int = 200_000, forbid: dict[int, np.ndarray] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Class map (uint8, NODATA_U8 where unusable) and confidence (max probability, NaN)."""
    classes = np.full(X.shape[0], config.NODATA_U8, dtype=np.uint8)
    confidence = np.full(X.shape[0], np.nan, dtype=np.float32)
    idx = np.flatnonzero(usable)
    for start in range(0, idx.size, chunk):
        part = idx[start:start + chunk]
        proba = _apply_rules(predict_proba_full(model, X[part]), forbid, part)
        classes[part] = np.argmax(proba, axis=1).astype(np.uint8)
        confidence[part] = proba.max(axis=1)
    return classes.reshape(shape), confidence.reshape(shape)


def class_areas_ha(class_map: np.ndarray) -> dict[str, float]:
    return {
        name: round(float((class_map == i).sum()) * config.PIXEL_HA, 2)
        for i, name in enumerate(config.CLASSES)
    }
