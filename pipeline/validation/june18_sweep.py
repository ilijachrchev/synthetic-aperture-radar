"""18 June: does the NISAR result depend on the -15 dB threshold? A sweep on the fixed sample points.

Asked by the review panel of the paper (docs/paper/review/). The 513 points, their strata and their
referee labels stay exactly as committed (data/validation/june18/reference.csv); only the NISAR map
scored on them changes: water = 5x5-filtered HH below T, for T from -13 to -18 dB. The estimator is
the same stratum-weighted one as june18.map_accuracy (the strata are just the sampling design, so any
map can be scored on them, as the U-Net map already is).

    python -m pipeline.validation.june18_sweep [--data DIR]

Writes data/validation/june18/threshold_sweep.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from pipeline.config import DATA_DIR
from pipeline.validation import june18 as j

THRESHOLDS_DB = (-13.0, -14.0, -15.0, -16.0, -17.0, -18.0)
LABELS = {"v1": "label_v1", "v2": "label", "strict": "label_strict"}
REPS = 1000


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=DATA_DIR)
    a = ap.parse_args(argv)
    from pipeline.cv.data import open_stack
    from pipeline.prediction.nisar_check import scene_db

    out = j.OUT_DIR
    strata = json.loads((out / "strata.json").read_text(encoding="utf-8"))
    pts = list(csv.DictReader((out / "reference.csv").open(encoding="utf-8")))
    ds = open_stack(a.data / "stack" / j.STACK_FILE)
    days = [str(t)[:10] for t in ds["time"].values]
    hh, ok, _ = scene_db(ds, days.index(j.DATE))
    rows = np.array([int(p["row"]) for p in pts])
    cols = np.array([int(p["col"]) for p in pts])
    hh_pt, ok_pt = hh[rows, cols], ok[rows, cols]

    # sanity: at -15 dB the point map must reproduce the strata it was sampled from
    at15 = (ok_pt & (hh_pt < j.NISAR_DB)).astype(int)
    rice = [k for k, p in enumerate(pts) if p["stratum"] in "ABCD"]
    agree = float(np.mean([at15[k] == int(pts[k]["nisar"]) for k in rice]))
    if agree < 0.99:
        raise ValueError(f"point map at -15 dB agrees with the strata on only {agree:.3f} of rice points")

    res = {"date": j.DATE, "points": len(pts), "rice_points": len(rice), "check_agreement_at_-15": round(agree, 4),
           "median_hh_db_rice_points": round(float(np.nanmedian(hh_pt[rice])), 2), "by_threshold": {}}
    w = strata["weights"]
    for t in THRESHOLDS_DB:
        key = f"nisar_{-t:.0f}"
        for k, p in enumerate(pts):
            p[key] = int(ok_pt[k] and hh_pt[k] < t)
        row = {"mapped_share_of_rice_points_weighted": round(sum(
            w[s] * np.mean([pts[k][key] for k in rice if pts[k]["stratum"] == s]) for s in "ABCD"), 3)}
        for name, lab in LABELS.items():
            m = j.map_accuracy(pts, w, key, lab)
            ci = j.bootstrap(pts, w, keys=(key,), label=lab, reps=REPS)
            row[name] = {"user": round(m["user"], 3), "producer": round(m["producer"], 3),
                         "user_ci95": [round(x, 3) for x in ci[f"{key}_user"]],
                         "producer_ci95": [round(x, 3) for x in ci[f"{key}_producer"]]}
        res["by_threshold"][f"{t:.0f}"] = row
        print(t, row["mapped_share_of_rice_points_weighted"], row["v1"]["producer"], row["v1"]["user"])
    (out / "threshold_sweep.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("wrote", out / "threshold_sweep.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
