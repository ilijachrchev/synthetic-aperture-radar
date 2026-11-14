"""Run with python -m pipeline.prediction; all scientific computation is offline."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import platform
import sys
from urllib.error import URLError

import numpy as np

from . import __version__
from .data import Series, fetch_ngl, load_egms, load_ngl, utc_now
from .evaluation import interval_radius, rolling_backtest, select_models, summarize, training_window
from .models import MODEL_NAMES, fit_model


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Lorca displacement baselines, backtests, and forecast exports")
    commands = root.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Download one small public NGL GNSS series")
    fetch.add_argument("--station", default="LOR1")
    fetch.add_argument("--directory", type=Path, default=Path("data/raw/ngl"))
    run = commands.add_parser("run", help="Evaluate models and export a forecast from a local input")
    run.add_argument("--format", choices=("ngl", "egms"), default="ngl")
    run.add_argument("--input", type=Path, help="Default: data/raw/ngl/LOR1.tenv3")
    run.add_argument("--point-id", default="LOR1", help="NGL station or exact EGMS pid")
    run.add_argument("--site", default="lorca")
    run.add_argument("--output", type=Path, default=Path("data/prediction/lorca"))
    run.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    run.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date(),
                     help="Forecast origin; observations after this UTC date are excluded")
    run.add_argument("--data-start", type=date.fromisoformat, default=date(2020, 1, 1))
    run.add_argument("--selection-start", type=date.fromisoformat, default=date(2023, 1, 1))
    run.add_argument("--calibration-start", type=date.fromisoformat, default=date(2024, 1, 1))
    run.add_argument("--test-start", type=date.fromisoformat, default=date(2025, 1, 1))
    run.add_argument("--test-end", type=date.fromisoformat, default=date(2025, 12, 31))
    run.add_argument("--horizons", type=int, nargs="+", default=[12, 24, 36])
    run.add_argument("--window-days", type=int, default=1096)
    run.add_argument("--stride-days", type=int, default=7)
    run.add_argument("--min-observations", type=int, default=100)
    run.add_argument("--min-span-days", type=int, default=730)
    run.add_argument("--target-tolerance-days", type=int, default=0,
                     help="Allowed nearest-date mismatch in backtests; never interpolate")
    run.add_argument("--max-sigma-mm", type=float, default=20.0, help="NGL provider uncertainty filter")
    run.add_argument("--nodata-value", type=float, help="Optional numeric EGMS missing-data sentinel")
    run.add_argument("--no-plot", action="store_true")
    return root


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _intervals(calibration: list[dict], name: str, lead: int, value: float) -> dict:
    errors = [r["error_mm"] for r in calibration if r["model"] == name and r["horizon_days"] == lead]
    result = {}
    for label, coverage in (("80", 0.8), ("95", 0.95)):
        radius = interval_radius(errors, coverage)
        result[label] = {"nominal_coverage": coverage, "calibration_n": len(errors),
                         "lower_mm": None if radius is None else value - radius,
                         "upper_mm": None if radius is None else value + radius,
                         "status": "insufficient_calibration" if radius is None else "estimated"}
    return result


def _update_manifest(path: Path, forecast: dict, output: Path, has_plot: bool) -> None:
    manifest = json.loads(path.read_text()) if path.exists() else {"schema_version": 1, "layers": []}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("forecasts", []), list):
        raise ValueError("Manifest must be an object with an optional forecasts array")
    entry = {"id": forecast["id"], "model": "prediction", "site": forecast["site"],
             "point_id": forecast["point_id"], "file": (output / "forecast.json").as_posix(),
             "metrics": (output / "metrics.json").as_posix(),
             "observations": (output / "observations.csv").as_posix(),
             "chart": (output / "chart.png").as_posix() if has_plot else None,
             "source_type": forecast["source"]["type"], "units": "mm",
             "issued_at_utc": forecast["issued_at_utc"], "data_cutoff": forecast["data_cutoff"]}
    entries = [item for item in manifest.get("forecasts", []) if item.get("id") != entry["id"]]
    manifest["forecasts"] = entries + [entry]
    write_json(path, manifest)


def run(args: argparse.Namespace) -> dict:
    if not args.data_start <= args.selection_start < args.calibration_start < args.test_start <= args.test_end <= args.as_of:
        raise ValueError("Require data-start <= selection-start < calibration-start < test-start <= test-end <= as-of")
    horizons = tuple(sorted(set(args.horizons)))
    if not horizons or min(horizons) <= 0:
        raise ValueError("Forecast horizons must be positive days")
    if args.window_days <= 0 or args.stride_days <= 0 or args.min_observations < 4:
        raise ValueError("Window/stride must be positive and min-observations at least four")
    if not 0 <= args.min_span_days <= args.window_days:
        raise ValueError("min-span-days must lie between zero and window-days")
    if not 0 <= args.target_tolerance_days < min(horizons):
        raise ValueError("Target tolerance must be nonnegative and smaller than the shortest horizon")
    if args.nodata_value is not None and not np.isfinite(args.nodata_value):
        raise ValueError("A numeric no-data sentinel must be finite")
    path = args.input
    if path is None:
        if args.format != "ngl":
            raise ValueError("EGMS input requires --input path/to/vertical.csv and --point-id PID")
        path = Path("data/raw/ngl") / f"{args.point_id}.tenv3"
    if not path.is_file():
        raise ValueError(f"Input not found: {path}. First run: python -m pipeline.prediction fetch")
    existing_path = args.output / "forecast.json"
    if existing_path.exists():
        existing = json.loads(existing_path.read_text())
        expected_source = "gnss" if args.format == "ngl" else "egms_ortho_vertical"
        if (existing.get("point_id"), existing.get("site"), existing.get("source", {}).get("type")) != (args.point_id, args.site, expected_source):
            raise ValueError("Output contains a different point/site/source; choose a separate --output directory")
    loaded = load_ngl(path, args.point_id, args.max_sigma_mm) if args.format == "ngl" else load_egms(path, args.point_id, args.nodata_value)
    series = loaded.between(args.data_start, args.as_of)
    age = (args.as_of - series.dates[-1]).days
    required_horizons = tuple(sorted(set(horizons) | {h + age for h in horizons}))
    periods = {"selection": (args.selection_start, args.calibration_start - timedelta(days=1)),
               "calibration": (args.calibration_start, args.test_start - timedelta(days=1)),
               "test": (args.test_start, args.test_end)}
    kwargs = {"window_days": args.window_days, "stride_days": args.stride_days,
              "min_observations": args.min_observations, "min_span_days": args.min_span_days,
              "target_tolerance_days": args.target_tolerance_days}
    rows = {name: rolling_backtest(series, start, end, required_horizons, **kwargs)
            for name, (start, end) in periods.items()}
    scores = {"selection": summarize(rows["selection"]),
              "calibration": summarize(rows["calibration"]),
              "test": summarize(rows["test"], rows["calibration"])}
    for period, values in scores.items():
        if any(str(h) not in values or any(values[str(h)].get(name, {}).get("n", 0) < 5
                                           for name in MODEL_NAMES) for h in required_horizons):
            raise ValueError(f"Too few observed backtest targets in {period}. Check date coverage, training window, and target tolerance")
    selected = select_models(scores["selection"])
    train_days, train_values = training_window(series, series.days[-1], args.window_days,
                                               args.min_observations, args.min_span_days)
    fits = {name: fit_model(name, train_days, train_values) for name in MODEL_NAMES}
    issued = utc_now()
    gaps = [{"after": a.isoformat(), "before": b.isoformat(), "missing_days": (b - a).days - 1}
            for a, b in zip(series.dates, series.dates[1:]) if (b - a).days > 30]
    warnings = ["Empirical ranges do not guarantee nominal coverage for dependent or changing time series",
                "Retrospective backtests use the current provider release, not archived publication vintages"]
    if age:
        warnings.append(f"Last observation precedes forecast origin by {age} days; intervals use the longer effective leads")
    if gaps:
        warnings.append("Large observation gaps exist; no missing observations were filled")
    forecast = {
        "schema_version": 1, "id": f"prediction-{args.site}-{series.point_id}",
        "site": args.site, "point_id": series.point_id,
        "source": series.source, "component": "vertical", "units": "mm", "positive_direction": "up",
        "reference_date": series.dates[0].isoformat(), "issued_at_utc": issued,
        "forecast_origin": args.as_of.isoformat(), "data_cutoff": series.dates[-1].isoformat(),
        "observation_age_days": age, "last_observation_mm": float(series.values[-1]),
        "requested_horizons_days": list(horizons),
        "selection_method": "Lowest development MAE per effective lead; final test never selects the model",
        "interval_method": "Absolute rolling-error order statistic ceil((n+1)*coverage) from calibration split",
        "software": {"name": "spaceapps-prediction", "version": __version__,
                     "assistance": "Implementation assisted by OpenAI Codex; observations are provider data"},
        "predictions": [], "model_predictions": {}, "warnings": warnings,
        "nisar_validation": {"status": "not_performed", "reason": "Requires corrected GUNW and compatible motion geometry"},
    }
    for horizon in horizons:
        target = args.as_of + timedelta(days=horizon)
        lead = horizon + age
        for name, fitted in fits.items():
            value = float(fitted.predict(np.array([target.toordinal()]))[0])
            item = {"target_date": target.isoformat(), "horizon_days": horizon,
                    "lead_from_last_observation_days": lead, "model": name, "value_mm": value,
                    "delta_since_last_observation_mm": value - float(series.values[-1]),
                    "intervals": _intervals(rows["calibration"], name, lead, value),
                    "backtest_at_effective_lead": scores["test"][str(lead)][name]}
            forecast["model_predictions"].setdefault(name, []).append(item)
            if name == selected[lead]:
                forecast["predictions"].append(item)
    forecast["predictions"].sort(key=lambda p: p["horizon_days"])
    metrics = {"schema_version": 1, "issued_at_utc": issued, "source": series.source,
               "evaluation": "retrospective rolling-origin, current provider release",
               "periods": {name: {"start": a.isoformat(), "end": b.isoformat()} for name, (a, b) in periods.items()},
               "configuration": kwargs | {"data_start": args.data_start.isoformat(), "as_of": args.as_of.isoformat(),
                                           "evaluated_horizons_days": list(required_horizons)},
               "selected_models_by_lead": selected,
               "observations": {"n": len(series.dates), "start": series.dates[0].isoformat(),
                                "end": series.dates[-1].isoformat(), "large_gaps": gaps},
               "current_fits": {name: {"origin": date.fromordinal(int(fit.origin)).isoformat(),
                                       "coefficients": fit.coefficients.tolist()}
                                for name, fit in fits.items()},
               "software": {"pipeline_version": __version__, "python": platform.python_version(),
                            "numpy": np.__version__, "assistance": "Implementation assisted by OpenAI Codex"},
               **scores}
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    with (output / "observations.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["point_id", "date", "displacement_mm"])
        writer.writerows((series.point_id, day.isoformat(), float(value)) for day, value in zip(series.dates, series.values))
    with (output / "backtest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", *rows["test"][0].keys()])
        writer.writeheader()
        for split, entries in rows.items():
            writer.writerows({"split": split, **entry} for entry in entries)
    write_json(output / "forecast.json", forecast)
    write_json(output / "metrics.json", metrics)
    if not args.no_plot:
        from .plot import plot_results
        plot_results(series, forecast, metrics, output)
    _update_manifest(args.manifest, forecast, output, not args.no_plot)
    return forecast


def main(argv: list[str] | None = None) -> int:
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.command == "fetch":
            print(fetch_ngl(args.station, args.directory))
            return 0
        forecast = run(args)
    except (ValueError, OSError, URLError) as error:
        print(f"prediction: {error}", file=sys.stderr)
        return 1
    print(f"Exported {forecast['source']['type']} forecast for {forecast['point_id']} to {args.output}")
    print(f"Observations through {forecast['data_cutoff']}; forecast origin {forecast['forecast_origin']}")
    for item in forecast["predictions"]:
        print(f"  +{item['horizon_days']} days: {item['model']}, change from last observation "
              f"{item['delta_since_last_observation_mm']:+.2f} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
