"""Helpers of the NISAR check: pairing NISAR dates with Sentinel-1 passes, correlation."""

from datetime import date

import numpy as np

from pipeline.prediction import nisar_check as nc


def rows():
    return [{"date": "2026-10-16", "usable": "True", "v": "100"},
            {"date": "2026-10-16", "usable": "True", "v": "200"},     # two passes on one day are averaged
            {"date": "2026-10-17", "usable": "True", "v": "999"},
            {"date": "2026-10-28", "usable": "False", "v": "500"},    # unusable pass is skipped
            {"date": "2026-10-29", "usable": "True", "v": "300"}]


def test_nearest_pass_prefers_the_same_day_and_averages_it():
    p = nc.nearest_pass(date(2026, 10, 16), rows(), "v")
    assert (p["date"], p["day_gap"], p["value"]) == ("2026-10-16", 0, 150.0)


def test_nearest_pass_allows_one_day_after_and_skips_unusable():
    p = nc.nearest_pass(date(2026, 10, 28), rows(), "v")
    assert (p["date"], p["day_gap"], p["value"]) == ("2026-10-29", 1, 300.0)
    assert nc.nearest_pass(date(2026, 10, 20), rows(), "v") is None


def test_pearson_needs_three_points_and_spread():
    assert nc.pearson([1, 2], [1, 2]) is None
    assert nc.pearson([1, 1, 1], [1, 2, 3]) is None
    assert nc.pearson([1, 2, 3, 4], [2, 4, 6, 8.5]) > 0.99


def test_water_ha_counts_dark_valid_pixels_inside_the_region():
    hh = np.array([[-20.0, -5.0], [-20.0, -20.0]])
    valid = np.array([[True, True], [True, False]])
    region = np.array([[True, True], [False, True]])
    assert nc.water_ha(hh, valid, region, threshold_db=-10.0) == 0.04
