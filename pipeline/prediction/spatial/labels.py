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


class Merged:
    """Sentinel-1 and NISAR passes as one time-ordered stack, read pass by pass (no 0.8 GB copy).

    The NISAR passes come from pipeline.cv.labels.load, already as 0 / 1 / 255 water codes,
    which to_water leaves unchanged.
    """

    def __init__(self, *sources: tuple[np.ndarray, list[dict]]):
        order = sorted(((p["begin_utc"].rstrip("Z"), i, k) for i, (_, passes) in enumerate(sources)
                        for k, p in enumerate(passes)))
        self._sources = sources
        self._where = [(i, k) for _, i, k in order]
        self.passes = [sources[i][1][k] for i, k in self._where]
        self.shape = (len(order),) + tuple(sources[0][0].shape[1:])

    def __getitem__(self, n: int) -> np.ndarray:
        i, k = self._where[n]
        return self._sources[i][0][k]


def load_set(site: str, label_set: str = "s1"):
    """(stack, passes) for 's1' (DSWx-S1 only) or 's1+nisar' (with the team's NISAR water labels)."""
    s1 = load(site)
    if label_set == "s1":
        return s1
    if label_set != "s1+nisar":
        raise ValueError(label_set)
    m = Merged(s1, load_nisar(site))
    return m, m.passes


NISAR_DIR = HISTORY_RAW.parents[1] / "labels_nisar"   # data/labels_nisar, written by pipeline.cv.labels


def load_nisar(site: str, labels_dir: Path = NISAR_DIR) -> tuple[np.ndarray, list[dict]]:
    """The team's NISAR water labels as 0 dry / 1 wet / 255 unknown, with their pass list.

    Same mapping as pipeline.cv.labels.load (class 0 not water, 1 open water; 2 water under plants
    and 3 not assessed stay unknown), read here directly so that PyTorch is not needed.
    """
    import rasterio
    passes = json.loads((labels_dir / f"{site}_passes.json").read_text(encoding="utf-8"))
    out = None
    for i, p in enumerate(passes):
        with rasterio.open(labels_dir.parents[1] / p["class_file"]) as src:
            cls = src.read(1)
        if out is None:
            out = np.full((len(passes),) + cls.shape, UNKNOWN, dtype="uint8")
        out[i][cls == 0] = 0
        out[i][cls == 1] = 1
    return out, passes


def pass_times(passes: list[dict]) -> np.ndarray:
    return np.array([p["begin_utc"].rstrip("Z") for p in passes], dtype="datetime64[s]")
