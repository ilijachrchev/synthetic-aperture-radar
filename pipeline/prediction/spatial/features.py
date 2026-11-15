"""Features of one (pixel, target pass) sample, built the same way for training and for a map.

Times. Every sample has a target pass and an issue pass: the latest pass at least
MIN_LEAD_DAYS before the target. Only water maps up to the issue pass, rain
before the issue day ("prior") and rain from the issue day to the day before the
target ("between") are used. In training and in the replays the "between" rain is
the rain that really fell (IFS archive), so those scores are a reconstruction,
not a forecast score. In a scenario it is the rain amount the user picks.

Rain is one number per site and day (the wettest IFS lattice point, from
``data/prediction/flood/rain_<site>.csv``), so it does not vary inside a site.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import numpy as np
import rasterio

from pipeline.config import DATA_DIR

from . import HOLDOUT_END, HOLDOUT_START
from .labels import UNKNOWN
from .terrain import static_dir

CONTEXT_DIR = DATA_DIR / "context"
RICE_MASK = DATA_DIR / "prediction" / "albufera" / "rice_mask.tif"
RAIN_DIR = DATA_DIR / "prediction" / "flood"

MIN_LEAD_DAYS = 3.0     # the issue pass is at least this long before the target
MAX_LEAD_DAYS = 12.0    # targets with no pass in this window are left out
MAX_OBS_AGE_DAYS = 10.0 # a pixel not seen at the issue pass may use an older pass, up to this much older
MIN_FREQ_OBS = 20       # passes needed before a pixel's past wet share is trusted
JRC_PERMANENT = 90
WORLDCOVER_URBAN = 50

STATIC = ("hand_m", "elevation_m", "slope_deg", "jrc_occurrence_pct", "worldcover_class", "rice_flag")
CONTEXT = ("s1_wet_freq", "doy_sin", "doy_cos")
RAIN = ("rain_prior_7d_mm", "rain_prior_30d_mm", "rain_between_mm", "rain_between_max1d_mm",
        "days_since_rain_peak", "lead_days")
STATE = ("prev_water", "prev_water_age_d", "prev_water_missing")
FEATURES = STATIC + CONTEXT + RAIN + STATE
TERRAIN_ONLY = STATIC + CONTEXT          # the comparison model: no rain, no previous water
CATEGORICAL = ("worldcover_class",)

UNITS = {
    "hand_m": "m above the nearest drainage (ASF GLO-30 HAND, 30 m)", "elevation_m": "m (Copernicus GLO-30)",
    "slope_deg": "degrees, from the elevation on the 20 m grid", "jrc_occurrence_pct": "% of 1984-2021 months with water (JRC)",
    "worldcover_class": "ESA WorldCover 2021 class code", "rice_flag": "1 inside the Albufera rice mask",
    "s1_wet_freq": "share of earlier Sentinel-1 passes (before the held-out window) that saw water here",
    "doy_sin": "season", "doy_cos": "season",
    "rain_prior_7d_mm": "mm in the 7 days before the issue day", "rain_prior_30d_mm": "mm in the 30 days before the issue day",
    "rain_between_mm": "mm from the issue day to the day before the target",
    "rain_between_max1d_mm": "wettest day of that interval, mm", "days_since_rain_peak": "days from that wettest day to the target",
    "lead_days": "days from the issue pass to the target", "prev_water": "1 water, 0 dry at the latest pass up to the issue pass",
    "prev_water_age_d": "days from that observation to the target", "prev_water_missing": "1 where no such observation exists",
}


def in_holdout(day: str) -> bool:
    return HOLDOUT_START <= day <= HOLDOUT_END


# ---------------------------------------------------------------- static layers

def _read(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1)


def load_static(site: str) -> dict[str, np.ndarray]:
    wc = _read(CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif")
    jrc = _read(CONTEXT_DIR / f"{site}_jrc_occurrence_20m.tif")
    sea = _read(CONTEXT_DIR / f"{site}_sea_20m.tif")
    d = static_dir(site)
    out = {name: _read(d / f"{name}.tif") for name in ("hand_m", "elevation_m", "slope_deg")}
    rice = _read(RICE_MASK) if site == "albufera" else np.zeros(wc.shape, "uint8")
    for name, arr in (("worldcover", wc), ("jrc", jrc), ("sea", sea), ("rice", rice), *out.items()):
        if arr.shape != wc.shape:
            raise ValueError(f"{site}: {name} is {arr.shape}, the grid is {wc.shape}")
    out["jrc_occurrence_pct"] = np.where(jrc == 255, np.nan, jrc).astype("float32")
    out["worldcover_class"] = wc.astype("float32")
    out["rice_flag"] = (rice > 0).astype("float32")
    out["land"] = (sea == 0) & (wc != 0)
    out["permanent"] = (jrc >= JRC_PERMANENT) & (jrc != 255)
    out["urban"] = wc == WORLDCOVER_URBAN
    return out


def train_domain(static: dict) -> np.ndarray:
    """Pixels the model may learn from: land, not permanent water, not urban, with terrain."""
    return static["land"] & ~static["permanent"] & ~static["urban"] & np.isfinite(static["hand_m"])


def static_columns(static: dict, idx: np.ndarray) -> np.ndarray:
    return np.stack([static[name].ravel()[idx].astype("float32") for name in STATIC], axis=1)


# ---------------------------------------------------------------- rain

def load_rain(site: str, rain_dir: Path = RAIN_DIR) -> dict[int, float]:
    """{ordinal day: site rain in mm}; a missing value stays missing (NaN)."""
    out = {}
    with (rain_dir / f"rain_{site}.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[date.fromisoformat(row["date"]).toordinal()] = float(row["max_mm"]) if row["max_mm"] not in ("", "nan") else float("nan")
    return out


def _days(rain: dict[int, float], first: int, last: int) -> np.ndarray:
    """Rain of the days first..last inclusive; NaN for a day not in the table."""
    return np.array([rain.get(d, np.nan) for d in range(first, last + 1)], dtype="float64")


def rain_features(rain: dict[int, float], issue_day: int, target_day: int) -> dict[str, float]:
    """Rain before the issue day and from the issue day to the day before the target (the target day may rain after the pass)."""
    between = _days(rain, issue_day, target_day - 1)
    out = {"rain_prior_7d_mm": float(_days(rain, issue_day - 7, issue_day - 1).sum()),
           "rain_prior_30d_mm": float(_days(rain, issue_day - 30, issue_day - 1).sum())}
    if between.size == 0 or not np.all(np.isfinite(between)):
        out.update(rain_between_mm=np.nan, rain_between_max1d_mm=np.nan, days_since_rain_peak=np.nan)
    else:
        peak = int(np.argmax(between))
        out.update(rain_between_mm=float(between.sum()), rain_between_max1d_mm=float(between[peak]),
                   days_since_rain_peak=float(between.size - peak))
    return out


# ---------------------------------------------------------------- time and state

def issue_before(times: np.ndarray, target_time, min_lead: float = MIN_LEAD_DAYS, max_lead: float = MAX_LEAD_DAYS,
                 not_after=None) -> int | None:
    """Index of the latest pass at least min_lead days before a target time (and not after not_after), or None."""
    cutoff = target_time - np.timedelta64(int(min_lead * 86400), "s")
    if not_after is not None:
        cutoff = min(cutoff, not_after)
    j = int(np.searchsorted(times, cutoff, side="right")) - 1
    if j < 0 or (target_time - times[j]) / np.timedelta64(1, "D") > max_lead:
        return None
    return j


def issue_index(times: np.ndarray, t: int, min_lead: float = MIN_LEAD_DAYS, max_lead: float = MAX_LEAD_DAYS) -> int | None:
    """Index of the latest pass at least min_lead days before pass t, or None if none within max_lead."""
    return issue_before(times, times[t], min_lead, max_lead)


def prev_state(get, times: np.ndarray, j: int, target_time, n: int,
               max_age: float = MAX_OBS_AGE_DAYS) -> tuple[np.ndarray, np.ndarray]:
    """Latest known water state per pixel at passes j, j-1, ... and its age at the target, both NaN if unknown.

    get(k) returns the 0 / 1 / 255 water codes of pass k for the n pixels.
    """
    state = np.full(n, np.nan, dtype="float32")
    age = np.full(n, np.nan, dtype="float32")
    k = j
    while k >= 0 and (times[j] - times[k]) / np.timedelta64(1, "D") <= max_age:
        w = get(k)
        take = np.isnan(state) & (w != UNKNOWN)
        state[take] = w[take]
        age[take] = (target_time - times[k]) / np.timedelta64(1, "D")
        if not np.isnan(state).any():
            break
        k -= 1
    return state, age


def wet_frequency(wet_count: np.ndarray, obs_count: np.ndarray, minus_wet=0, minus_obs=0) -> np.ndarray:
    """Share of earlier passes that saw water; the optional terms leave the sample's own pass out."""
    n = obs_count.astype("float32") - minus_obs
    with np.errstate(invalid="ignore", divide="ignore"):
        f = (wet_count.astype("float32") - minus_wet) / n
    return np.where(n >= MIN_FREQ_OBS, f, np.nan).astype("float32")


def assemble(static_cols: np.ndarray, freq: np.ndarray, target_day: int, lead_days: float,
             rain: dict[str, float], state: np.ndarray, age: np.ndarray) -> np.ndarray:
    """(n, len(FEATURES)) float32 in FEATURES order."""
    n = static_cols.shape[0]
    doy = date.fromordinal(int(target_day)).timetuple().tm_yday
    ang = 2 * np.pi * doy / 365.25
    cols = {
        "s1_wet_freq": freq, "doy_sin": np.full(n, np.sin(ang)), "doy_cos": np.full(n, np.cos(ang)),
        **{k: np.full(n, rain[k]) for k in RAIN if k != "lead_days"}, "lead_days": np.full(n, lead_days),
        "prev_water": state, "prev_water_age_d": age, "prev_water_missing": np.isnan(state).astype("float32"),
    }
    dyn = np.stack([np.asarray(cols[name], dtype="float32") for name in FEATURES[len(STATIC):]], axis=1)
    return np.concatenate([static_cols.astype("float32"), dyn], axis=1)


# ---------------------------------------------------------------- training table

def counts(water_stack_get, n_passes: int, keep: np.ndarray, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """(wet passes, observed passes) per pixel over the passes flagged in keep."""
    wet = np.zeros(shape, dtype="int32")
    obs = np.zeros(shape, dtype="int32")
    for k in range(n_passes):
        if keep[k]:
            w = water_stack_get(k)
            wet += w == 1
            obs += w != UNKNOWN
    return wet, obs


def pick_pool(domain: np.ndarray, wet: np.ndarray, obs: np.ndarray, size: int, rng: np.random.Generator,
              min_obs_share: float = 0.5, n_fit: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Flat pixel indices to learn from and their weights: half ever-wet pixels, half never-wet.

    The weight is how many domain pixels one pool pixel stands for, so weighted
    scores describe the whole domain and not the oversampled wet part.
    """
    n_fit = int(obs.max()) if n_fit is None else n_fit
    ok = domain & (obs >= min_obs_share * n_fit)
    idx_all, w_all = [], []
    for sel in (ok & (wet > 0), ok & (wet == 0)):
        cand = np.flatnonzero(sel.ravel())
        if cand.size == 0:
            continue
        take = rng.choice(cand, size=min(size // 2, cand.size), replace=False)
        idx_all.append(take)
        w_all.append(np.full(take.size, cand.size / take.size, dtype="float32"))
    idx = np.concatenate(idx_all)
    order = np.argsort(idx)
    return idx[order], np.concatenate(w_all)[order]


def build_table(pool_water: np.ndarray, times: np.ndarray, days: list[str], static_cols: np.ndarray,
                pool_weight: np.ndarray, rain: dict[int, float], rng: np.random.Generator,
                dry_keep: float = 0.1) -> dict[str, np.ndarray]:
    """Samples of every target pass outside the held-out window.

    pool_water: (passes, pixels) 0 / 1 / 255. Dry samples are thinned to dry_keep
    and weighted back up. The past wet share of a sample leaves its own pass out.
    """
    fit = np.array([not in_holdout(d) for d in days])
    wet_n = (pool_water[fit] == 1).sum(axis=0)
    obs_n = (pool_water[fit] != UNKNOWN).sum(axis=0)
    X, y, w, tt, pp = [], [], [], [], []
    for t in range(len(days)):
        if not fit[t]:
            continue                      # the held-out storm never enters the table
        j = issue_index(times, t)
        if j is None:
            continue
        lab = pool_water[t]
        valid = lab != UNKNOWN
        keep = valid & ((lab == 1) | (rng.random(lab.size) < dry_keep))
        if not keep.any():
            continue
        target_day = date.fromisoformat(days[t]).toordinal()
        issue_day = date.fromisoformat(days[j]).toordinal()
        state, age = prev_state(lambda k: pool_water[k], times, j, times[t], lab.size)
        freq = wet_frequency(wet_n, obs_n, minus_wet=(lab == 1), minus_obs=valid)
        lead = float((times[t] - times[j]) / np.timedelta64(1, "D"))
        feats = assemble(static_cols, freq, target_day, lead, rain_features(rain, issue_day, target_day), state, age)
        X.append(feats[keep]); y.append(lab[keep]); tt.append(np.full(int(keep.sum()), t, "int32"))
        pp.append(np.flatnonzero(keep).astype("int32"))
        w.append(pool_weight[keep] * np.where(lab[keep] == 1, 1.0, 1.0 / dry_keep))
    return {"X": np.concatenate(X), "y": np.concatenate(y).astype("uint8"), "w": np.concatenate(w).astype("float32"),
            "t": np.concatenate(tt), "p": np.concatenate(pp)}
