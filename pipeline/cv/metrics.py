"""Score a binary prediction against a binary label, on valid pixels only.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np


def confusion(pred: np.ndarray, truth: np.ndarray, valid: np.ndarray) -> dict[str, int]:
    """True/false positives and negatives over pixels where valid is set."""
    v = valid.astype(bool)
    p, t = pred.astype(bool) & v, truth.astype(bool) & v
    return {
        "tp": int(np.count_nonzero(p & t)),
        "fp": int(np.count_nonzero(p & ~t)),
        "fn": int(np.count_nonzero(~p & t & v)),
        "tn": int(np.count_nonzero(~p & ~t & v)),
    }


def scores(c: dict[str, int]) -> dict[str, float | None]:
    """Precision, recall, F1 and IoU from a confusion dict (None when undefined)."""
    tp, fp, fn = c["tp"], c["fp"], c["fn"]

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    f1 = ratio(2 * tp, 2 * tp + fp + fn)
    return {"precision": precision, "recall": recall, "f1": f1, "iou": ratio(tp, tp + fp + fn)}
