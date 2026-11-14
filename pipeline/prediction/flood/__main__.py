"""Rain-threshold flood alerts: python -m pipeline.prediction.flood <step>.

    history --site S [--download]   every DSWx-S1 pass over a site since Aug 2024
    water                           flooded ha per pass in each site's zone -> water_<site>.csv
    rain                            daily IFS rain per site -> rain_<site>.csv
    fit [--as-of D]                 labels, threshold, held-out scores, live alert, DANA replay
    all                             water + rain + fit
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import numpy as np

from pipeline.config import DATA_DIR, REPO_ROOT, get_site
from pipeline.prediction.manifest import upsert as upsert_manifest

from . import SITES, model, rain, water
from ..albufera import history

OUT_DIR = DATA_DIR / "prediction" / "flood"
HISTORY_START = "2024-08-01"
# The held-out storm, at both sites: the same DANA also reached the Albufera grid,
# so keeping its Albufera passes in training would leak the test event.
HOLDOUT = {"sites": list(SITES), "start": "2026-10-15", "end": "2026-11-15",
           "event": "DANA Adam, 18-19 Oct 2026 (EMSR935 at Pego-Oliva)"}
# Alert threshold: the published anchor from discussion #9 (ref. 26), chosen before any of our
# data was looked at. Camarasa-Belmonte (2016, J. Hydrol. 541): flash floods in Valencian
# ephemeral streams generally followed about 100 mm of accumulated rain (142 events, 1989-2007).
LITERATURE_MM = 100.0
LITERATURE_SOURCE = "Camarasa-Belmonte (2016), J. Hydrol. 541, 99-115, doi:10.1016/j.jhydrol.2016.03.019"
REPLAY_RUNS = ("2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18")
CHECK_POLYGONS = {"pego_oliva": {"emsr935": DATA_DIR / "labels" / "pego_oliva_emsr935_flood.geojson",
                                 "generalitat": DATA_DIR / "labels" / "pego_oliva_generalitat_footprint.geojson"}}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_history(args) -> None:
    site = get_site(args.site)
    index = history.build_index(history.search_range(site, HISTORY_START, args.end))
    print(f"{site.name}: {len(index)} passes, {index[0]['date']} to {index[-1]['date']}")
    if args.download:
        print(f"  index -> {rel(history.download(site, index))}")


def cmd_water(_) -> None:
    for name in SITES:
        site_dir = history.HISTORY_RAW / name
        index = json.loads((site_dir / "index.json").read_text(encoding="utf-8"))
        candidate, grid = water.land(name)
        zone = water.zone(index, site_dir, candidate, grid)
        checks = {k: water.polygon_mask(p, grid) for k, p in CHECK_POLYGONS.get(name, {}).items()}
        rows = water.table(index, site_dir, zone, grid, checks)
        write_csv(OUT_DIR / f"water_{name}.csv", rows)
        print(f"{name}: zone {zone.sum() * 0.04:,.0f} ha, {len(rows)} passes "
              f"({sum(r['usable'] for r in rows)} usable) -> {rel(OUT_DIR / f'water_{name}.csv')}")


def cmd_rain(args) -> None:
    for name in SITES:
        h = rain.history(get_site(name), HISTORY_START, args.end)
        rows = [{"date": d, "max_mm": round(float(m), 2), "mean_mm": round(float(a), 2)}
                for d, m, a in zip(h["dates"], h["max_mm"], h["mean_mm"])]
        write_csv(OUT_DIR / f"rain_{name}.csv", rows)
        print(f"{name}: {len(rows)} days over {h['points']} points -> {rel(OUT_DIR / f'rain_{name}.csv')}")


def site_samples(name: str) -> tuple[list[dict], list[dict]]:
    days, values = model.daily_values(read_csv(OUT_DIR / f"water_{name}.csv"))
    labels = model.label(days, values)
    rain_rows = read_csv(OUT_DIR / f"rain_{name}.csv")
    rdays = np.array([date.fromisoformat(r["date"]).toordinal() for r in rain_rows])
    rmm = np.array([float(r["max_mm"]) for r in rain_rows])
    return labels, model.samples(name, labels, model.rolling_sum(rdays, rmm))


def in_holdout(s: dict) -> bool:
    return s["site"] in HOLDOUT["sites"] and HOLDOUT["start"] <= s["date"] <= HOLDOUT["end"]


def cmd_fit(args) -> dict:
    labels, samples = {}, []
    for name in SITES:
        labels[name], s = site_samples(name)
        samples += s
    train = [s for s in samples if not in_holdout(s)]
    test = [s for s in samples if in_holdout(s)]
    r_tr = np.array([s["rain_3d_max_mm"] for s in train]); y_tr = np.array([s["new_flood"] for s in train], bool)
    r_te = np.array([s["rain_3d_max_mm"] for s in test]); y_te = np.array([s["new_flood"] for s in test], bool)

    fitted = model.fit_threshold(r_tr, y_tr)
    threshold = LITERATURE_MM
    a, b = model.fit_logistic(r_tr, y_tr)
    base = float(y_tr.mean())
    for s in samples:
        s["predicted_flood"] = int(s["rain_3d_max_mm"] >= threshold)
        s["probability"] = round(float(model.probability(a, b, np.array([s["rain_3d_max_mm"]]))[0]), 3)
        s["split"] = "test" if in_holdout(s) else "train"
    write_csv(OUT_DIR / "events.csv", samples)

    scores = {
        "train": {**model.contingency(r_tr >= threshold, y_tr),
                  **model.brier(model.probability(a, b, r_tr), y_tr, base)},
        "test": {**model.contingency(r_te >= threshold, y_te),
                 **(model.brier(model.probability(a, b, r_te), y_te, base) if len(test) else {})},
        "fitted_threshold": {"threshold_mm_3d": fitted,
                             "train": model.contingency(r_tr >= fitted, y_tr),
                             "test": model.contingency(r_te >= fitted, y_te)},
        "train_by_site": {n: model.contingency(np.array([s["rain_3d_max_mm"] >= threshold for s in train if s["site"] == n]),
                                               np.array([bool(s["new_flood"]) for s in train if s["site"] == n]))
                          for n in SITES},
    }

    # The held-out DANA itself: rain before it, the label, and the check against the official outlines.
    water_rows = read_csv(OUT_DIR / "water_pego_oliva.csv")
    dana_passes = [{k: r[k] for k in r if k in ("date", "platform", "flooded_ha", "observed_fraction",
                                                  "flooded_in_emsr935_ha", "flooded_in_generalitat_ha")}
                   for r in water_rows if "2026-10-14" <= r["date"] <= "2026-11-10"]

    replay = []
    for run_day in REPLAY_RUNS:
        run = rain.past_run(get_site("pego_oliva"), date.fromisoformat(run_day), days=5)
        total = model.max_window_total(np.nan_to_num(run["max_mm"]))
        replay.append({"run": run_day, "forecast_days": run["dates"],
                       "daily_max_mm": [round(float(v), 1) for v in np.nan_to_num(run["max_mm"])],
                       "max_3d_mm": round(total, 1),
                       "alert": "red" if total >= threshold else ("amber" if total >= 0.5 * threshold else "green")})

    issued = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    live = {}
    for name in SITES:
        ens = rain.ensemble(get_site(name), days=7)
        totals = np.array([model.max_window_total(np.nan_to_num(m[:3])) for m in ens["members"]])
        share = float(np.mean(totals >= threshold))
        live[name] = {"window": f"{ens['dates'][0]} to {ens['dates'][2]}", "members": int(len(totals)),
                      "share_above_threshold": round(share, 3), "alert": model.alert_level(share),
                      "max_3d_mm": {"median": round(float(np.median(totals)), 1),
                                    "p90": round(float(np.percentile(totals, 90)), 1),
                                    "max": round(float(totals.max()), 1)}}

    forecast = {
        "schema_version": 1, "id": "prediction-flood-alert", "issued_at_utc": issued,
        "forecast_origin": args.as_of.isoformat(),
        "what": "Alert that new flood water appears on the next Sentinel-1 pass, from the largest 3-day rain total",
        "threshold_mm_3d": threshold,
        "threshold_rule": f"Published anchor, fixed before looking at our data: {LITERATURE_SOURCE}",
        "threshold_fitted_mm_3d": fitted,
        "why_not_fitted": "Only 4 new-flood labels in training, 3 after 7-29 mm of rain (water management or radar "
                          "noise); the best-Peirce threshold then alarms on almost any rain. See metrics.json.",
        "alert_rule": f"share of ECMWF ensemble members whose largest 3-day total in the next 3 days reaches the threshold: "
                      f"red >= {model.ALERT['red']}, amber >= {model.ALERT['amber']}",
        "rain_source": "Open-Meteo: ECMWF IFS 9 km archive (history), IFS single runs (replay), "
                       "ECMWF IFS 0.25 deg 51-member ensemble (live); site value = max over a 0.1 deg lattice",
        "label_rule": {"baseline_days": model.BASELINE_DAYS, "min_excess_ha": model.MIN_EXCESS_HA,
                       "k_spread": model.K_SPREAD, "window_days": model.WINDOW_DAYS, "max_gap_days": model.MAX_GAP_DAYS},
        "holdout": HOLDOUT, "live": live, "dana_replay_pego_oliva": replay,
        "logistic": {"a": round(a, 4), "b": round(b, 4), "form": "p = 1 / (1 + exp(-(a + b ln(1 + rain_mm))))"},
        "caveats": [
            "Gridded rain misses extremes: the IFS cell saw about 72 mm in the DANA, AEMET Pego 634 mm.",
            "Few flood events since Aug 2024, so the threshold is loose and the probability is not calibrated.",
            "The 100 mm anchor comes from station totals; ours is the wettest IFS grid point, a different product.",
            "Local rain only: river water from upstream and sea surge (both mattered in 2024 and 2026) are not inputs.",
            "Label = new water on the next radar pass; floods that drain between passes are missed.",
        ],
    }
    metrics = {"issued_at_utc": issued, "threshold_mm_3d": threshold, "base_rate_train": round(base, 4),
               "samples": {"train": len(train), "test": len(test),
                           "train_events": int(y_tr.sum()), "test_events": int(y_te.sum())},
               "scores": scores, "dana_passes_pego_oliva": dana_passes}
    write_json(OUT_DIR / "forecast.json", forecast)
    write_json(OUT_DIR / "metrics.json", metrics)
    upsert_manifest(DATA_DIR / "manifest.json", [{
        "model": "prediction", "site": name, "stack": "open-meteo-ifs", "layer": "flood_alert",
        "date": forecast["forecast_origin"], "id": f"prediction-flood-alert-{name}",
        "file": rel(OUT_DIR / "forecast.json"), "metrics": rel(OUT_DIR / "metrics.json"),
        "observations": rel(OUT_DIR / f"water_{name}.csv"), "source_type": "open-meteo + dswx-s1",
        "alert": live[name]["alert"], "issued_at_utc": issued} for name in SITES])

    print(f"threshold {threshold} mm in 3 days (fitted would be {fitted}); train {len(train)} samples ({int(y_tr.sum())} floods), "
          f"test {len(test)} ({int(y_te.sum())} floods)")
    print("train:", {k: scores['train'][k] for k in ('hits', 'misses', 'false_alarms', 'peirce_skill', 'brier_skill')})
    print("test: ", {k: scores['test'].get(k) for k in ('hits', 'misses', 'false_alarms', 'peirce_skill', 'brier_skill')})
    print("fitted:", {k: {m: scores['fitted_threshold'][k][m] for m in ('hits', 'misses', 'false_alarms')} for k in ('train', 'test')})
    for r in replay:
        print(f"  replay run {r['run']}: max 3-day {r['max_3d_mm']} mm -> {r['alert']}")
    for n, v in live.items():
        print(f"  live {n}: {v['alert']} ({v['share_above_threshold']:.0%} of members)")
    return forecast


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Rain-threshold flood alerts")
    sub = root.add_subparsers(dest="command", required=True)
    today = datetime.now(timezone.utc).date()
    h = sub.add_parser("history")
    h.add_argument("--site", required=True, choices=SITES)
    h.add_argument("--end", default=today.isoformat())
    h.add_argument("--download", action="store_true")
    sub.add_parser("water")
    r = sub.add_parser("rain")
    r.add_argument("--end", default=(today - timedelta(days=1)).isoformat())
    for name in ("fit", "all"):
        f = sub.add_parser(name)
        f.add_argument("--as-of", type=date.fromisoformat, default=today)
        f.add_argument("--end", default=(today - timedelta(days=1)).isoformat())
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    steps = {"history": [cmd_history], "water": [cmd_water], "rain": [cmd_rain], "fit": [cmd_fit],
             "all": [cmd_water, cmd_rain, cmd_fit]}
    for step in steps[args.command]:
        step(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
