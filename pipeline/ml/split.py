"""Spatial train / test split on map blocks, so neighbouring pixels do not leak.

Whole 1 km blocks go to test. With labels given, test blocks are picked class by
class, rarest class first, until each class has about test_fraction of its
labelled pixels in test. A purely random pick can miss a rare, clustered class
almost entirely (the first Albufera rice polygons landed 77 pixels in test out of
1,276), and then its score says nothing.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_dilation

from . import config

MIN_TRAIN_SHARE = 0.5  # a test block is never taken if it would leave a class less than this in train
OVERSHOOT = 0.10       # top-up blocks avoid pushing a class more than this above its test share


def block_ids(shape: tuple[int, int], block_px: int = config.BLOCK_PX) -> np.ndarray:
    h, w = shape
    rows = np.arange(h) // block_px
    cols = np.arange(w) // block_px
    n_cols = (w + block_px - 1) // block_px
    return rows[:, None] * n_cols + cols[None, :]


def _per_block_counts(ids: np.ndarray, labels: np.ndarray, n_blocks: int) -> np.ndarray:
    """(n_classes, n_blocks) labelled pixel counts."""
    counts = np.zeros((len(config.CLASSES), n_blocks), dtype=np.int64)
    for c in range(len(config.CLASSES)):
        m = labels == c
        counts[c] = np.bincount(ids[m], minlength=n_blocks)
    return counts


def pick_test_blocks(
    ids: np.ndarray, labels: np.ndarray | None, test_fraction: float, rng: np.random.Generator,
) -> np.ndarray:
    """Block ids that go to test."""
    n_blocks = int(ids.max()) + 1
    target = max(1, round(test_fraction * n_blocks))
    test = np.zeros(n_blocks, bool)

    counts = _per_block_counts(ids, labels, n_blocks) if labels is not None else None
    if counts is not None:
        totals = counts.sum(axis=1)
        for c in np.argsort(totals):  # rarest class first
            if totals[c] == 0:
                continue
            goal = test_fraction * totals[c]
            while counts[c, test].sum() < goal:
                have = counts[:, test].sum(axis=1)
                cands = [b for b in rng.permutation(np.flatnonzero((counts[c] > 0) & ~test))
                         # never starve any class's training set
                         if not np.any((totals > 0) & (totals - have - counts[:, b] < MIN_TRAIN_SHARE * totals))]
                if not cands:
                    break
                # The block that lands this class closest to its goal. A few big
                # blocks can hold most of a clustered class, so a random pick
                # overshoots badly; stop if every block would move us further away.
                miss = [abs(have[c] + counts[c, b] - goal) for b in cands]
                best = int(np.argmin(miss))
                if miss[best] >= abs(have[c] - goal) and have[c] > 0:
                    break
                test[cands[best]] = True

    # Top up to the overall block count. Prefer blocks that keep every class at
    # most OVERSHOOT above its fair test share; others only if still short.
    rest = rng.permutation(np.flatnonzero(~test))
    need = max(0, target - int(test.sum()))
    if counts is None:
        test[rest[:need]] = True
        return np.flatnonzero(test)
    in_test = counts[:, test].sum(axis=1).astype(float)
    limit = (test_fraction + OVERSHOOT) * totals
    skipped = []
    for b in rest:
        if need == 0:
            break
        if np.all((totals == 0) | (in_test + counts[:, b] <= limit)):
            test[b] = True
            in_test += counts[:, b]
            need -= 1
        else:
            skipped.append(b)
    test[skipped[:need]] = True
    return np.flatnonzero(test)


def split_blocks(
    shape: tuple[int, int],
    block_px: int = config.BLOCK_PX,
    test_fraction: float = config.TEST_FRACTION,
    gap_px: int = config.GAP_PX,
    seed: int = config.SEED,
    labels: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (train_mask, test_mask) as (y, x) bool arrays.

    labels: (y, x) class indices (config.UNLABELED elsewhere) to balance the
    test blocks per class; without it blocks are picked at random. Train pixels
    within gap_px of a test block are dropped, so a 5x5 speckle filter or label
    blur cannot bridge the split.
    """
    ids = block_ids(shape, block_px)
    rng = np.random.default_rng(seed)
    test = np.isin(ids, pick_test_blocks(ids, labels, test_fraction, rng))
    near_test = binary_dilation(test, iterations=gap_px) if gap_px > 0 else test
    return ~near_test, test
