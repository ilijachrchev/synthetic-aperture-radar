"""Spatial water-likelihood model: label codes, timing rules, rain windows and the held-out window."""

from datetime import date

import numpy as np

from pipeline.prediction.spatial import features as F, labels, terrain


def _times(*days):
    return np.array(days, dtype="datetime64[s]")


def test_unknown_codes_never_become_dry():
    out = labels.to_water(np.array([0, 1, 3, 250, 251, 255, 2], dtype="uint8"))
    assert out.tolist() == [0, 1, 1, 255, 255, 255, 255]


def test_tile_names_cross_greenwich():
    assert terrain.tile_names((-0.25, 38.78, 0.06, 39.02)) == [
        "N38_00_W001_00", "N38_00_E000_00", "N39_00_W001_00", "N39_00_E000_00"]


def test_issue_pass_is_at_least_three_days_before_target():
    times = _times("2026-10-16T06:00", "2026-10-17T18:00", "2026-10-22T06:00", "2026-10-23T06:00")
    assert F.issue_index(times, 2) == 1      # 4.5 days before
    assert F.issue_index(times, 3) == 1      # the pass one day earlier is too close
    assert F.issue_index(times, 1) is None   # nothing 3 days before
    late = _times("2026-01-01T06:00", "2026-02-01T06:00")
    assert F.issue_index(late, 1) is None    # older than the longest lead


def test_previous_state_uses_only_passes_up_to_the_issue_pass():
    times = _times("2026-10-10T06:00", "2026-10-16T06:00", "2026-10-22T06:00")
    water = np.array([[1, 0, 255], [255, 1, 255], [1, 1, 1]], dtype="uint8")   # last row is the future
    state, age = F.prev_state(lambda k: water[k], times, 1, times[2], 3)
    assert state[:2].tolist() == [1.0, 1.0] and np.isnan(state[2])
    assert age[:2].tolist() == [12.0, 6.0] and np.isnan(age[2])


def test_rain_windows_exclude_the_target_day_and_keep_missing_missing():
    d0 = date(2026, 10, 17).toordinal()
    rain = {d0 + i: v for i, v in enumerate([6.0, 135.0, 115.0, 2.0, 0.0, 99.0])}   # 17..22 Oct
    rain.update({d0 - i: 1.0 for i in range(1, 31)})
    f = F.rain_features(rain, d0, d0 + 5)
    assert f["rain_between_mm"] == 258.0 and f["rain_between_max1d_mm"] == 135.0
    assert f["days_since_rain_peak"] == 4.0
    assert f["rain_prior_7d_mm"] == 7.0 and f["rain_prior_30d_mm"] == 30.0
    del rain[d0 + 2]
    assert np.isnan(F.rain_features(rain, d0, d0 + 5)["rain_between_mm"])


def test_assemble_matches_feature_order():
    static = np.zeros((4, len(F.STATIC)), "float32")
    rain = {k: 1.0 for k in F.RAIN if k != "lead_days"}
    X = F.assemble(static, np.full(4, 0.5), date(2026, 10, 22).toordinal(), 5.0, rain,
                   np.array([0, 1, np.nan, 0], "float32"), np.array([5, 5, np.nan, 5], "float32"))
    assert X.shape == (4, len(F.FEATURES))
    assert X[:, F.FEATURES.index("prev_water_missing")].tolist() == [0, 0, 1, 0]
    assert X[0, F.FEATURES.index("lead_days")] == 5.0 and X[0, F.FEATURES.index("s1_wet_freq")] == 0.5


def test_table_leaves_the_held_out_window_out():
    days = [f"2026-09-{d:02d}" for d in range(1, 29, 3)] + ["2026-10-22", "2026-10-28"]
    times = np.array([d + "T06:00" for d in days], dtype="datetime64[s]")
    rng = np.random.default_rng(0)
    water = rng.integers(0, 2, size=(len(days), 50)).astype("uint8")
    rain = {date(2026, 8, 1).toordinal() + i: 0.0 for i in range(120)}
    tab = F.build_table(water, times, days, np.zeros((50, len(F.STATIC)), "float32"), np.ones(50, "float32"),
                        rain, rng, dry_keep=1.0)
    assert tab["y"].size > 0
    assert all(not F.in_holdout(days[t]) for t in set(tab["t"].tolist()))
    assert F.in_holdout("2026-10-15") and F.in_holdout("2026-11-15") and not F.in_holdout("2026-10-14")


def test_past_wet_share_leaves_the_sample_out_and_needs_enough_passes():
    f = F.wet_frequency(np.array([10, 10, 3]), np.array([40, 40, 10]), minus_wet=np.array([1, 0, 0]), minus_obs=1)
    assert abs(f[0] - 9 / 39) < 1e-6 and abs(f[1] - 10 / 39) < 1e-6 and np.isnan(f[2])
