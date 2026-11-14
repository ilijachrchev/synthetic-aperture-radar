"""Small transparent baselines. Fits consume only observations passed by callers.

Trend models can take step dates (known equipment changes). Each step inside the
training window adds a 0/1 column, so a level jump at that date is not read as
trend. A step needs MIN_AFTER_STEP observations after it, otherwise it is left out.
"""

from dataclasses import dataclass

import numpy as np

MODEL_NAMES = ("persistence", "linear", "trend_seasonal")
YEAR_DAYS = 365.25
MIN_AFTER_STEP = 30


def _features(days: np.ndarray, origin: float, seasonal: bool, steps: tuple[float, ...] = ()) -> np.ndarray:
    t = (days - origin) / YEAR_DAYS
    columns = [np.ones(len(days)), t]
    if seasonal:
        columns.extend((np.sin(2 * np.pi * t), np.cos(2 * np.pi * t)))
    columns.extend((days >= step).astype(float) for step in steps)
    return np.column_stack(columns)


@dataclass(frozen=True)
class Fit:
    name: str
    origin: float
    coefficients: np.ndarray
    steps: tuple[float, ...] = ()

    def predict(self, days: np.ndarray) -> np.ndarray:
        days = np.atleast_1d(days).astype(float)
        if self.name == "persistence":
            return np.full(len(days), self.coefficients[0])
        return _features(days, self.origin, self.name == "trend_seasonal", self.steps) @ self.coefficients


def fit_model(name: str, days: np.ndarray, values: np.ndarray, steps: tuple[float, ...] = ()) -> Fit:
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
    used = tuple(float(s) for s in steps
                 if days[0] < s <= days[-1] and np.sum(days >= s) >= MIN_AFTER_STEP)
    design = _features(days, origin, name == "trend_seasonal", used)
    coefficients, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    if rank < design.shape[1]:
        raise ValueError(f"Insufficient independent observations for {name}")
    return Fit(name, origin, coefficients, used)
