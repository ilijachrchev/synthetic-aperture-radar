"""Checks for the CV baseline and metrics on synthetic scenes. Written with SI assistance (Claude Code)."""

import numpy as np

from pipeline.cv.baseline import (
    CHANGE_CLASSES, PIXEL_HA, area_ha, burn_candidate, change_classes, flooded_vegetation,
    otsu_threshold_db, threshold_sensitivity, water_mask,
)
from pipeline.cv.data import boxcar_power, to_db
from pipeline.cv.metrics import confusion, scores

RNG = np.random.default_rng(42)


def _speckled(mean_power, shape, looks=8):
    """Gamma-distributed speckle with the given mean power and number of looks."""
    return RNG.gamma(looks, mean_power / looks, size=shape).astype("float32")


def test_to_db_and_invalid():
    p = np.array([1.0, 0.1, 0.0, np.nan, -1.0], dtype="float32")
    db = to_db(p)
    assert np.allclose(db[:2], [0.0, -10.0])
    assert np.all(np.isnan(db[2:]))


def test_boxcar_does_not_leak_invalid_pixels():
    power = np.full((20, 20), 0.1, dtype="float32")
    power[:, 10:] = 100.0          # a huge value right next to the edge
    valid = np.ones((20, 20), bool)
    valid[:, 10:] = False          # ... but it is invalid
    out = boxcar_power(power, valid, size=5)
    assert np.allclose(out[:, :10][np.isfinite(out[:, :10])], 0.1)
    assert np.all(np.isnan(out[:, 10:]))


def test_otsu_finds_water_in_speckled_scene():
    shape = (200, 200)
    truth = np.zeros(shape, bool)
    truth[50:120, 40:150] = True
    power = np.where(truth, _speckled(0.002, shape), _speckled(0.08, shape))
    valid = np.ones(shape, bool)
    hh_db = to_db(boxcar_power(power, valid, size=5))
    thr = otsu_threshold_db(hh_db, valid)
    assert -27 < thr < -11  # between water (about -27 dB) and land (about -11 dB)
    pred = water_mask(hh_db, valid, thr)
    s = scores(confusion(pred, truth, valid))
    assert s["iou"] > 0.9 and s["f1"] > 0.95
    sens = threshold_sensitivity(hh_db, valid, thr)
    assert sens[-1.0] <= sens[0.0] <= sens[1.0]
    assert abs(sens[0.0] - area_ha(truth)) / area_ha(truth) < 0.1


def test_change_classes_cover_every_case():
    wb = np.array([[0, 0, 1, 1, 0, 1]], bool)
    wa = np.array([[0, 1, 1, 0, 0, 1]], bool)
    vb = np.array([[1, 1, 1, 1, 1, 0]], bool)
    va = np.ones_like(vb)
    d_hh = np.array([[0.0, 0.0, 0.0, 0.0, 5.0, 0.0]])
    got = change_classes(wb, wa, vb, va, d_hh)
    assert [CHANGE_CLASSES[c] for c in got[0]] == [
        "stable_land", "water_gain", "stable_water", "water_loss", "other_change", "not_observed"]


def test_flooded_vegetation_and_burn_rules():
    hh_b, hh_a = np.array([-10.0, -10.0, -10.0]), np.array([-6.5, -6.5, -9.0])
    hv_b, hv_a = np.array([-17.0, -17.0, -17.0]), np.array([-16.5, -14.0, -19.0])
    valid = np.ones(3, bool)
    assert flooded_vegetation(hh_b, hh_a, hv_b, hv_a, valid).tolist() == [True, False, False]
    assert burn_candidate(hv_b, hv_a, valid).tolist() == [False, False, True]


def test_metrics_edge_cases():
    z = np.zeros((2, 2), bool)
    c = confusion(z, z, np.ones((2, 2), bool))
    assert c == {"tp": 0, "fp": 0, "fn": 0, "tn": 4}
    assert scores(c) == {"precision": None, "recall": None, "f1": None, "iou": None}
    assert PIXEL_HA == 0.04
