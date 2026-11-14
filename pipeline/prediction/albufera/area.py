"""Flooded hectares inside the rice-field mask, one row per Sentinel-1 pass.

Each pass's WTR tiles (30 m, in their own UTM zone: Albufera straddles zones 30
and 31) are put onto the 20 m site grid by nearest neighbour, so classes are
never blended. A pixel counts as flooded when DSWx-S1 says open water (1) or
inundated vegetation (3). Masked classes (250 HAND, 251 layover/shadow) and
fill (255) are not observed: their share is recorded, and passes that observe
too little of the mask are flagged rather than silently scaled.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from .mask import PIXEL_HA

FILL = 255
OBSERVED_CLASSES = (0, 1, 3)
MIN_OBSERVED_FRACTION = 0.9

COLUMNS = ("date", "begin_utc", "pass_id", "platform", "tiles", "open_water_ha", "inundated_vegetation_ha",
           "flooded_ha", "observed_fraction", "flooded_share_of_observed", "usable")


def merge_on_grid(paths: list[Path], grid: dict) -> np.ndarray:
    """WTR classes of one pass on the site grid; the first observed value wins per pixel."""
    merged = np.full((grid["height"], grid["width"]), FILL, dtype="uint8")
    for path in paths:
        tile = np.full_like(merged, FILL)
        with rasterio.open(path) as src:
            reproject(source=rasterio.band(src, 1), destination=tile,
                      src_nodata=src.nodata if src.nodata is not None else FILL,
                      dst_transform=grid["transform"], dst_crs=grid["crs"],
                      dst_nodata=FILL, resampling=Resampling.nearest)
        take = ~np.isin(merged, OBSERVED_CLASSES) & np.isin(tile, OBSERVED_CLASSES)
        take |= (merged == FILL) & (tile != FILL)  # keep a masked class over plain fill
        merged[take] = tile[take]
    return merged


def summarize_pass(classes: np.ndarray, mask: np.ndarray) -> dict:
    """Hectares of each flooded class in the mask, and how much of the mask was observed."""
    inside = classes[mask]
    n = inside.size
    if n == 0:
        raise ValueError("Empty rice mask")
    observed = int(np.isin(inside, OBSERVED_CLASSES).sum())
    open_water = int((inside == 1).sum())
    veg = int((inside == 3).sum())
    return {
        "open_water_ha": round(open_water * PIXEL_HA, 2),
        "inundated_vegetation_ha": round(veg * PIXEL_HA, 2),
        "flooded_ha": round((open_water + veg) * PIXEL_HA, 2),
        "observed_fraction": round(observed / n, 4),
        "flooded_share_of_observed": round((open_water + veg) / observed, 4) if observed else None,
        "usable": observed / n >= MIN_OBSERVED_FRACTION,
    }


def build_table(index: list[dict], site_dir: Path, mask: np.ndarray, grid: dict) -> list[dict]:
    rows = []
    for entry in index:
        paths = [site_dir / f for f in entry.get("files", [])]
        if not paths:
            continue
        stats = summarize_pass(merge_on_grid(paths, grid), mask)
        rows.append({"date": entry["date"], "begin_utc": entry["begin_utc"], "pass_id": entry["pass_id"],
                     "platform": entry["platform"], "tiles": "+".join(entry["tiles"]), **stats})
    return rows


def write_table(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_table(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
