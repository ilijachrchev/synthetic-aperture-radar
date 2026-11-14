"""Non-ML baseline for the CV model: the reference the U-Net has to beat.

Rules (starting points, to tune on the labels):
- Water: Otsu threshold per scene on speckle-filtered HH in dB. Published
  thresholds disagree (about -18 dB vs -11 dB for L-band), so it is computed
  per scene, never hard-coded.
- Flooded vegetation: HH rises by at least 3 dB while HV stays within 1 dB
  (double bounce between water and stems).
- Burn: HV drops by at least 1.5 dB on land (loss of volume scattering).

Every output is "candidate" until checked against the labels.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np
from skimage.filters import threshold_otsu

PIXEL_HA = 20.0 * 20.0 / 10_000.0  # one 20 m pixel = 0.04 ha
BURN_DROP_DB = 1.5  # HV drop that counts as a candidate burn (starting point, to tune on EFFIS)

CHANGE_CLASSES = {
    0: "not_observed",
    1: "stable_land",
    2: "stable_water",
    3: "water_gain",
    4: "water_loss",
    5: "other_change",
}


def otsu_threshold_db(db: np.ndarray, valid: np.ndarray) -> float:
    """Otsu threshold (dB) over the valid, finite pixels of one scene."""
    values = db[valid.astype(bool) & np.isfinite(db)]
    if values.size < 100:
        raise ValueError(f"only {values.size} valid pixels: too few for a threshold")
    return float(threshold_otsu(values))


def water_mask(hh_db: np.ndarray, valid: np.ndarray, threshold_db: float) -> np.ndarray:
    """Candidate open water: valid pixels darker than the threshold."""
    return valid.astype(bool) & np.isfinite(hh_db) & (hh_db < threshold_db)


def flooded_vegetation(hh_before: np.ndarray, hh_after: np.ndarray, hv_before: np.ndarray, hv_after: np.ndarray,
                       valid_both: np.ndarray, rise_db: float = 3.0, hv_flat_db: float = 1.0) -> np.ndarray:
    """Candidate flooded vegetation: HH up by rise_db or more, HV within hv_flat_db (all in dB)."""
    d_hh, d_hv = hh_after - hh_before, hv_after - hv_before
    return valid_both.astype(bool) & (d_hh >= rise_db) & (np.abs(d_hv) <= hv_flat_db)


def burn_candidate(hv_before: np.ndarray, hv_after: np.ndarray, land_both: np.ndarray,
                   drop_db: float = BURN_DROP_DB) -> np.ndarray:
    """Candidate burned ground: HV down by drop_db or more on pixels that are land on both dates."""
    return land_both.astype(bool) & ((hv_after - hv_before) <= -drop_db)


def change_classes(water_before: np.ndarray, water_after: np.ndarray, valid_before: np.ndarray, valid_after: np.ndarray,
                   d_hh_db: np.ndarray, other_change_db: float = 3.0) -> np.ndarray:
    """Per-pixel change class for a before/after pair (codes in CHANGE_CLASSES)."""
    wb, wa = water_before.astype(bool), water_after.astype(bool)
    both = valid_before.astype(bool) & valid_after.astype(bool)
    out = np.zeros(wb.shape, dtype="uint8")  # 0 not observed
    out[both & ~wb & ~wa] = 1
    out[both & ~wb & ~wa & (np.abs(d_hh_db) >= other_change_db)] = 5
    out[both & wb & wa] = 2
    out[both & ~wb & wa] = 3
    out[both & wb & ~wa] = 4
    return out


def area_ha(mask: np.ndarray, pixel_ha: float = PIXEL_HA) -> float:
    """Area of a boolean mask in hectares on the 20 m analysis grid."""
    return float(np.count_nonzero(mask)) * pixel_ha


def threshold_sensitivity(hh_db: np.ndarray, valid: np.ndarray, threshold_db: float,
                          deltas_db: tuple[float, ...] = (-1.0, 0.0, 1.0)) -> dict[float, float]:
    """Water area (ha) when the threshold moves by each delta: the range we report."""
    return {d: area_ha(water_mask(hh_db, valid, threshold_db + d)) for d in deltas_db}
