"""Albufera flooded-area forecast: python -m pipeline.prediction.albufera <step>.

    history   find (and with --download, fetch) every DSWx-S1 pass since Aug 2024
    mask      build the rice-field mask on the site grid
    area      flooded hectares per pass -> water_area.csv
    forecast  backtest, select, calibrate, forecast -> forecast.json, metrics.json, chart
    all       mask, area and forecast from what is already downloaded
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path

from pipeline.config import DATA_DIR, REPO_ROOT, get_site
from pipeline.dswx import DSWX_COLLECTION
from pipeline.prediction.manifest import upsert as upsert_manifest

from . import SITE
from . import area as area_mod
from . import forecast as fc
from . import history
from . import mask as mask_mod

OUT_DIR = DATA_DIR / "prediction" / SITE
MASK_PATH = OUT_DIR / "rice_mask.tif"
MASK_STATS = OUT_DIR / "rice_mask.json"
AREA_CSV = OUT_DIR / "water_area.csv"
MANIFEST = DATA_DIR / "manifest.json"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def cmd_history(args: argparse.Namespace) -> None:
    site = get_site(SITE)
    granules = history.search_range(site, args.start, args.end)
    index = history.build_index(granules)
    print(f"{site.name}: {len(granules)} DSWx-S1 granules -> {len(index)} passes, "
          f"{index[0]['date'] if index else '-'} to {index[-1]['date'] if index else '-'}")
    if args.download:
        out = history.download(site, index)
        print(f"  index -> {rel(out)}")
    else:
        print("  dry run: add --download (needs the Earthdata login in ~/.netrc)")


def cmd_mask(_: argparse.Namespace) -> dict:
    stats = mask_mod.build(SITE, MASK_PATH)
    write_json(MASK_STATS, stats)
    print(f"rice mask: {stats['area_ha']} ha -> {rel(MASK_PATH)}")
    return stats


def cmd_area(_: argparse.Namespace) -> None:
    site_dir = history.HISTORY_RAW / SITE
    index_path = site_dir / "index.json"
    if not index_path.exists():
        raise SystemExit(f"No {rel(index_path)}: run the history step with --download first")
    mask, grid = mask_mod.load(MASK_PATH)
    rows = area_mod.build_table(json.loads(index_path.read_text(encoding="utf-8")), site_dir, mask, grid)
    area_mod.write_table(rows, AREA_CSV)
    usable = sum(1 for r in rows if r["usable"])
    print(f"water area: {len(rows)} passes ({usable} usable) -> {rel(AREA_CSV)}")


def plot(result: dict, mask_ha: float, path_base: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    days, values = result["series"]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot([date.fromordinal(int(d)) for d in days], values, ".", ms=4, color="#2b6cb0",
            label="Observed (Sentinel-1 DSWx-S1)")
    preds = result["predictions"]
    if preds:
        t = [date.fromisoformat(p["target_date"]) for p in preds]
        v = [p["value_ha"] for p in preds]
        for label, alpha in (("95", 0.15), ("80", 0.3)):
            lo = [p["intervals"][label]["lower_ha"] for p in preds]
            hi = [p["intervals"][label]["upper_ha"] for p in preds]
            if None not in lo and None not in hi:
                ax.fill_between(t, lo, hi, color="#dd6b20", alpha=alpha, lw=0, label=f"{label}% range")
        ax.plot(t, v, "o-", color="#dd6b20", label="Forecast")
    ax.axvline(date.fromisoformat(result["forecast_origin"]), color="grey", ls="--", lw=1)
    ax.set_ylim(0, mask_ha * 1.02)
    ax.set_ylabel("Flooded area in rice fields (ha)")
    ax.set_title(f"Albufera rice fields: flooded area · forecast made on {result['forecast_origin']}")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(path_base.with_suffix(f".{ext}"), dpi=150)
    plt.close(fig)


def cmd_forecast(args: argparse.Namespace) -> dict:
    stats = json.loads(MASK_STATS.read_text(encoding="utf-8"))
    mask_ha = float(stats["area_ha"])
    rows = area_mod.read_table(AREA_CSV)
    days, values = fc.daily_series(rows, mask_ha)
    settings = fc.Settings()
    result = fc.forecast(days, values, args.as_of, args.horizons, mask_ha, settings)
    result["forecast_origin"] = args.as_of.isoformat()
    issued = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    usable = [r for r in rows if str(r["usable"]) == "True"]
    forecast_json = {
        "schema_version": 1,
        "id": "prediction-albufera-flooded-area",
        "site": SITE,
        "quantity": "flooded area inside the rice-field mask (open water + inundated vegetation)",
        "units": "ha",
        "issued_at_utc": issued,
        "forecast_origin": result["forecast_origin"],
        "data_cutoff": result["data_cutoff"],
        "observation_age_days": result["observation_age_days"],
        "recent_level_ha": result["recent_level_ha"],
        "climatology_at_cutoff_ha": result["climatology_at_cutoff_ha"],
        "mask": {"file": rel(MASK_PATH), "area_ha": mask_ha, "rule": stats["rule"]},
        "source": {"type": "sentinel-1 water maps", "collection": DSWX_COLLECTION, "layer": "B01_WTR",
                   "flooded_classes": {"1": "open water", "3": "inundated vegetation"},
                   "passes_used": len(usable), "first_date": usable[0]["date"] if usable else None,
                   "last_date": usable[-1]["date"] if usable else None},
        "season": {"start_month": fc.SEASON_START_MONTH, "current": result["current_season"],
                   "reference": result["reference_seasons"]},
        "selection_method": "Lowest MAE per effective lead on past seasons held out in turn; current season never selects",
        "interval_method": "Absolute-error order statistic ceil((n+1)*coverage) from the selection folds; "
                           "clipped to 0 and the mask area. Historical-error ranges, not a coverage guarantee",
        "selected_models_by_lead": result["selected_models_by_lead"],
        "predictions": result["predictions"],
        "model_predictions": result["model_predictions"],
        "nisar_check": {"status": "not_performed"},
        "caveats": [
            "Seasonal agricultural flooding of rice fields, not a disaster flood forecast.",
            "Wind can roughen water and hide it from radar; single passes can read low.",
            "Only two past seasons: climatology is thin and the ranges are wide on purpose.",
        ],
    }
    metrics = {
        "schema_version": 1, "issued_at_utc": issued, "forecast_origin": result["forecast_origin"],
        "settings": asdict(settings),
        "selected_models_by_lead": result["selected_models_by_lead"],
        "scores": result["scores"],
        "series": {"days": int(len(days)), "first": date.fromordinal(int(days[0])).isoformat(),
                   "last": result["data_cutoff"]},
    }
    out = args.output
    write_json(out / "forecast.json", forecast_json)
    write_json(out / "metrics.json", metrics)
    with (out / "backtest.csv").open("w", newline="", encoding="utf-8") as f:
        brows = result["backtest_rows"]
        if brows:
            writer = csv.DictWriter(f, fieldnames=list(brows[0]))
            writer.writeheader()
            writer.writerows(brows)
    if not args.no_plot:
        plot(result, mask_ha, out / "chart")
    update_manifest(args.manifest, forecast_json, out, not args.no_plot)

    for p in result["predictions"]:
        r80 = p["intervals"]["80"]
        print(f"  {p['target_date']} (+{p['horizon_days']} d): {p['value_ha']} ha "
              f"[80%: {r80['lower_ha']}-{r80['upper_ha']}] via {p['model']}")
    print(f"forecast -> {rel(out / 'forecast.json')}")
    return forecast_json


def update_manifest(path: Path, forecast_json: dict, out: Path, has_plot: bool) -> None:
    entry = {
        "model": "prediction", "site": SITE, "layer": "flooded_area", "date": forecast_json["forecast_origin"],
        "id": forecast_json["id"],
        "file": rel(out / "forecast.json"), "metrics": rel(out / "metrics.json"),
        "observations": rel(AREA_CSV), "chart": rel(out / "chart.png") if has_plot else None,
        "source_type": "dswx-s1", "units": "ha",
        "issued_at_utc": forecast_json["issued_at_utc"], "data_cutoff": forecast_json["data_cutoff"],
    }
    upsert_manifest(path, [entry])


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Albufera rice-field flooded-area forecast")
    sub = root.add_subparsers(dest="command", required=True)
    h = sub.add_parser("history", help="find every DSWx-S1 pass; --download fetches them")
    h.add_argument("--start", default="2024-08-01")
    h.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat())
    h.add_argument("--download", action="store_true")
    sub.add_parser("mask", help="rice-field mask on the site grid")
    sub.add_parser("area", help="flooded hectares per pass")
    for name in ("forecast", "all"):
        f = sub.add_parser(name, help="backtest and forecast" if name == "forecast" else "mask + area + forecast")
        f.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
        f.add_argument("--horizons", type=int, nargs="+", default=[12, 24, 36])
        f.add_argument("--output", type=Path, default=OUT_DIR)
        f.add_argument("--manifest", type=Path, default=MANIFEST)
        f.add_argument("--no-plot", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "history":
        cmd_history(args)
    elif args.command == "mask":
        cmd_mask(args)
    elif args.command == "area":
        cmd_area(args)
    elif args.command == "forecast":
        cmd_forecast(args)
    else:
        cmd_mask(args)
        cmd_area(args)
        cmd_forecast(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
