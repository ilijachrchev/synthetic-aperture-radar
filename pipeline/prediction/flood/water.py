"""Flooded hectares per Sentinel-1 pass in each site's assessment zone.

Zone = land the satellite can see: not sea, not permanent water (JRC >= 90 %),
not urban (WorldCover 50, where radar water maps are unreliable), at Albufera
not the rice mask (deliberately flooded), and observed (DSWx classes 0, 1 or 3)
in at least ZONE_MIN_OBSERVED of the passes, which drops hills masked by HAND
and radar shadow.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

from pipeline.config import DATA_DIR

from ..albufera.area import OBSERVED_CLASSES, merge_on_grid
from ..albufera.mask import PIXEL_HA

CONTEXT_DIR = DATA_DIR / "context"
LABELS_DIR = DATA_DIR / "labels"
RICE_MASK = DATA_DIR / "prediction" / "albufera" / "rice_mask.tif"
ZONE_MIN_OBSERVED = 0.8
MIN_PASS_OBSERVED = 0.9


def land(site: str) -> tuple[np.ndarray, dict]:
    """Candidate zone before the observation filter, and the grid."""
    def read(name):
        with rasterio.open(CONTEXT_DIR / f"{site}_{name}_20m.tif") as src:
            return src.read(1), {"crs": src.crs, "transform": src.transform, "width": src.width, "height": src.height}
    wc, grid = read("worldcover_2021")
    jrc, _ = read("jrc_occurrence")
    sea, _ = read("sea")
    out = (sea == 0) & ~((jrc >= 90) & (jrc != 255)) & (wc != 50) & (wc != 0)
    if site == "albufera":
        with rasterio.open(RICE_MASK) as src:
            out &= src.read(1) == 0
    return out, grid


def polygon_mask(path: Path, grid: dict) -> np.ndarray:
    g = gpd.read_file(path).to_crs(grid["crs"])
    return rasterize(((geom, 1) for geom in g.geometry if geom is not None),
                     out_shape=(grid["height"], grid["width"]), transform=grid["transform"],
                     fill=0, dtype="uint8").astype(bool)


def passes(index: list[dict], site_dir: Path, grid: dict):
    for entry in index:
        paths = [site_dir / f for f in entry.get("files", [])]
        if paths:
            yield entry, merge_on_grid(paths, grid)


def zone(index: list[dict], site_dir: Path, candidate: np.ndarray, grid: dict) -> np.ndarray:
    """Candidate pixels observed in at least ZONE_MIN_OBSERVED of the passes."""
    seen = np.zeros(candidate.shape, dtype=np.int32)
    n = 0
    for _, classes in passes(index, site_dir, grid):
        seen += np.isin(classes, OBSERVED_CLASSES)
        n += 1
    if not n:
        raise ValueError("No downloaded passes")
    return candidate & (seen >= ZONE_MIN_OBSERVED * n)


def table(index: list[dict], site_dir: Path, zone_mask: np.ndarray, grid: dict,
          check_masks: dict[str, np.ndarray] | None = None) -> list[dict]:
    """One row per pass: flooded ha in the zone, observed share, and flooded ha inside optional check masks."""
    n_zone = int(zone_mask.sum())
    rows = []
    for entry, classes in passes(index, site_dir, grid):
        inside = classes[zone_mask]
        observed = int(np.isin(inside, OBSERVED_CLASSES).sum())
        flooded = int(np.isin(inside, (1, 3)).sum())
        row = {"date": entry["date"], "begin_utc": entry["begin_utc"], "pass_id": entry["pass_id"],
               "platform": entry["platform"], "zone_ha": round(n_zone * PIXEL_HA, 1),
               "flooded_ha": round(flooded * PIXEL_HA, 2),
               "observed_fraction": round(observed / n_zone, 4) if n_zone else 0.0,
               "usable": n_zone > 0 and observed / n_zone >= MIN_PASS_OBSERVED}
        for name, m in (check_masks or {}).items():
            sel = classes[m & zone_mask]
            row[f"flooded_in_{name}_ha"] = round(int(np.isin(sel, (1, 3)).sum()) * PIXEL_HA, 2)
        rows.append(row)
    return rows
