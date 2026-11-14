"""Small transparent baselines. Fits consume only observations passed by callers."""

from dataclasses import dataclass

import numpy as np

MODEL_NAMES = ("persistence", "linear", "trend_seasonal")
YEAR_DAYS = 365.25


def _features(days: np.ndarray, origin: float, seasonal: bool) -> np.ndarray:
    t = (days - origin) / YEAR_DAYS
    columns = [np.ones(len(days)), t]
    if seasonal:
        columns.extend((np.sin(2 * np.pi * t), np.cos(2 * np.pi * t)))
    return np.column_stack(columns)


@dataclass(frozen=True)
class Fit:
    name: str
    origin: float
    coefficients: np.ndarray

    def predict(self, days: np.ndarray) -> np.ndarray:
        days = np.atleast_1d(days).astype(float)
        if self.name == "persistence":
            return np.full(len(days), self.coefficients[0])
        return _features(days, self.origin, self.name == "trend_seasonal") @ self.coefficients


def fit_model(name: str, days: np.ndarray, values: np.ndarray) -> Fit:
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown model {name}")
    if len(days) == 0 or days.shape != values.shape:
        raise ValueError("Fit needs equally sized, nonempty day and value arrays")
    if not np.all(np.isfinite(days)) or not np.all(np.isfinite(values)):
        raise ValueError("Fit inputs must be finite")
    if np.any(np.diff(days) <= 0):
        raise ValueError("Fit dates must be unique and increasing")
    origin = float(days[-1])
    if name == "persistence":
        return Fit(name, origin, np.array([values[-1]], dtype=float))
    design = _features(days, origin, name == "trend_seasonal")
    coefficients, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    if rank < design.shape[1]:
        raise ValueError(f"Insufficient independent observations for {name}")
    return Fit(name, origin, coefficients)
