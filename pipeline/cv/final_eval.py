"""Final CV evaluation, following docs/CV_PROTOCOL.md: choose on validation, then test once.

1. Choose the final ensemble and threshold on the validation blocks only: E2 (3 seeds), E2 + E4,
   E2 + E5, E2 + E4 + E5; the highest pooled IoU on changing open water wins, ties go to fewer models.
2. Threshold of the Albufera-only control (E3, 2 seeds) from its own validation sweep; the previous
   final model (E1, 6 U-Nets) keeps its threshold of 0.4.
3. Score each once on the test sites (Pego-Oliva with its extra 167 D stack, Donana), with the
   baseline and the DANA flood checks, and build the benchmark tables with bootstrap intervals.

    python -m pipeline.cv.final_eval        # after the training runs of docs/CV_RESULTS.md

Writes data/metrics/cv_select_*.json, cv_test_*.json and cv_benchmark_final.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""
import json
import time
from pathlib import Path

from pipeline.cv.benchmark import print_table, summarize
from pipeline.cv.evaluate import METRICS_DIR, model_report, threshold_sweep

M = Path("data/models")
E2 = [M / f"cv_e2_aec_s{s}.pt" for s in (0, 1, 2)]
E4, E5 = M / "cv_e4_aec_current_s0.pt", M / "cv_e5_aec_gap13_s0.pt"
E3 = [M / "cv_e3_alb_s0.pt", M / "cv_e3_alb_s1.pt"]
E1 = [M / n for n in ("cv_unet.pt", "cv_unet_v3a.pt", "cv_unet_v3b.pt", "cv_unet_v3c.pt",
                      "cv_unet_v3c_s1.pt", "cv_unet_v2_s1.pt")]
THRESHOLDS = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]
TEST_SITES = ("pego_oliva", "donana")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save(name: str, obj: dict) -> Path:
    path = METRICS_DIR / f"{name}.json"
    path.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    return path


def best_row(sweep: dict) -> dict:
    return max(sweep["rows"], key=lambda r: (r["open_pooled_iou"] or -1.0))


def main() -> None:
    candidates = {"e2": E2, "e2_e4": E2 + [E4], "e2_e5": E2 + [E5], "e2_e4_e5": E2 + [E4, E5]}
    choice = {}
    for name, paths in candidates.items():
        log(f"validation sweep {name} ({len(paths)} models)")
        sweep = threshold_sweep(paths, THRESHOLDS)
        save(f"cv_select_{name}_sweep", sweep)
        row = best_row(sweep)
        choice[name] = {"pooled_iou": row["open_pooled_iou"], "threshold": row["threshold"], "models": len(paths),
                        "median_iou": row["open_median_iou"]}
        log(f"  best {row}")
    final = max(choice, key=lambda k: (choice[k]["pooled_iou"] or -1.0, -choice[k]["models"]))
    log(f"chosen on validation: {final} {choice[final]}")
    save("cv_select_summary", {"rule": "highest pooled validation IoU, ties to fewer models", "candidates": choice,
                               "chosen": final})

    log("validation sweep of the Albufera-only control (E3)")
    e3_sweep = threshold_sweep(E3, THRESHOLDS)
    save("cv_select_e3_sweep", e3_sweep)
    e3_thr = best_row(e3_sweep)["threshold"]

    reports = {}
    for name, paths, thr in (("cv_test_multisite", candidates[final], choice[final]["threshold"]),
                             ("cv_test_albufera_only", E3, e3_thr),
                             ("cv_test_previous", E1, 0.4)):
        log(f"test {name}: {len(paths)} models, threshold {thr}")
        report = model_report(paths, thr, val_only=False, sites=TEST_SITES)
        reports[name] = report
        log(f"  -> {save(name, report)}")

    summary = summarize(reports)
    print_table(summary, list(reports))
    save("cv_benchmark_final", {"reports": list(reports), "groups": summary})
    log("done")


if __name__ == "__main__":
    main()
