"""Rolling-origin backtests, independent calendar splits, and empirical intervals."""

from __future__ import annotations

from datetime import date
import math

import numpy as np

from .data import Series
from .models import MODEL_NAMES, fit_model


def training_window(series: Series, origin: float, window_days: int,
                    min_observations: int, min_span_days: int) -> tuple[np.ndarray, np.ndarray]:
    keep = (series.days <= origin) & (series.days >= origin - window_days)
    days, values = series.days[keep], series.values[keep]
    if len(days) < min_observations or days[-1] - days[0] < min_span_days:
        raise ValueError("Insufficient observed training history for the configured window")
    return days, values


def rolling_backtest(series: Series, start: date, end: date, horizons: tuple[int, ...],
                     *, window_days: int = 1096, stride_days: int = 7,
                     min_observations: int = 100, min_span_days: int = 730,
                     target_tolerance_days: int = 0) -> list[dict]:
    """Fit at each observed origin and evaluate only observed targets in this split.

    Missing dates are never filled. With nonzero tolerance, predict at the actual
    nearest observed target date, and record its distance from the requested date.
    """
    if start > end or stride_days <= 0 or window_days <= 0:
        raise ValueError("Backtest requires ordered dates and positive window/stride")
    if not horizons or any(h <= 0 for h in horizons) or target_tolerance_days < 0:
        raise ValueError("Backtest requires positive horizons and nonnegative tolerance")
    days = series.days
    output = []
    last_origin = -math.inf
    for index, origin in enumerate(days):
        if not start.toordinal() <= origin <= end.toordinal() or origin - last_origin < stride_days:
            continue
        try:
            train_days, train_values = training_window(
                series, origin, window_days, min_observations, min_span_days)
            fits = [fit_model(name, train_days, train_values) for name in MODEL_NAMES]
        except ValueError:
            continue
        last_origin = origin
        for horizon in horizons:
            nominal_target = origin + horizon
            insertion = int(np.searchsorted(days, nominal_target))
            candidates = [i for i in (insertion - 1, insertion) if index < i < len(days)
                          and start.toordinal() <= days[i] <= end.toordinal()]
            if not candidates:
                continue
            target = min(candidates, key=lambda i: (abs(days[i] - nominal_target), days[i]))
            if abs(days[target] - nominal_target) > target_tolerance_days:
                continue
            for fitted in fits:
                predicted = float(fitted.predict(np.array([days[target]]))[0])
                actual = float(series.values[target])
                output.append({
                    "model": fitted.name, "origin": series.dates[index].isoformat(),
                    "training_start": date.fromordinal(int(train_days[0])).isoformat(),
                    "training_end": date.fromordinal(int(train_days[-1])).isoformat(),
                    "training_observations": len(train_days), "horizon_days": horizon,
                    "target_date": series.dates[target].isoformat(),
                    "actual_horizon_days": int(days[target] - origin),
                    "predicted_mm": predicted, "observed_mm": actual,
                    "error_mm": actual - predicted,
                })
    return output


def interval_radius(errors: list[float], coverage: float) -> float | None:
    """Finite-sample absolute-error order statistic; unavailable if rank > n.

    Time dependence invalidates a general exchangeability coverage guarantee.
    These are historical-error ranges, whose held-out coverage must be reported.
    """
    if not 0 < coverage < 1:
        raise ValueError("Coverage must be between zero and one")
    if not errors:
        return None
    values = np.abs(np.array(errors, dtype=float))
    if not np.all(np.isfinite(values)):
        raise ValueError("Calibration errors must be finite")
    rank = math.ceil((len(values) + 1) * coverage)
    return None if rank > len(values) else float(np.sort(values)[rank - 1])


def summarize(rows: list[dict], calibration: list[dict] | None = None) -> dict:
    if not rows:
        return {}
    summary = {}
    for horizon in sorted({row["horizon_days"] for row in rows}):
        summary[str(horizon)] = {}
        for name in MODEL_NAMES:
            selected = [r for r in rows if r["horizon_days"] == horizon and r["model"] == name]
            errors = np.array([r["error_mm"] for r in selected])
            if not len(errors):
                continue
            item = {"n": len(errors), "mae_mm": float(np.mean(np.abs(errors))),
                    "rmse_mm": float(np.sqrt(np.mean(errors ** 2))),
                    "first_origin": min(r["origin"] for r in selected),
                    "last_origin": max(r["origin"] for r in selected),
                    "first_target": min(r["target_date"] for r in selected),
                    "last_target": max(r["target_date"] for r in selected)}
            if calibration is not None:
                reference = [r["error_mm"] for r in calibration
                             if r["horizon_days"] == horizon and r["model"] == name]
                item["intervals"] = {}
                for label, coverage in (("80", 0.8), ("95", 0.95)):
                    radius = interval_radius(reference, coverage)
                    item["intervals"][label] = {
                        "calibration_n": len(reference), "radius_mm": radius,
                        "empirical_coverage": None if radius is None else float(np.mean(np.abs(errors) <= radius)),
                        "mean_width_mm": None if radius is None else 2 * radius,
                    }
            summary[str(horizon)][name] = item
        baseline = summary[str(horizon)].get("persistence", {}).get("mae_mm")
        for item in summary[str(horizon)].values():
            item["skill_vs_persistence"] = None if baseline is None or baseline <= 1e-12 else 1 - item["mae_mm"] / baseline
    return summary


def select_models(selection_scores: dict) -> dict[int, str]:
    """Select on development scores only. Never consult final test scores."""
    chosen = {}
    for horizon, scores in selection_scores.items():
        eligible = [name for name in MODEL_NAMES if scores.get(name, {}).get("n", 0) >= 5]
        if not eligible:
            raise ValueError(f"Too few development forecasts for horizon {horizon}; need at least five")
        chosen[int(horizon)] = min(eligible, key=lambda name: scores[name]["mae_mm"])
    return chosen
