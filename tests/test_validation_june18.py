"""Checks of the 18 June sample-based validation (pipeline.validation.june18)."""

import numpy as np
import pytest

from pipeline.validation import june18 as v


def test_strata_map_letters():
    rice = np.array([[1, 1, 1, 1, 0]], bool)
    control = np.array([[0, 0, 0, 0, 1]], bool)
    ok = np.ones((1, 5), bool)
    nisar = np.array([[1, 1, 0, 0, 1]], bool)
    s1 = np.array([[1, 0, 1, 0, 0]], bool)
    out = v.strata_map(rice, control, ok, nisar, s1, ok)
    assert out.tolist() == [["A", "B", "C", "D", "E"]]


def test_strata_map_skips_invalid():
    one = np.ones((1, 2), bool)
    out = v.strata_map(one, ~one, np.array([[1, 0]], bool), one, one, one)
    assert out.tolist() == [["A", ""]]


def test_sample_points_spacing_and_reproducible():
    strata = np.full((100, 100), "B", dtype="<U1")
    a = v.sample_points(strata, n=20, step=10, seed=1)
    b = v.sample_points(strata, n=20, step=10, seed=1)
    assert a == b and len(a) == 20
    rows = {r for _, r, _ in a}
    assert all((r - min(rows)) % 10 == 0 for r in rows)


def test_sample_points_takes_all_when_few():
    strata = np.full((30, 30), "", dtype="<U1")
    strata[5, 5] = "C"
    pts = v.sample_points(strata, n=50, step=1, seed=0)
    assert pts == [("C", 5, 5)]


def test_wet_on_date():
    # open water: green above SWIR; dense crop: NIR high, SWIR moderate
    water = v.wet_on_date(0.05, 0.06, 0.04, 0.03, 0.01)
    crop = v.wet_on_date(0.03, 0.06, 0.03, 0.45, 0.20)
    assert bool(water) and not bool(crop)


def test_bracket_label():
    out = v.bracket_label([1, 0, 1, 1], [1, 0, 0, 1], [1, 1, 1, 0], [1, 1, 1, 1])
    assert out.tolist() == ["wet", "dry", "unclear", "unclear"]


def _pts(spec):
    return [{"stratum": s, "label": lab} for s, labs in spec.items() for lab in labs]


def test_estimates_weighted():
    pts = _pts({"A": ["wet"] * 10, "B": ["wet"] * 8 + ["dry"] * 2, "C": ["dry"] * 10, "D": ["wet"] * 1 + ["dry"] * 9})
    w = {"A": 0.1, "B": 0.4, "C": 0.05, "D": 0.45}
    e = v.estimates(pts, w)
    assert e["b_user"] == pytest.approx(0.8)
    assert e["nisar_user"] == pytest.approx((0.1 * 1 + 0.4 * 0.8) / 0.5)
    wet = 0.1 + 0.32 + 0 + 0.045
    assert e["wet_share"] == pytest.approx(wet)
    assert e["nisar_producer"] == pytest.approx(0.42 / wet)
    assert e["s1_producer"] == pytest.approx(0.1 / wet)


def test_estimates_ignore_unclear():
    pts = _pts({"B": ["wet", "unclear", "unclear", "dry"]})
    assert v.estimates(pts, {"B": 1.0})["b_user"] == pytest.approx(0.5)


def test_bootstrap_brackets_estimate():
    pts = _pts({"A": ["wet"] * 30, "B": ["wet"] * 21 + ["dry"] * 9, "C": ["dry"] * 30, "D": ["dry"] * 30})
    w = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    ci = v.bootstrap(pts, w, reps=300, seed=3)
    assert ci["b_user"][0] < 0.7 < ci["b_user"][1]


def test_verdict_rule():
    assert v.verdict(0.8, [0.65, 0.9]).startswith("NISAR wins")
    assert not v.verdict(0.8, [0.55, 0.9]).startswith("NISAR wins")
    assert not v.verdict(0.6, [0.62, 0.7]).startswith("NISAR wins")
