"""Benchmark tables for the CV water models: pooled IoU per site with bootstrap intervals.

    python -m pipeline.cv.benchmark data/metrics/cv_multi.json data/metrics/cv_final_v2.json

Reads model reports written by python -m pipeline.cv.evaluate --model (one row per
date for the baseline and the U-Net, scored on exactly the same pixels) and gives,
per site and split, for each model:
- pooled IoU of changing open water (and of any water): the sum of true positives
  over the sum of TP + FP + FN over every scored date, so each date weighs by its
  water, not one vote per date;
- the median IoU over dates (each date one vote);
- a 95 % bootstrap interval of the pooled IoU: dates resampled with replacement
  within each stack (tracks differ), N_BOOT times with a fixed seed;
- paired differences on the same resampled dates: each U-Net minus the baseline,
  and each later report minus the first one, so "better" comes with an interval.
Rows of several reports are matched by site, stack and date; only dates every
model scored are used. Test sites (never seen in training) are also pooled
together. Writes <first report>_benchmark.json next to the first report.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

N_BOOT = 2000
SEED = 0
TEST_SPLIT = "test site, never seen in training"
KINDS = {"open": "", "any": "any_"}  # key prefixes of the counts in the rows


def scored_rows(report: dict, model: str) -> dict[tuple[str, str, str], dict]:
    """(site, stack, date) -> row, for one model of a report, scored dates only."""
    return {(r["site"], r["stack"], r["date"]): r for r in report["water_vs_dswx"]
            if r["model"] == model and "skipped" not in r and "tp" in r}


def counts(rows: list[dict], prefix: str) -> np.ndarray:
    """(n, 2) array of TP and TP + FP + FN per row."""
    return np.array([[r[f"{prefix}tp"], r[f"{prefix}tp"] + r[f"{prefix}fp"] + r[f"{prefix}fn"]] for r in rows],
                    dtype="float64").reshape(-1, 2)


def pooled_iou(c: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray | float | None:
    """Pooled IoU of count rows; with a (B, n) weight matrix, one value per bootstrap draw."""
    if weights is None:
        return float(c[:, 0].sum() / c[:, 1].sum()) if c[:, 1].sum() else None
    union = weights @ c[:, 1]
    return np.where(union > 0, (weights @ c[:, 0]) / np.where(union > 0, union, 1), np.nan)


def bootstrap_weights(strata: list[str], n_boot: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    """(n_boot, n) multiplicity of each date in each draw; dates are resampled within their stratum."""
    rng = np.random.default_rng(seed)
    strata_arr = np.array(strata)
    w = np.zeros((n_boot, len(strata)))
    for s in dict.fromkeys(strata):
        idx = np.flatnonzero(strata_arr == s)
        draws = rng.integers(0, len(idx), (n_boot, len(idx)))
        for b in range(n_boot):
            w[b] += np.bincount(idx[draws[b]], minlength=len(strata))
    return w


def interval(values: np.ndarray) -> list[float] | None:
    v = values[np.isfinite(values)]
    return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] if v.size else None


def summarize(reports: dict[str, dict], n_boot: int = N_BOOT) -> list[dict]:
    """One entry per (site, split) group and per pooled test group, with every model's scores."""
    names = list(reports)
    models = {"baseline": scored_rows(reports[names[0]], "baseline")}
    models.update({name: scored_rows(rep, "unet") for name, rep in reports.items()})
    split_of = {(r["site"], r["stack"], r["date"]): r["split"] for rep in reports.values()
                for r in rep["water_vs_dswx"] if r["model"] == "unet"}
    keys = sorted(set.intersection(*(set(m) for m in models.values())))
    # a site can be a training site of one report and a test site of another: then not comparable
    splits = {}
    for k in keys:
        per_report = {r["split"] for rep in reports.values() for r in rep["water_vs_dswx"]
                      if r["model"] == "unet" and (r["site"], r["stack"], r["date"]) == k}
        splits[k] = split_of[k] if len(per_report) == 1 else "mixed: training site of some models"
    groups: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for k in keys:
        groups.setdefault((k[0], splits[k]), []).append(k)
        if splits[k] == TEST_SPLIT:
            groups.setdefault(("all test sites", TEST_SPLIT), []).append(k)

    out = []
    for (site, split), ks in groups.items():
        strata = [f"{k[0]} {k[1]}" for k in ks]
        w = bootstrap_weights(strata, n_boot)
        entry = {"site": site, "split": split, "dates": len(ks), "stacks": sorted(set(strata)), "models": {}}
        boot: dict[str, dict[str, np.ndarray]] = {}
        for model, rows in models.items():
            picked = [rows[k] for k in ks]
            entry["models"][model] = {}
            boot[model] = {}
            for kind, prefix in KINDS.items():
                c = counts(picked, prefix)
                b = pooled_iou(c, w)
                boot[model][kind] = b
                per_date = [r[f"{prefix}iou"] for r in picked if r.get(f"{prefix}iou") is not None]
                entry["models"][model][kind] = {
                    "pooled_iou": round(pooled_iou(c), 4) if pooled_iou(c) is not None else None,
                    "ci95": interval(b),
                    "median_iou": round(float(np.median(per_date)), 4) if per_date else None,
                    "precision": _pooled_ratio(picked, prefix, "fp"),
                    "recall": _pooled_ratio(picked, prefix, "fn"),
                }
        diffs = {}
        for i, name in enumerate(names):
            for ref in ["baseline"] + names[:i]:
                diffs[f"{name} - {ref}"] = {kind: {
                    "pooled_iou": round(entry["models"][name][kind]["pooled_iou"] - entry["models"][ref][kind]["pooled_iou"], 4)
                    if entry["models"][name][kind]["pooled_iou"] is not None and entry["models"][ref][kind]["pooled_iou"] is not None
                    else None,
                    "ci95": interval(boot[name][kind] - boot[ref][kind]),
                    "share_of_draws_better": round(float(np.mean(boot[name][kind] > boot[ref][kind])), 3),
                } for kind in KINDS}
        entry["differences"] = diffs
        out.append(entry)
    order = {TEST_SPLIT: 0}
    return sorted(out, key=lambda e: (order.get(e["split"], 1), e["site"] == "all test sites", e["site"]))


def _pooled_ratio(rows: list[dict], prefix: str, error: str) -> float | None:
    tp = sum(r[f"{prefix}tp"] for r in rows)
    other = sum(r[f"{prefix}{error}"] for r in rows)
    return round(tp / (tp + other), 4) if tp + other else None


def print_table(summary: list[dict], names: list[str]) -> None:
    cols = ["baseline"] + names
    for kind in KINDS:
        print(f"\n{'Changing open water' if kind == 'open' else 'Changing water, open plus flooded vegetation'}"
              " vs same-day Sentinel-1: pooled IoU [95% interval]")
        print("| Site | Split | Dates | " + " | ".join(cols) + " | " + " | ".join(f"{n} - baseline" for n in names) + " |")
        print("|" + "---|" * (3 + len(cols) + len(names)))
        for e in summary:
            m = e["models"]
            cells = [f"{m[c][kind]['pooled_iou']} {m[c][kind]['ci95']}" for c in cols]
            diffs = [f"{e['differences'][f'{n} - baseline'][kind]['pooled_iou']} "
                     f"{e['differences'][f'{n} - baseline'][kind]['ci95']}" for n in names]
            split = "test" if e["split"] == TEST_SPLIT else ("validation" if "validation" in e["split"] else e["split"])
            print(f"| {e['site']} | {split} | {e['dates']} | " + " | ".join(cells) + " | " + " | ".join(diffs) + " |")
        if len(names) > 1:
            print(f"\nPaired, later minus first report ({kind} water):")
            for e in summary:
                for n in names[1:]:
                    d = e["differences"][f"{n} - {names[0]}"][kind]
                    print(f"   {e['site']} ({e['split'][:10]}): {n} - {names[0]} = {d['pooled_iou']} {d['ci95']}, "
                          f"better in {d['share_of_draws_better']:.0%} of draws")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", type=Path, nargs="+", help="model reports from pipeline.cv.evaluate --model")
    parser.add_argument("--boot", type=int, default=N_BOOT, help="bootstrap draws")
    args = parser.parse_args()
    reports = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in args.reports}
    summary = summarize(reports, args.boot)
    print_table(summary, list(reports))
    out = args.reports[0].with_name(f"{args.reports[0].stem}_benchmark.json")
    out.write_text(json.dumps({"reports": [str(p).replace("\\", "/") for p in args.reports], "n_boot": args.boot,
                               "seed": SEED, "groups": summary}, indent=1), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
