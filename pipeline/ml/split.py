"""Spatial train / test split on map blocks, so neighbouring pixels do not leak.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_dilation

from . import config


def block_ids(shape: tuple[int, int], block_px: int = config.BLOCK_PX) -> np.ndarray:
    h, w = shape
    rows = np.arange(h) // block_px
    cols = np.arange(w) // block_px
    n_cols = (w + block_px - 1) // block_px
    return rows[:, None] * n_cols + cols[None, :]


def split_blocks(
    shape: tuple[int, int],
    block_px: int = config.BLOCK_PX,
    test_fraction: float = config.TEST_FRACTION,
    gap_px: int = config.GAP_PX,
    seed: int = config.SEED,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (train_mask, test_mask) as (y, x) bool arrays.

    Whole blocks go to test. Train pixels within gap_px of a test block are
    dropped, so a 5x5 speckle filter or label blur cannot bridge the split.
    """
    ids = block_ids(shape, block_px)
    unique = np.unique(ids)
    rng = np.random.default_rng(seed)
    n_test = max(1, round(test_fraction * unique.size))
    test_ids = rng.choice(unique, size=n_test, replace=False)
    test = np.isin(ids, test_ids)
    near_test = binary_dilation(test, iterations=gap_px) if gap_px > 0 else test
    train = ~near_test
    return train, test
