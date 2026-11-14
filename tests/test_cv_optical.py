"""Checks for the optical answer key (clear-first mosaic of DSWx-HLS within the window). Written with SI assistance (Claude Code)."""

import numpy as np

from pipeline.cv.optical import CLOUD, FILL, NOT_WATER, OPEN, PARTIAL, SNOW_ICE, combine, needed_dates, window_order


def _a(values):
    return np.array([values], dtype="uint8")


def test_same_day_clear_wins_over_next_day_clear():
    wtr, days = combine([(0, _a([OPEN, NOT_WATER])), (1, _a([NOT_WATER, OPEN]))])
    assert wtr.tolist() == [[OPEN, NOT_WATER]]
    assert days.tolist() == [[0, 0]]


def test_next_day_clear_fills_a_same_day_cloud():
    wtr, days = combine([(0, _a([CLOUD, OPEN])), (1, _a([PARTIAL, NOT_WATER]))])
    assert wtr.tolist() == [[PARTIAL, OPEN]]
    assert days.tolist() == [[1, 0]]


def test_cloud_stays_cloud_when_nothing_is_clear_and_fill_stays_fill():
    wtr, days = combine([(0, _a([CLOUD, FILL, FILL])), (1, _a([SNOW_ICE, FILL, CLOUD]))])
    assert wtr.tolist() == [[CLOUD, FILL, CLOUD]]
    assert days.tolist() == [[0, FILL, 1]]


def test_a_later_clear_value_beats_an_earlier_cloud_of_any_day():
    wtr, days = combine([(0, _a([CLOUD])), (1, _a([CLOUD])), (1, _a([OPEN]))])
    assert wtr.tolist() == [[OPEN]] and days.tolist() == [[1]]


def test_window_order_is_same_day_then_day_before_then_day_after_by_name():
    by_date = {"2026-09-06": ["b.tif", "a.tif"], "2026-09-07": ["z.tif", "c.tif"], "2026-09-08": ["d.tif"],
               "2026-09-09": ["far.tif"]}
    assert window_order("2026-09-07", by_date) == [
        (0, "2026-09-07", "c.tif"), (0, "2026-09-07", "z.tif"),
        (1, "2026-09-06", "a.tif"), (1, "2026-09-06", "b.tif"),
        (1, "2026-09-08", "d.tif")]


def test_needed_dates_cover_the_window():
    assert needed_dates({"2026-09-07"}) == {"2026-09-06", "2026-09-07", "2026-09-08"}
