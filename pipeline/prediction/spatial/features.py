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
SOIL = ("soil_moisture", "soil_moisture_age_d", "soil_moisture_missing")   # NISAR SME2, optional
SENSOR = ("target_is_nisar", "prev_is_nisar")   # which radar the target and the previous map come from, optional
NEIGH = ("prev_wet_share_100m", "prev_wet_share_500m")   # water around a pixel in the issue-time map, optional
NEIGH_SIZES = (5, 25)                    # square windows in pixels (100 m and 500 m on the 20 m grid)
ALL = FEATURES + SOIL + SENSOR + NEIGH   # column order of every feature matrix
TERRAIN_ONLY = STATIC + CONTEXT          # the comparison model: no rain, no previous water
CATEGORICAL = ("worldcover_class",)

UNITS = {
    "hand_m": "m above the nearest drainage (ASF GLO-30 HAND, 30 m)", "elevation_m": "m (Copernicus GLO-30)",
    "slope_deg": "degrees, from the elevation on the 20 m grid", "jrc_occurrence_pct": "% of 1984-2021 months with water (JRC)",
    "worldcover_class": "ESA WorldCover 2021 class code", "rice_flag": "1 inside the Albufera rice mask",
    "s1_wet_freq": "share of the passes up to the issue pass (never one from the held-out window) that saw water here",
    "soil_moisture": "m3/m3, newest NISAR SME2 map before the issue day (200 m, provisional)",
    "target_is_nisar": "1 when the water map to predict is NISAR's, 0 for Sentinel-1: the two radars see different water",
    "prev_is_nisar": "1 where the previous water map is NISAR's",
    "prev_wet_share_100m": "share of water among the observed pixels of the issue-time map in the 100 m square around the pixel",
    "prev_wet_share_500m": "the same in the 500 m square",
    "soil_moisture_age_d": "days from that map to the target", "soil_moisture_missing": "1 where there is no such map",
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
               max_age: float = MAX_OBS_AGE_DAYS, source: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Latest known water state per pixel at passes j, j-1, ... and its age at the target, both NaN if unknown.

    get(k) returns the 0 / 1 / 255 water codes of pass k for the n pixels.
    If an int array `source` is given, it receives the pass index each state came from (-1 if none).
    """
    if source is not None:
        source[:] = -1
    state = np.full(n, np.nan, dtype="float32")
    age = np.full(n, np.nan, dtype="float32")
    k = j
    while k >= 0 and (times[j] - times[k]) / np.timedelta64(1, "D") <= max_age:
        w = get(k)
        take = np.isnan(state) & (w != UNKNOWN)
        state[take] = w[take]
        age[take] = (target_time - times[k]) / np.timedelta64(1, "D")
        if source is not None:
            source[take] = k
        if not np.isnan(state).any():
            break
        k -= 1
    return state, age


def wet_frequency(wet_count: np.ndarray, obs_count: np.ndarray) -> np.ndarray:
    """Share of the counted passes that saw water; NaN with fewer than MIN_FREQ_OBS observations."""
    n = obs_count.astype("float32")
    with np.errstate(invalid="ignore", divide="ignore"):
        f = wet_count.astype("float32") / n
    return np.where(n >= MIN_FREQ_OBS, f, np.nan).astype("float32")


def assemble(static_cols: np.ndarray, freq: np.ndarray, target_day: int, lead_days: float,
             rain: dict[str, float], state: np.ndarray, age: np.ndarray,
             soil: np.ndarray | None = None, soil_age: float | None = None,
             target_nisar: bool = False, prev_nisar: np.ndarray | None = None,
             neigh: np.ndarray | None = None) -> np.ndarray:
    """(n, len(ALL)) float32 in ALL order; the soil and neighbourhood columns are missing unless given."""
    n = static_cols.shape[0]
    soil = np.full(n, np.nan, "float32") if soil is None else soil
    neigh = np.full((n, len(NEIGH)), np.nan, "float32") if neigh is None else neigh
    doy = date.fromordinal(int(target_day)).timetuple().tm_yday
    ang = 2 * np.pi * doy / 365.25
    cols = {
        "s1_wet_freq": freq, "doy_sin": np.full(n, np.sin(ang)), "doy_cos": np.full(n, np.cos(ang)),
        **{k: np.full(n, rain[k]) for k in RAIN if k != "lead_days"}, "lead_days": np.full(n, lead_days),
        "prev_water": state, "prev_water_age_d": age, "prev_water_missing": np.isnan(state).astype("float32"),
        "target_is_nisar": np.full(n, float(target_nisar)),
        "prev_is_nisar": np.zeros(n) if prev_nisar is None else prev_nisar,
        "soil_moisture": soil, "soil_moisture_missing": np.isnan(soil).astype("float32"),
        "soil_moisture_age_d": np.where(np.isnan(soil), np.nan, np.nan if soil_age is None else soil_age),
        **{name: neigh[:, i] for i, name in enumerate(NEIGH)},
    }
    dyn = np.stack([np.asarray(cols[name], dtype="float32") for name in ALL[len(STATIC):]], axis=1)
    return np.concatenate([static_cols.astype("float32"), dyn], axis=1)


def neighbourhood(state: np.ndarray) -> np.ndarray:
    """(len(NEIGH), y, x) share of water among the observed pixels in squares of NEIGH_SIZES around each pixel.

    state: (y, x) issue-time water map, 1 water, 0 dry, NaN unknown. NaN where a square holds no observed pixel.
    Outside the grid counts as unknown.
    """
    from scipy import ndimage
    known = np.isfinite(state).astype("float64")
    wet = (state == 1).astype("float64")
    out = np.full((len(NEIGH_SIZES),) + state.shape, np.nan, dtype="float32")
    for i, size in enumerate(NEIGH_SIZES):
        k = ndimage.uniform_filter(known, size, mode="constant") * size * size
        w = ndimage.uniform_filter(wet, size, mode="constant") * size * size
        ok = k > 0.5
        out[i][ok] = (w[ok] / k[ok]).astype("float32")
    return np.clip(out, 0.0, 1.0)


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
                dry_keep: float = 0.1, soil=None, is_nisar: np.ndarray | None = None, neigh=None,
                fit: np.ndarray | None = None, only: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Samples of every target pass outside the held-out window.

    pool_water: (passes, pixels) 0 / 1 / 255. Dry samples are thinned to dry_keep
    and weighted back up. The past wet share of a sample counts only passes up to
    its issue pass, so nothing later than the issue time enters it.
    soil(issue_day, target_day) returns (values per pool pixel or None, age in days).
    is_nisar flags the NISAR passes, for the two sensor columns.
    neigh(j) returns the neighbourhood columns (pixels, len(NEIGH)) of issue pass j, for the optional NEIGH inputs.
    fit (passes that may be targets and count in the past wet share; default: every pass outside the held-out window)
    and only (restrict the targets further) are for the fit-then-test version, which adds held-out passes of one site.
    """
    nisar = np.zeros(len(days), bool) if is_nisar is None else is_nisar
    src = np.empty(pool_water.shape[1], dtype="int64")
    fit = np.array([not in_holdout(d) for d in days]) if fit is None else np.asarray(fit, bool)
    cum_wet = np.cumsum((pool_water == 1) & fit[:, None], axis=0, dtype="int16")
    cum_obs = np.cumsum((pool_water != UNKNOWN) & fit[:, None], axis=0, dtype="int16")
    X, y, w, tt, pp = [], [], [], [], []
    for t in range(len(days)):
        if not fit[t] or (only is not None and not only[t]):
            continue                      # the held-out storm never enters the table (unless fit says so)
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
        state, age = prev_state(lambda k: pool_water[k], times, j, times[t], lab.size, source=src)
        freq = wet_frequency(cum_wet[j], cum_obs[j])
        lead = float((times[t] - times[j]) / np.timedelta64(1, "D"))
        sm, sm_age = soil(days[j], days[t]) if soil is not None else (None, None)
        feats = assemble(static_cols, freq, target_day, lead, rain_features(rain, issue_day, target_day), state, age,
                         sm, sm_age, bool(nisar[t]), np.where(src >= 0, nisar[np.maximum(src, 0)], False),
                         None if neigh is None else neigh(j))
        X.append(feats[keep]); y.append(lab[keep]); tt.append(np.full(int(keep.sum()), t, "int32"))
        pp.append(np.flatnonzero(keep).astype("int32"))
        w.append(pool_weight[keep] * np.where(lab[keep] == 1, 1.0, 1.0 / dry_keep))
    return {"X": np.concatenate(X), "y": np.concatenate(y).astype("uint8"), "w": np.concatenate(w).astype("float32"),
            "t": np.concatenate(tt), "p": np.concatenate(pp)}


# ---------------------------------------------------------------- soil moisture (NISAR SME2)

def soil_reader(site: str, idx: np.ndarray):
    """soil(issue_day, target_day) -> (soil moisture at the idx pixels or None, days from that map to the target).

    Uses the newest SME2 map at least one day before the issue day (pipeline.soil_moisture). The 72 hour
    product latency is not modelled, so in a replay the map may be up to two days too fresh.
    """
    from pipeline import soil_moisture as sm
    days_available = sm.dates_of(site)
    cache: dict[str, np.ndarray] = {}

    def soil(issue_day: str, target_day: str):
        pick = sm.latest_day_before(days_available, issue_day)
        if pick is None:
            return None, None
        if pick not in cache:
            cache[pick] = sm.load_day(site, pick).ravel()[idx]
        return cache[pick], float((date.fromisoformat(target_day) - date.fromisoformat(pick)).days)
    return soil
