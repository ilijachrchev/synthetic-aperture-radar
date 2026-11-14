"""Scientific failure modes: units, date leakage, gaps, and honest uncertainty."""

import csv
from datetime import date, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from pipeline.prediction.__main__ import parser, run
from pipeline.prediction.data import Series, fetch_ngl, load_egms, load_ngl
from pipeline.prediction.evaluation import interval_radius, rolling_backtest, select_models, summarize
from pipeline.prediction.models import fit_model


def example_series(n=1800):
    dates = tuple(date(2020, 1, 1) + timedelta(days=i) for i in range(n))
    t = np.arange(n)
    return Series("test", dates, -0.08 * t + 4 * np.sin(2 * np.pi * t / 365.25), {})


class InputTests(unittest.TestCase):
    def test_ngl_integer_fraction_units_and_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LOR1.tenv3"
            path.write_text(
                "site __MJD u0(m) ____up(m) sig_u(m) _latitude(deg) _longitude(deg)\n"
                "LOR1 58849 365 0.99 0.003 37.654 -1.687\n"
                "LOR1 58850 366 -0.005 0.003 37.654 -1.687\n"
                "LOR1 58851 366 0.03 0.100 37.654 -1.687\n")
            series = load_ngl(path, "LOR1").between(date(2020, 1, 1), date(2020, 1, 3))
            np.testing.assert_allclose(series.values, [0, 5], atol=1e-8)
            self.assertEqual(series.dates[-1], date(2020, 1, 2))
            self.assertEqual(series.source["quality_filter"]["rejected_rows_in_source"], 1)

    def test_egms_date_columns_are_mm_and_zero_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "up.csv"
            path.write_text("pid;easting;northing;mean_velocity;20240101;20240107;20240113;20240119\n"
                            "p1;1;2;-100;0;-2.5;;nan\n")
            series = load_egms(path, "p1")
            np.testing.assert_allclose(series.values, [0, -2.5])
            self.assertEqual(len(series.dates), 2)
            self.assertEqual(series.source["grid_crs"], "EPSG:3035")

    def test_egms_pid_is_exact_and_missing_sentinel_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "up.csv"
            path.write_text("pid,20240101,20240107,20240113\np1,0,-9999,-2\np2,50,51,52\n")
            series = load_egms(path, "p1", nodata=-9999)
            np.testing.assert_allclose(series.values, [0, -2])
            with self.assertRaisesRegex(ValueError, "not found"):
                load_egms(path, "p")

    def test_duplicate_dates_fail_instead_of_silently_averaging(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            Series("test", (date(2020, 1, 1), date(2020, 1, 1)), np.array([0, 1]), {})

    def test_velocity_only_egms_input_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "velocity.csv"
            path.write_text("pid,mean_velocity\np1,-10\n")
            with self.assertRaisesRegex(ValueError, "velocity-only"):
                load_egms(path, "p1")

    def test_fetch_rejects_html_instead_of_caching_it(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("pipeline.prediction.data.urlopen", return_value=io.BytesIO(b"<html>error</html>")):
                with self.assertRaisesRegex(ValueError, "not an NGL"):
                    fetch_ngl("LOR1", Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_fetch_rejects_empty_response(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("pipeline.prediction.data.urlopen", return_value=io.BytesIO(b"")):
                with self.assertRaisesRegex(ValueError, "not an NGL"):
                    fetch_ngl("LOR1", Path(directory))


class ForecastTests(unittest.TestCase):
    def test_persistence_does_not_invent_a_trend(self):
        fitted = fit_model("persistence", np.array([1., 2., 3.]), np.array([5., 6., 4.]))
        np.testing.assert_array_equal(fitted.predict(np.array([10., 20.])), [4, 4])

    def test_linear_extrapolation_uses_actual_elapsed_days(self):
        days = np.array([10., 13., 20., 40.])
        values = -0.1 * days + 2
        fitted = fit_model("linear", days, values)
        np.testing.assert_allclose(fitted.predict(np.array([52., 64.])), [-3.2, -4.4], atol=1e-10)

    def test_seasonal_model_recovers_both_annual_phase_terms(self):
        days = np.arange(1000, dtype=float)
        values = 10 - 0.03 * days + 2 * np.sin(2 * np.pi * days / 365.25) + 3 * np.cos(2 * np.pi * days / 365.25)
        targets = np.array([1012., 1024., 1036.])
        expected = 10 - 0.03 * targets + 2 * np.sin(2 * np.pi * targets / 365.25) + 3 * np.cos(2 * np.pi * targets / 365.25)
        np.testing.assert_allclose(fit_model("trend_seasonal", days, values).predict(targets), expected, atol=1e-9)

    def test_future_values_cannot_change_earlier_backtests(self):
        series = example_series()
        start, end = date(2023, 1, 1), date(2023, 3, 31)
        before = rolling_backtest(series, start, end, (12, 24))
        changed = series.values.copy()
        changed[series.days > end.toordinal()] = 1e9
        after = rolling_backtest(Series(series.point_id, series.dates, changed, {}), start, end, (12, 24))
        self.assertTrue(before)
        self.assertEqual(before, after)
        for row in before:
            self.assertLessEqual(row["training_end"], row["origin"])
            self.assertGreater(row["target_date"], row["origin"])
            self.assertLessEqual(row["target_date"], end.isoformat())

    def test_missing_target_is_not_interpolated(self):
        series = example_series()
        missing = date(2023, 2, 10)
        keep = [i for i, d in enumerate(series.dates) if d != missing]
        series = Series("test", tuple(series.dates[i] for i in keep), series.values[keep], {})
        rows = rolling_backtest(series, date(2023, 1, 1), date(2023, 3, 1), (12,), stride_days=1)
        self.assertFalse(any(row["origin"] == "2023-01-29" for row in rows))
        self.assertFalse(any(row["target_date"] == missing.isoformat() for row in rows))

    def test_target_tolerance_records_and_predicts_at_the_actual_date(self):
        series = example_series()
        keep = [i for i, d in enumerate(series.dates) if d != date(2023, 2, 10)]
        series = Series("test", tuple(series.dates[i] for i in keep), series.values[keep], {})
        rows = rolling_backtest(series, date(2023, 1, 1), date(2023, 3, 1), (12,),
                                stride_days=1, target_tolerance_days=1)
        result = next(r for r in rows if r["origin"] == "2023-01-29" and r["model"] == "trend_seasonal")
        self.assertEqual(result["target_date"], "2023-02-09")
        self.assertEqual(result["actual_horizon_days"], 11)
        self.assertAlmostEqual(result["error_mm"], 0, places=8)

    def test_ranges_use_finite_sample_rank_and_refuse_small_95_sample(self):
        self.assertEqual(interval_radius(list(range(1, 21)), 0.8), 17)
        self.assertEqual(interval_radius(list(range(1, 21)), 0.95), 20)
        self.assertIsNone(interval_radius([1] * 18, 0.95))
        self.assertIsNone(interval_radius([], 0.8))

    def test_zero_baseline_error_has_no_infinite_skill(self):
        rows = [{"model": name, "horizon_days": 12, "origin": "2024-01-01",
                 "target_date": "2024-01-13", "error_mm": 0.0} for name in ("persistence", "linear", "trend_seasonal")]
        scores = summarize(rows)
        self.assertIsNone(scores["12"]["linear"]["skill_vs_persistence"])
        json.dumps(scores, allow_nan=False)

    def test_selection_uses_development_scores(self):
        scores = {"12": {"persistence": {"n": 10, "mae_mm": 4},
                          "linear": {"n": 10, "mae_mm": 1},
                          "trend_seasonal": {"n": 10, "mae_mm": 2}}}
        self.assertEqual(select_models(scores), {12: "linear"})


class PipelineTests(unittest.TestCase):
    def test_egms_pipeline_exports_and_accounts_for_stale_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "egms_up.csv"
            end = date(2026, 10, 17)
            count = (end - date(2020, 1, 1)).days + 1
            days = [date(2020, 1, 1) + timedelta(days=i) for i in range(count)]
            values = [-0.05 * i + 3 * np.sin(2 * np.pi * i / 365.25) for i in range(count)]
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["pid", *[day.strftime("%Y%m%d") for day in days]])
                writer.writerow(["p1", *values])
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"layers": [{"id": "existing-cv"}]}))
            args = parser().parse_args(["run", "--format", "egms", "--input", str(path),
                                        "--point-id", "p1", "--output", str(root / "out"),
                                        "--manifest", str(manifest), "--as-of", "2026-11-14", "--no-plot"])
            forecast = run(args)
            self.assertEqual(forecast["observation_age_days"], 28)
            self.assertEqual([p["lead_from_last_observation_days"] for p in forecast["predictions"]], [40, 52, 64])
            self.assertEqual(forecast["predictions"][0]["target_date"], "2026-11-26")
            self.assertEqual(forecast["nisar_validation"]["status"], "not_performed")
            scores = json.loads((root / "out/metrics.json").read_text())
            self.assertIn("64", scores["test"])
            self.assertTrue(all(p["intervals"]["95"]["calibration_n"] >= 19 for p in forecast["predictions"]))
            existing = json.loads(manifest.read_text())
            self.assertEqual(existing["layers"], [{"id": "existing-cv"}])
            self.assertEqual(len(existing["forecasts"]), 1)
            run(args)
            self.assertEqual(len(json.loads(manifest.read_text())["forecasts"]), 1)

            existing = json.loads((root / "out/forecast.json").read_text())
            existing["point_id"] = "another_point"
            (root / "out/forecast.json").write_text(json.dumps(existing))
            with self.assertRaisesRegex(ValueError, "separate --output"):
                run(args)
            self.assertEqual(json.loads((root / "out/forecast.json").read_text())["point_id"], "another_point")

    def test_invalid_date_splits_fail_before_writing(self):
        args = parser().parse_args(["run", "--calibration-start", "2025-02-01"])
        with self.assertRaisesRegex(ValueError, "selection-start"):
            run(args)


if __name__ == "__main__":
    unittest.main()
