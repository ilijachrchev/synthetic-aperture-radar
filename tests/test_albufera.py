"""Albufera flooded-area forecast: mask rule, pass merging, folds, leakage and ranges."""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from pipeline.prediction.albufera import area, forecast as fc, history, mask


def test_rice_mask_keeps_deep_or_flooded_corine_rice_only():
    #          deep   edge+seasonal  edge+never-water  town  lagoon  not-CORINE  sea
    rice = np.array([[1, 1, 1, 1, 1, 0, 1]], bool)
    deep = np.array([[1, 0, 0, 1, 1, 0, 1]], bool)
    wc = np.array([[40, 40, 40, 50, 80, 40, 80]])
    jrc = np.array([[0, 40, 0, 40, 95, 40, 95]])
    sea = np.array([[0, 0, 0, 0, 0, 0, 1]])
    assert mask.rice_mask(rice, deep, wc, jrc, sea).tolist() == [[True, True, False, False, False, False, False]]
    with pytest.raises(ValueError):
        mask.rice_mask(rice, deep, wc, jrc[:, :2], sea)


def test_jrc_no_data_is_not_permanent_water():
    one = np.ones((1, 1), bool)
    assert mask.rice_mask(one, one, np.array([[40]]), np.array([[255]]), np.array([[0]])).all()


def test_summarize_pass_counts_flooded_classes_and_unobserved():
    classes = np.array([[0, 1, 3, 251, 255, 1]], dtype="uint8")
    m = np.array([[True, True, True, True, False, False]])
    s = area.summarize_pass(classes, m)
    assert s["open_water_ha"] == 0.04 and s["inundated_vegetation_ha"] == 0.04
    assert s["observed_fraction"] == 0.75 and s["flooded_share_of_observed"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["usable"] is False


def _tif(path: Path, data: np.ndarray, crs="EPSG:32630", origin=(0, 60)):
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1,
                       dtype="uint8", crs=crs, transform=from_origin(*origin, 20, 20), nodata=255) as dst:
        dst.write(data, 1)


def test_merge_prefers_observed_over_masked_and_fill(tmp_path):
    grid = {"crs": "EPSG:32630", "transform": from_origin(0, 60, 20, 20), "width": 3, "height": 3}
    _tif(tmp_path / "a.tif", np.array([[1, 255, 251]] * 3, dtype="uint8"))
    _tif(tmp_path / "b.tif", np.array([[0, 3, 0]] * 3, dtype="uint8"))
    merged = area.merge_on_grid([tmp_path / "a.tif", tmp_path / "b.tif"], grid)
    assert merged[0].tolist() == [1, 3, 0]


def test_history_groups_tiles_and_keeps_newest_reprocessing():
    def g(tile, acq, prod, plat="S1A"):
        return {"granule_ur": f"OPERA_L3_DSWx-S1_{tile}_{acq}Z_{prod}Z_{plat}_30_v1.0",
                "begin_utc": f"{acq[:4]}-{acq[4:6]}-{acq[6:8]}T{acq[9:11]}:{acq[11:13]}:{acq[13:15]}Z",
                "wtr_url": f"https://x/{tile}_{prod}_B01_WTR.tif"}
    granules = [g("T30SYJ", "20250101T060000", "20250102T000000"),
                g("T30SYJ", "20250101T060000", "20250301T000000"),   # reprocessed: wins
                g("T31SBD", "20250101T060010", "20250102T000000"),
                g("T30SYJ", "20250107T180000", "20250108T000000", "S1C")]
    index = history.build_index(sorted(granules, key=lambda x: x["begin_utc"]))
    assert [e["tiles"] for e in index] == [["T30SYJ", "T31SBD"], ["T30SYJ"]]
    assert "20250301" in index[0]["selected"][0]["wtr_url"]
    assert index[0]["pass_id"] == "20250101T060000_S1A"


def test_daily_series_skips_unusable_and_averages_same_day():
    rows = [{"date": "2025-01-01", "usable": "True", "flooded_share_of_observed": "0.5"},
            {"date": "2025-01-01", "usable": "True", "flooded_share_of_observed": "0.7"},
            {"date": "2025-01-02", "usable": "False", "flooded_share_of_observed": "0.9"}]
    days, values = fc.daily_series(rows, 1000.0)
    assert days.tolist() == [date(2025, 1, 1).toordinal()] and values.tolist() == [600.0]


def test_season_boundary_is_august():
    assert fc.season_of(date(2025, 7, 31)) == 2024 and fc.season_of(date(2025, 8, 1)) == 2025


def seasonal_series(start=date(2024, 8, 21), end=date(2026, 11, 10), step=3, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    days = np.arange(start.toordinal(), end.toordinal() + 1, step, dtype=float)
    doy = np.array([fc.day_of_year(d) for d in days])
    # flooded in winter (peak around 1 Jan), dry in summer
    values = 5000 + 4000 * np.cos(2 * np.pi * (doy - 1) / 365.25) + noise * rng.standard_normal(days.size)
    return days, np.clip(values, 0, 10000)


def test_folds_hold_out_each_past_season_and_test_only_on_current():
    days, _ = seasonal_series()
    f = fc.folds(days)
    assert f == [{"role": "selection", "test_season": 2024, "ref_seasons": [2025]},
                 {"role": "selection", "test_season": 2025, "ref_seasons": [2024]},
                 {"role": "test", "test_season": 2026, "ref_seasons": [2024, 2025]}]
    with pytest.raises(ValueError):
        fc.folds(days[days < date(2025, 8, 1).toordinal()])


def test_backtest_never_uses_the_test_season_as_climatology():
    days, values = seasonal_series()
    values = values.copy()
    values[days >= date(2026, 8, 1).toordinal()] += 3000   # current season is unusual
    rows = fc.backtest(days, values, [12], fc.Settings())
    clim = [r for r in rows if r["role"] == "test" and r["model"] == "climatology"]
    assert clim and all(r["error_ha"] > 2500 for r in clim)   # climatology did not see the shift


def test_seasonal_cycle_beats_persistence_at_long_lead():
    days, values = seasonal_series(noise=150)
    out = fc.forecast(days, values, date(2026, 11, 14), [12, 24, 36], 10000.0, fc.Settings())
    sel = out["scores"]["selection"]["36"]
    assert sel["climatology"]["mae_ha"] < sel["persistence"]["mae_ha"]
    assert out["data_cutoff"] == date.fromordinal(int(days[-1])).isoformat()
    for p in out["predictions"]:
        assert p["model"] == out["selected_models_by_lead"][str(p["effective_lead_days"])]
        for label in ("80", "95"):
            iv = p["intervals"][label]
            if iv["status"] == "available":
                assert 0 <= iv["lower_ha"] <= p["value_ha"] <= iv["upper_ha"] <= 10000


def test_forecast_ignores_observations_after_as_of():
    days, values = seasonal_series()
    a = fc.forecast(days, values, date(2026, 10, 1), [12], 10000.0, fc.Settings())
    later = values.copy()
    later[days > date(2026, 10, 1).toordinal()] = 0
    b = fc.forecast(days, later, date(2026, 10, 1), [12], 10000.0, fc.Settings())
    assert a["predictions"] == b["predictions"]
