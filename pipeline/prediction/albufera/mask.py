"""Rice-field mask on the shared 20 m site grid.

A pixel is rice-field candidate when it was water only some of the time in
1984 to 2024 (JRC occurrence 1 to 89 %: seasonal, not permanent water), is
cropland, water or herbaceous wetland in WorldCover 2021, and is not sea. The
Albufera lagoon has occurrence of 90 % or more and drops out; towns and orchards
are other WorldCover classes and drop out too.

Luka found JRC 1 to 89 % covers about 16 % of the Albufera box; the rice area
of the Albufera natural park is about 14,000 ha, which this mask is checked
against.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from pipeline.config import DATA_DIR

CONTEXT_DIR = DATA_DIR / "context"
PIXEL_HA = 0.04  # 20 m x 20 m
WORLDCOVER_KEEP = (40, 80, 90)  # cropland, permanent water bodies, herbaceous wetland
JRC_SEASONAL = (1, 89)  # percent of time water; 255 is no data


def rice_mask(worldcover: np.ndarray, jrc: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """Boolean rice-field mask from three arrays on the same grid."""
    if not (worldcover.shape == jrc.shape == sea.shape):
        raise ValueError("Context layers must share one grid")
    seasonal = (jrc >= JRC_SEASONAL[0]) & (jrc <= JRC_SEASONAL[1])
    return seasonal & np.isin(worldcover, WORLDCOVER_KEEP) & (sea == 0)


def build(site_name: str, out_path: Path, context_dir: Path = CONTEXT_DIR) -> dict:
    """Write the mask as a uint8 GeoTIFF (1 rice, 0 other) and return its statistics."""
    paths = {k: context_dir / f"{site_name}_{k}_20m.tif" for k in ("worldcover_2021", "jrc_occurrence", "sea")}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing context layers (run python -m pipeline.context): {missing}")
    arrays, profile = {}, None
    for key, path in paths.items():
        with rasterio.open(path) as src:
            arrays[key] = src.read(1)
            if profile is None:
                profile = src.profile.copy()
            elif (src.transform, src.crs, src.shape) != (profile["transform"], profile["crs"], (profile["height"], profile["width"])):
                raise ValueError(f"{path.name} is not on the site grid")
    mask = rice_mask(arrays["worldcover_2021"], arrays["jrc_occurrence"], arrays["sea"])
    profile.update(dtype="uint8", count=1, nodata=None, compress="deflate")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mask.astype("uint8"), 1)
    by_class = {int(c): round(float(np.sum(mask & (arrays["worldcover_2021"] == c))) * PIXEL_HA, 1)
                for c in WORLDCOVER_KEEP}
    return {
        "file": out_path.name,
        "rule": "JRC occurrence 1-89 % AND WorldCover in {40, 80, 90} AND not sea",
        "pixels": int(mask.sum()),
        "area_ha": round(float(mask.sum()) * PIXEL_HA, 1),
        "area_ha_by_worldcover_class": by_class,
        "grid": {"crs": str(profile["crs"]), "width": profile["width"], "height": profile["height"],
                 "transform": list(profile["transform"])[:6]},
    }


def load(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        return src.read(1).astype(bool), {"crs": src.crs, "transform": src.transform,
                                          "width": src.width, "height": src.height}
