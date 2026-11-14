"""Every downloaded DSWx-S1 pass of a site as one array on the 20 m grid.

Codes are kept as delivered (0 not water, 1 open water, 3 inundated vegetation,
250 masked by the terrain model, 251 layover or shadow, 255 fill) and only
turned into wet / dry / unknown by ``to_water``. A masked or missing pixel is
unknown, never dry.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pipeline.stack import Grid

from ..albufera.area import merge_on_grid
from ..albufera.history import HISTORY_RAW
from .terrain import static_dir

UNKNOWN = 255
WET_CLASSES = (1, 3)
DRY_CLASS = 0


def to_water(classes: np.ndarray) -> np.ndarray:
    """0 observed dry, 1 observed water, 255 unknown."""
    out = np.full(classes.shape, UNKNOWN, dtype="uint8")
    out[classes == DRY_CLASS] = 0
    out[np.isin(classes, WET_CLASSES)] = 1
    return out


def stack_paths(site: str) -> tuple[Path, Path]:
    d = static_dir(site)
    return d / "dswx_classes.npy", d / "dswx_passes.json"


def build(site: str, grid: Grid, history_dir: Path = HISTORY_RAW) -> list[dict]:
    """Write the (pass, y, x) class stack as an .npy memory map plus its pass list, in time order."""
    site_dir = history_dir / site
    index = json.loads((site_dir / "index.json").read_text(encoding="utf-8"))
    index = sorted((e for e in index if e.get("files")), key=lambda e: e["begin_utc"])
    npy, meta = stack_paths(site)
    npy.parent.mkdir(parents=True, exist_ok=True)
    g = {"crs": grid.crs, "transform": grid.transform, "width": grid.width, "height": grid.height}
    out = np.lib.format.open_memmap(npy, mode="w+", dtype="uint8", shape=(len(index), grid.height, grid.width))
    passes = []
    for i, entry in enumerate(index):
        out[i] = merge_on_grid([site_dir / f for f in entry["files"]], g)
        passes.append({"pass_id": entry["pass_id"], "date": entry["date"], "begin_utc": entry["begin_utc"],
                       "platform": entry["platform"],
                       "granules": [Path(f).name.removesuffix("_B01_WTR.tif") for f in entry["files"]]})
    out.flush()
    meta.write_text(json.dumps(passes, indent=1) + "\n", encoding="utf-8")
    return passes


def load(site: str) -> tuple[np.ndarray, list[dict]]:
    npy, meta = stack_paths(site)
    return np.load(npy, mmap_mode="r"), json.loads(meta.read_text(encoding="utf-8"))


def pass_times(passes: list[dict]) -> np.ndarray:
    return np.array([p["begin_utc"].rstrip("Z") for p in passes], dtype="datetime64[s]")
