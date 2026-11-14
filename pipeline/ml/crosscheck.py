"""Cross-check: do the class maps of two tracks of one site agree?

Each track sees the ground from its own angle and gets its own trained model,
so pixel-by-pixel agreement between the two maps tells which classes the
radar separates reliably, independent of the labels.

    python -m pipeline.ml.crosscheck          # every site with two ML stacks

Writes data/ml/crosscheck.json. A class counts as "reliable" when the two maps
overlap on at least RELIABLE_IOU of its pixels (intersection over union).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio

from pipeline.config import STACKS

from . import config, export

RELIABLE_IOU = 0.70


def compare(site: str, stack_a: str, stack_b: str, ml_dir: Path = config.ML_OUT_DIR) -> dict:
    maps, metrics = {}, {}
    for s in (stack_a, stack_b):
        d = ml_dir / f"{site}_{s}"
        with rasterio.open(d / "class_utm.tif") as src:
            maps[s] = src.read(1)
        metrics[s] = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
    a, b = maps[stack_a], maps[stack_b]
    both = (a != config.NODATA_U8) & (b != config.NODATA_U8)
    classes = {}
    for i, name in enumerate(config.CLASSES):
        in_a, in_b = (a == i) & both, (b == i) & both
        union = int((in_a | in_b).sum())
        if union == 0:
            continue
        iou = float((in_a & in_b).sum() / union)
        classes[name] = {
            "area_ha": {stack_a: round(float((a == i).sum()) * config.PIXEL_HA),
                        stack_b: round(float((b == i).sum()) * config.PIXEL_HA)},
            "overlap_iou": round(iou, 3),
            "f1": {s: round(metrics[s]["per_class"][name]["f1"], 3) for s in (stack_a, stack_b)},
            "reliable": iou >= RELIABLE_IOU,
        }
    return {
        "site": site, "stacks": [stack_a, stack_b],
        "pixels_agree": round(float((a[both] == b[both]).mean()), 3),
        "accuracy": {s: round(metrics[s]["overall_accuracy"], 3) for s in (stack_a, stack_b)},
        "macro_f1": {s: round(metrics[s]["macro_f1"], 3) for s in (stack_a, stack_b)},
        "reliable_classes": [n for n, c in classes.items() if c["reliable"]],
        "classes": classes,
    }


def main() -> None:
    results = []
    for site, stacks in STACKS.items():
        ready = [s for s in stacks if (config.ML_OUT_DIR / f"{site}_{s}" / "class_utm.tif").exists()]
        if len(ready) == 2:
            r = compare(site, *ready)
            results.append(r)
            print(f"{site} {ready[0]} vs {ready[1]}: {r['pixels_agree']:.1%} of pixels agree; "
                  f"reliable: {', '.join(r['reliable_classes'])}")
    out = {
        "what": "Pixel agreement between the class maps of two tracks of one site, each with its own "
                "trained model. A class is reliable when the maps overlap on at least "
                f"{RELIABLE_IOU:.0%} of its pixels (IoU).",
        "sites": results,
    }
    export.write_json(out, config.ML_OUT_DIR / "crosscheck.json")
    print(f"wrote {config.ML_OUT_DIR / 'crosscheck.json'}")


if __name__ == "__main__":
    main()
