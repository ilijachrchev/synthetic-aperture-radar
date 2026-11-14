"""Rain-threshold flood alerts: labels, rain windows, threshold fit, scores and alerts."""

from datetime import date

import numpy as np
import pytest

from pipeline.config import get_site
from pipeline.prediction.flood import model, rain


def days_from(start: date, n: int, step: int = 3) -> np.ndarray:
    return np.array([start.toordinal() + i * step for i in range(n)])


def test_label_flags_only_the_first_flooded_date_as_new():
    days = days_from(date(2025, 1, 1), 15)
    values = np.full(15, 100.0) + np.arange(15) % 2   # quiet baseline with tiny noise
    values[10] = values[11] = 900.0                     # flood seen on two passes
    out = model.label(days, values)
    assert [o["new_flood"] for o in out[10:13]] == [True, False, False]
    assert out[11]["persisting"] is True and out[12]["persisting"] is True
    assert all(o["flooded"] is None for o in out[:3])   # not enough history for a baseline


def test_small_or_noisy_rise_is_not_a_flood():
    days = days_from(date(2025, 1, 1), 12)
    values = np.array([100, 160, 90, 150, 110, 170, 95, 140, 105, 165, 100, 180.0])
    assert not any(o["flooded"] for o in model.label(days, values) if o["flooded"] is not None)


def test_rain_feature_uses_rain_between_passes_but_not_the_pass_day():
    rdays = np.arange(date(2025, 1, 1).toordinal(), date(2025, 1, 31).toordinal())
    mm = np.zeros(rdays.size)
    mm[rdays == date(2025, 1, 10).toordinal()] = 40
    mm[rdays == date(2025, 1, 11).toordinal()] = 30
    mm[rdays == date(2025, 1, 15).toordinal()] = 500   # falls on the pass day: excluded
    sums = model.rolling_sum(rdays, mm)
    feature = model.rain_feature(date(2025, 1, 15).toordinal(), date(2025, 1, 9).toordinal(), sums)
    assert feature == 70


def test_samples_skip_persisting_floods_and_long_gaps():
    labels = [{"day": 1, "flooded": False, "persisting": False, "new_flood": False, "excess_ha": 0},
              {"day": 4, "flooded": True, "persisting": False, "new_flood": True, "excess_ha": 500},
              {"day": 7, "flooded": True, "persisting": True, "new_flood": False, "excess_ha": 400},
              {"day": 30, "flooded": False, "persisting": True, "new_flood": False, "excess_ha": 0},
              {"day": 33, "flooded": False, "persisting": False, "new_flood": False, "excess_ha": 0}]
    sums = {d: float(d) for d in range(0, 40)}
    out = model.samples("x", labels, sums)
    assert [s["new_flood"] for s in out] == [1, 0]
    assert out[1]["previous_date"] == date.fromordinal(30).isoformat()


def test_threshold_maximises_peirce_skill_and_breaks_ties_upward():
    rain_mm = np.array([5, 10, 20, 40, 60, 80, 90.0])
    obs = np.array([0, 0, 0, 0, 1, 1, 1])
    assert model.fit_threshold(rain_mm, obs) == 60
    with pytest.raises(ValueError):
        model.fit_threshold(rain_mm, np.zeros(7))


def test_contingency_and_brier():
    c = model.contingency(np.array([True, True, False, False]), np.array([True, False, True, False]))
    assert (c["hits"], c["false_alarms"], c["misses"], c["correct_negatives"]) == (1, 1, 1, 1)
    assert c["peirce_skill"] == 0.0
    b = model.brier(np.array([1.0, 0.0]), np.array([1.0, 0.0]), 0.5)
    assert b["brier"] == 0 and b["brier_skill"] == 1.0


def test_logistic_rises_with_rain():
    rain_mm = np.array([0, 1, 2, 5, 10, 20, 50, 80, 100, 120.0])
    obs = np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])
    a, b = model.fit_logistic(rain_mm, obs)
    p = model.probability(a, b, np.array([0.0, 100.0]))
    assert b > 0 and p[0] < 0.2 < 0.8 < p[1]


def test_alert_levels_and_window_totals():
    assert [model.alert_level(s) for s in (0.0, 0.1, 0.49, 0.5)] == ["green", "amber", "amber", "red"]
    assert model.max_window_total(np.array([0, 10, 50, 30, 0.0])) == 90
    assert model.max_window_total(np.array([5, 6.0])) == 11


def test_rain_points_cover_the_site_box():
    pts = rain.points(get_site("pego_oliva"))
    lats, lons = {p[0] for p in pts}, {p[1] for p in pts}
    w, s, e, n = get_site("pego_oliva").bbox
    assert min(lats) <= s + 0.05 and max(lats) >= n - 0.05 and min(lons) <= w + 0.05 and max(lons) >= e - 0.05
