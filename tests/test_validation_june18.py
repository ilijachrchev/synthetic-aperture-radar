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
    """spec: stratum -> list of (map_value, label)."""
    return [{"stratum": s, "nisar": m, "label": lab} for s, rows in spec.items() for m, lab in rows]


def test_map_accuracy_weighted():
    pts = _pts({"A": [(1, "wet")] * 10, "B": [(1, "wet")] * 8 + [(1, "dry")] * 2,
                "C": [(0, "dry")] * 10, "D": [(0, "wet")] * 1 + [(0, "dry")] * 9})
    w = {"A": 0.1, "B": 0.4, "C": 0.05, "D": 0.45}
    m = v.map_accuracy(pts, w, "nisar")
    wet = 0.1 + 0.32 + 0 + 0.045
    assert m["user"] == pytest.approx(0.42 / 0.5)
    assert m["producer"] == pytest.approx(0.42 / wet)
    assert m["wet_share"] == pytest.approx(wet)


def test_map_accuracy_leaves_out_unclear_and_bounds():
    pts = _pts({"B": [(1, "wet"), (1, "unclear"), (1, "unclear"), (1, "dry")]})
    assert v.map_accuracy(pts, {"B": 1.0}, "nisar")["user"] == pytest.approx(0.5)
    assert v.map_accuracy(pts, {"B": 1.0}, "nisar", unclear_as="dry")["user"] == pytest.approx(0.25)
    assert v.map_accuracy(pts, {"B": 1.0}, "nisar", unclear_as="wet")["user"] == pytest.approx(0.75)


def test_map_accuracy_any_map_on_same_points():
    # a second map that is not the strata: water only on the first two B points
    pts = _pts({"B": [(1, "wet"), (1, "wet"), (1, "dry"), (1, "dry")]})
    for q, u in zip(pts, (1, 0, 1, 0)):
        q["unet"] = u
    m = v.map_accuracy(pts, {"B": 1.0}, "unet")
    assert m["user"] == pytest.approx(0.5) and m["producer"] == pytest.approx(0.5)


def test_bootstrap_brackets_estimate():
    pts = _pts({"A": [(1, "wet")] * 30, "B": [(1, "wet")] * 21 + [(1, "dry")] * 9,
                "C": [(0, "dry")] * 30, "D": [(0, "dry")] * 30})
    ci = v.bootstrap(pts, {s: 0.25 for s in "ABCD"}, keys=("nisar",), reps=300, seed=3)
    assert ci["b_user"][0] < 0.7 < ci["b_user"][1]


def test_closest_after_prefers_first_clear_look():
    wet, ok = v.closest_after([1, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0])
    assert wet.tolist() == [True, True, False] and ok.tolist() == [True, True, False]


def test_strict_is_open_water_only():
    # dense wet crop: LSWI rule fires, MNDWI does not
    args = (0.03, 0.05, 0.05, 0.20, 0.12)
    assert bool(v.wet_on_date(*args)) and not bool(v.wet_on_date(*args, strict=True))


def test_decode_distance_sign():
    d = v.decode_distance(np.array([100, 128, 160], dtype="uint8"))
    assert d[0] < 0 and d[1] == 0 and d[2] > 0


def test_verdict_rule():
    assert v.verdict(0.8, [0.65, 0.9]).startswith("NISAR wins")
    assert not v.verdict(0.8, [0.55, 0.9]).startswith("NISAR wins")
    assert not v.verdict(0.6, [0.62, 0.7]).startswith("NISAR wins")
