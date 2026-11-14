"""Seasonal flooded-area models, season-held-out backtests and the forecast.

Seasons run 1 Aug to 31 Jul (the rice year: harvest in September, winter
flooding from about November, drained and replanted in spring), named by the
year they start in.

Models, all predicting flooded hectares at a target date from an origin date:

- ``persistence``: the recent level (median of observations in the last few days).
- ``climatology``: median of reference-season observations within +-N days of the
  target's day of year.
- ``damped_anomaly``: climatology at the target plus today's departure from
  climatology, decaying with an e-folding time fixed in advance (not tuned,
  because two complete seasons leave nothing to tune it on honestly).

Evaluation:

- ``selection`` folds: each complete past season, with climatology from the
  *other* past seasons. Picks the model per lead and calibrates the ranges.
- ``test`` fold: the current season, with climatology only from earlier seasons,
  exactly as the live forecast works. Never used to choose anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import numpy as np

from pipeline.prediction.evaluation import interval_radius

MODELS = ("persistence", "climatology", "damped_anomaly")
SEASON_START_MONTH = 8


@dataclass(frozen=True)
class Settings:
    half_window_days: int = 10     # climatology: +- days of year
    recent_days: int = 6           # level: median of observations in the last N days
    tau_days: float = 30.0         # damped anomaly e-folding time, fixed a priori
    stride_days: int = 3           # backtest origins at least this far apart
    tolerance_days: int = 3        # nearest observed target within this many days
    min_selection_n: int = 5


def season_of(day: date) -> int:
    return day.year if day.month >= SEASON_START_MONTH else day.year - 1


def day_of_year(ordinal: int) -> int:
    return date.fromordinal(int(ordinal)).timetuple().tm_yday


def daily_series(rows: list[dict], mask_ha: float) -> tuple[np.ndarray, np.ndarray]:
    """One value per date from usable passes: flooded share of the observed mask x mask area.

    Scaling by the observed share treats the unobserved few percent like the rest
    of the mask. Several passes on one day are averaged.
    """
    by_day: dict[int, list[float]] = {}
    for r in rows:
        if str(r["usable"]).lower() not in ("true", "1") or r["flooded_share_of_observed"] in ("", None):
            continue
        by_day.setdefault(date.fromisoformat(r["date"]).toordinal(), []).append(
            float(r["flooded_share_of_observed"]) * mask_ha)
    days = np.array(sorted(by_day), dtype=float)
    values = np.array([np.mean(by_day[int(d)]) for d in days], dtype=float)
    return days, values


def climatology(ref_days: np.ndarray, ref_values: np.ndarray, query_days: np.ndarray,
                half_window: int) -> np.ndarray:
    """Median reference value within +-half_window days of each query's day of year (circular)."""
    ref_doy = np.array([day_of_year(d) for d in ref_days])
    out = np.full(len(query_days), np.nan)
    for i, q in enumerate(query_days):
        diff = np.abs(ref_doy - day_of_year(q))
        diff = np.minimum(diff, 365 - diff)
        near = ref_values[diff <= half_window]
        if near.size:
            out[i] = float(np.median(near))
    return out


def recent_level(days: np.ndarray, values: np.ndarray, origin: float, recent_days: int) -> float:
    keep = (days <= origin) & (days > origin - recent_days)
    if not keep.any():
        raise ValueError("No observation in the recent window")
    return float(np.median(values[keep]))


def predict_all(level: float, clim_origin: float, clim_target: float, lead: float, tau: float) -> dict[str, float]:
    """The three model predictions for one origin/target pair (NaN if climatology is missing)."""
    return {
        "persistence": level,
        "climatology": clim_target,
        "damped_anomaly": clim_target + (level - clim_origin) * math.exp(-lead / tau),
    }


def folds(days: np.ndarray) -> list[dict]:
    """Selection folds (each past season vs the other past seasons) and the test fold (current season)."""
    seasons = sorted({season_of(date.fromordinal(int(d))) for d in days})
    if len(seasons) < 3:
        raise ValueError(f"Need at least two past seasons and the current one; have {seasons}")
    *past, current = seasons
    out = [{"role": "selection", "test_season": s, "ref_seasons": [p for p in past if p != s]} for s in past]
    out.append({"role": "test", "test_season": current, "ref_seasons": past})
    return out


def backtest(days: np.ndarray, values: np.ndarray, leads: list[int], settings: Settings) -> list[dict]:
    season = np.array([season_of(date.fromordinal(int(d))) for d in days])
    rows = []
    for fold in folds(days):
        ref = np.isin(season, fold["ref_seasons"])
        test = season == fold["test_season"]
        t_days, t_vals = days[test], values[test]
        last_origin = -math.inf
        for i, origin in enumerate(t_days):
            if origin - last_origin < settings.stride_days:
                continue
            last_origin = origin
            level = recent_level(t_days, t_vals, origin, settings.recent_days)
            for lead in leads:
                nominal = origin + lead
                cand = np.where((t_days > origin) & (np.abs(t_days - nominal) <= settings.tolerance_days))[0]
                if not cand.size:
                    continue
                j = int(cand[np.argmin(np.abs(t_days[cand] - nominal))])
                clim = climatology(days[ref], values[ref], np.array([origin, t_days[j]]), settings.half_window_days)
                if np.isnan(clim).any():
                    continue
                actual_lead = float(t_days[j] - origin)
                for model, pred in predict_all(level, clim[0], clim[1], actual_lead, settings.tau_days).items():
                    rows.append({
                        "role": fold["role"], "test_season": fold["test_season"],
                        "ref_seasons": "+".join(map(str, fold["ref_seasons"])), "model": model,
                        "origin": date.fromordinal(int(origin)).isoformat(),
                        "target_date": date.fromordinal(int(t_days[j])).isoformat(),
                        "lead_days": lead, "actual_lead_days": int(actual_lead),
                        "predicted_ha": round(pred, 2), "observed_ha": round(float(t_vals[j]), 2),
                        "error_ha": round(float(t_vals[j]) - pred, 2),
                    })
    return rows


def score(rows: list[dict], calibration: list[dict] | None = None) -> dict:
    """MAE, RMSE, skill vs persistence per lead and model; interval coverage if calibration is given."""
    out: dict[str, dict] = {}
    for lead in sorted({r["lead_days"] for r in rows}):
        out[str(lead)] = {}
        for model in MODELS:
            err = np.array([r["error_ha"] for r in rows if r["lead_days"] == lead and r["model"] == model])
            if not err.size:
                continue
            item = {"n": int(err.size), "mae_ha": round(float(np.mean(np.abs(err))), 2),
                    "rmse_ha": round(float(np.sqrt(np.mean(err ** 2))), 2)}
            if calibration is not None:
                ref = [r["error_ha"] for r in calibration if r["lead_days"] == lead and r["model"] == model]
                item["intervals"] = {}
                for label, cov in (("80", 0.8), ("95", 0.95)):
                    radius = interval_radius(ref, cov)
                    item["intervals"][label] = {
                        "calibration_n": len(ref), "radius_ha": None if radius is None else round(radius, 2),
                        "empirical_coverage": None if radius is None else round(float(np.mean(np.abs(err) <= radius)), 3),
                    }
            out[str(lead)][model] = item
        base = out[str(lead)].get("persistence", {}).get("mae_ha")
        for item in out[str(lead)].values():
            item["skill_vs_persistence"] = None if not base else round(1 - item["mae_ha"] / base, 3)
    return out


def select(selection_scores: dict, min_n: int) -> dict[int, str]:
    """Lowest selection-fold MAE per lead. The test fold is never consulted."""
    chosen = {}
    for lead, scores in selection_scores.items():
        eligible = [m for m in MODELS if scores.get(m, {}).get("n", 0) >= min_n]
        if not eligible:
            raise ValueError(f"Too few selection forecasts at lead {lead} days (need {min_n})")
        chosen[int(lead)] = min(eligible, key=lambda m: scores[m]["mae_ha"])
    return chosen


def forecast(days: np.ndarray, values: np.ndarray, as_of: date, horizons: list[int], mask_ha: float,
             settings: Settings) -> dict:
    """Backtest, select, calibrate and forecast from observations on or before as_of."""
    keep = days <= as_of.toordinal()
    days, values = days[keep], values[keep]
    if not days.size:
        raise ValueError("No observations on or before the forecast origin")
    last = days[-1]
    targets = [as_of.toordinal() + h for h in horizons]
    effective = sorted({int(t - last) for t in targets})
    leads = sorted(set(horizons) | set(effective))
    rows = backtest(days, values, leads, settings)
    selection = [r for r in rows if r["role"] == "selection"]
    test = [r for r in rows if r["role"] == "test"]
    sel_scores = score(selection)
    chosen = select({str(l): sel_scores.get(str(l), {}) for l in effective}, settings.min_selection_n)

    season = np.array([season_of(date.fromordinal(int(d))) for d in days])
    current = season_of(date.fromordinal(int(last)))
    ref = season != current
    level = recent_level(days, values, last, settings.recent_days)
    clim = climatology(days[ref], values[ref], np.array([last, *targets], dtype=float), settings.half_window_days)

    predictions, alternatives = [], []
    for h, target, c_target in zip(horizons, targets, clim[1:]):
        lead = int(target - last)
        preds = predict_all(level, clim[0], c_target, lead, settings.tau_days)
        for model, value in preds.items():
            errors = [r["error_ha"] for r in selection if r["model"] == model and r["lead_days"] == lead]
            intervals = {}
            for label, cov in (("80", 0.8), ("95", 0.95)):
                radius = interval_radius(errors, cov)
                intervals[label] = {
                    "lower_ha": None if radius is None or math.isnan(value) else round(max(0.0, value - radius), 1),
                    "upper_ha": None if radius is None or math.isnan(value) else round(min(mask_ha, value + radius), 1),
                    "radius_ha": None if radius is None else round(radius, 1),
                    "calibration_n": len(errors), "status": "available" if radius is not None else "unavailable",
                }
            item = {"horizon_days": h, "target_date": date.fromordinal(target).isoformat(),
                    "effective_lead_days": lead, "model": model,
                    "value_ha": None if math.isnan(value) else round(value, 1), "intervals": intervals}
            alternatives.append(item)
            if model == chosen[lead]:
                predictions.append(item)

    return {
        "predictions": predictions,
        "model_predictions": alternatives,
        "selected_models_by_lead": {str(k): v for k, v in chosen.items()},
        "data_cutoff": date.fromordinal(int(last)).isoformat(),
        "observation_age_days": int(as_of.toordinal() - last),
        "recent_level_ha": round(level, 1),
        "climatology_at_cutoff_ha": None if math.isnan(clim[0]) else round(float(clim[0]), 1),
        "current_season": current,
        "reference_seasons": sorted(set(int(s) for s in season[ref])),
        "scores": {"selection": sel_scores, "test": score(test, selection)},
        "backtest_rows": rows,
        "series": (days, values),
    }
