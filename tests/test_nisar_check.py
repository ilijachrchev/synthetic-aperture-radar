"""Helpers of the NISAR check: pairing NISAR dates with Sentinel-1 passes, correlation."""

from datetime import datetime, timezone

import numpy as np

from pipeline.prediction import nisar_check as nc


def rows():
    return [{"date": "2026-10-16", "begin_utc": "2026-10-16T06:02:00.000Z", "pass_id": "a", "usable": "True", "v": "100"},
            {"date": "2026-10-16", "begin_utc": "2026-10-16T18:02:00.000Z", "pass_id": "b", "usable": "True", "v": "200"},
            {"date": "2026-10-28", "begin_utc": "2026-10-28T18:10:00.000Z", "pass_id": "c", "usable": "False", "v": "500"},
            {"date": "2026-10-29", "begin_utc": "2026-10-29T18:00:00.000Z", "pass_id": "d", "usable": "True", "v": "300"}]


NISAR = datetime(2026, 10, 16, 18, 53, tzinfo=timezone.utc)


def test_nearest_pass_takes_only_the_pass_at_the_same_time_of_day():
    p = nc.nearest_pass(NISAR, rows(), "v")
    assert (p["pass_id"], p["value"], p["gap_h"]) == ("b", 200.0, 0.85)   # not the 06 UTC pass, not averaged


def test_nearest_pass_skips_unusable_and_passes_more_than_2_h_away():
    assert nc.nearest_pass(NISAR.replace(day=28), rows(), "v") is None    # same-time pass unusable, next day too far
    assert nc.nearest_pass(NISAR.replace(hour=12), rows(), "v") is None


def test_main_does_not_overwrite_results_without_stacks(tmp_path, monkeypatch):
    out = tmp_path / "nisar_check.json"
    out.write_text("committed")
    monkeypatch.setattr(nc, "OUT", out)
    monkeypatch.setattr(nc, "STACK_DIR", nc.REPO_ROOT / "no_such_dir")
    assert nc.main([]) == 1
    assert out.read_text() == "committed"


def test_pearson_needs_three_points_and_spread():
    assert nc.pearson([1, 2], [1, 2]) is None
    assert nc.pearson([1, 1, 1], [1, 2, 3]) is None
    assert nc.pearson([1, 2, 3, 4], [2, 4, 6, 8.5]) > 0.99


def test_water_ha_counts_dark_valid_pixels_inside_the_region():
    hh = np.array([[-20.0, -5.0], [-20.0, -20.0]])
    valid = np.array([[True, True], [True, False]])
    region = np.array([[True, True], [False, True]])
    assert nc.water_ha(hh, valid, region, threshold_db=-10.0) == 0.04
