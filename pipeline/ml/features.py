"""One feature row per pixel from the HH / HV time series (MODELS.md, ML Processing).

Inputs are in dB with NaN for "not seen on this date" (pipeline.ml.data.load).
HH and HV are treated separately, so a date with HH but no HV (the HH-only
2026-09-22 pass on track 058 A) still counts for HH. Steps between dates skip
missing dates. Pixels seen on fewer than config.MIN_VALID_DATES dates in HH or
in HV are flagged and not classified.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import warnings

import numpy as np

from . import config

FEATURE_NAMES: list[str] = [
    "hh_mean", "hh_std", "hh_min", "hh_max",
    "hv_mean", "hv_std", "hv_min", "hv_max",
    "hv_minus_hh_mean", "hv_minus_hh_std",   # HV/HH ratio in dB, dates with both
    "hh_variability", "hv_variability",      # mean absolute step between seen dates
    "hh_drop_size", "hh_drop_doy", "hh_rise_size", "hh_rise_doy",
    "hv_drop_size", "hv_drop_doy", "hv_rise_size", "hv_rise_doy",
    "dark_fraction",                          # share of HH dates darker than the water threshold
    "n_valid_hh", "n_valid_hv",
]


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    """Otsu threshold of a sample (NaNs ignored)."""
    v = values[np.isfinite(values)]
    if v.size == 0:
        raise ValueError("no finite values for the Otsu threshold")
    hist, edges = np.histogram(v, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centres) / np.maximum(w0, 1)
    m1 = (np.sum(hist * centres) - np.cumsum(hist * centres)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    # Well-separated modes leave a flat maximum across the empty gap between
    # them; take its middle rather than its edge next to one mode.
    best = np.flatnonzero(between >= between.max() * (1 - 1e-9))
    return float(centres[best].mean())


def _day_of_year(times: np.ndarray) -> np.ndarray:
    days = times.astype("datetime64[D]")
    years = days.astype("datetime64[Y]")
    return (days - years).astype(int) + 1


def _steps(a: np.ndarray) -> np.ndarray:
    """(t-1, n) change from the last seen value to date i+1; NaN where i+1 is not seen."""
    t, n = a.shape
    last = a[0].copy()
    out = np.full((t - 1, n), np.nan)
    for i in range(1, t):
        seen = np.isfinite(a[i])
        ok = seen & np.isfinite(last)
        out[i - 1, ok] = a[i, ok] - last[ok]
        last[seen] = a[i, seen]
    return out


def _step_features(steps: np.ndarray, doy: np.ndarray) -> list[np.ndarray]:
    """Variability, biggest drop (size, doy), biggest rise (size, doy)."""
    n = steps.shape[1]
    has = np.isfinite(steps).any(axis=0)
    cols = np.arange(n)
    i_drop = np.argmin(np.where(np.isfinite(steps), steps, np.inf), axis=0)
    i_rise = np.argmax(np.where(np.isfinite(steps), steps, -np.inf), axis=0)
    safe = np.where(np.isfinite(steps), steps, 0.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        variability = np.nanmean(np.abs(steps), axis=0)
    return [
        variability,
        np.where(has, np.maximum(-safe[i_drop, cols], 0.0), np.nan),
        np.where(has, doy[1:][i_drop], np.nan),
        np.where(has, np.maximum(safe[i_rise, cols], 0.0), np.nan),
        np.where(has, doy[1:][i_rise], np.nan),
    ]


def pixel_features(
    hh_db: np.ndarray,
    hv_db: np.ndarray,
    times: np.ndarray,
    dark_threshold_db: float | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Build the feature matrix.

    hh_db, hv_db: (t, y, x), NaN where not seen. times: (t,) datetime64.
    Returns X (y*x, n_features) float32, usable (y*x,) bool, and the HH dark
    threshold used (Otsu over every seen HH value unless given).
    """
    if hh_db.shape != hv_db.shape:
        raise ValueError("hh_db and hv_db must have the same shape")
    t, h, w = hh_db.shape
    if t < 2:
        raise ValueError("need at least 2 dates")
    hh = hh_db.reshape(t, h * w).astype(np.float64)
    hv = hv_db.reshape(t, h * w).astype(np.float64)
    doy = _day_of_year(np.asarray(times))

    if dark_threshold_db is None:
        dark_threshold_db = otsu_threshold(hh.ravel())

    n_hh = np.isfinite(hh).sum(axis=0)
    n_hv = np.isfinite(hv).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN pixels
        ratio = hv - hh  # NaN unless both seen
        hh_steps, hv_steps = _step_features(_steps(hh), doy), _step_features(_steps(hv), doy)
        cols = [
            np.nanmean(hh, 0), np.nanstd(hh, 0), np.nanmin(hh, 0), np.nanmax(hh, 0),
            np.nanmean(hv, 0), np.nanstd(hv, 0), np.nanmin(hv, 0), np.nanmax(hv, 0),
            np.nanmean(ratio, 0), np.nanstd(ratio, 0),
            hh_steps[0], hv_steps[0],
            *hh_steps[1:],
            *hv_steps[1:],
            np.where(n_hh > 0, (hh < dark_threshold_db).sum(0) / np.maximum(n_hh, 1), np.nan),
            n_hh.astype(np.float64), n_hv.astype(np.float64),
        ]
    X = np.stack(cols, axis=1).astype(np.float32)
    assert X.shape[1] == len(FEATURE_NAMES)
    usable = (n_hh >= config.MIN_VALID_DATES) & (n_hv >= config.MIN_VALID_DATES)
    return X, usable, dark_threshold_db
