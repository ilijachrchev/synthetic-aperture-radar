"""Rice-field mask on the shared 20 m site grid.

Built from the same sources as the ML rice labels (pipeline.ml.labels, PR #13):

    CORINE Land Cover 2018 class 213 (rice fields), keeping a pixel when it is
    at least 60 m inside a CORINE rice polygon (the ML rule) OR JRC saw it as
    seasonal water (occurrence 1 to 89 %), minus urban (WorldCover 50),
    permanent water (JRC >= 90 %: lagoon, canals) and the sea.

The 60 m shrink alone drops fields near polygon edges: only 23 of Luka's 50
hand-drawn rice fields lay fully inside it. Adding back edge pixels that JRC
saw flooded keeps 49 of 50 fully inside (the last at 97 %), while edge pixels
that never flood (paths, canals, field margins) stay out.

Why not JRC seasonal water (the first version): Luka checked it against
CORINE and 50 hand-drawn fields (review on PR #8). JRC is open water from 30 m
Landsat and misses shallow water under a rice canopy, so that mask held only
about two thirds of the rice (10,876 ha) and included about 400 ha of lagoon
edges. Flooded hectares would have been about a third too low.

Attribution: (c) European Union, Copernicus Land Monitoring Service 2018, EEA.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

from pipeline.config import DATA_DIR

CONTEXT_DIR = DATA_DIR / "context"
LABELS_DIR = DATA_DIR / "labels"
PIXEL_HA = 0.04  # 20 m x 20 m
CORINE_RICE = ("213",)
RICE_SHRINK_M = 60.0       # same as pipeline.ml.labels.RICE_SHRINK_M
WORLDCOVER_URBAN = 50
JRC_PERMANENT_MIN = 90     # percent of time water, 1984-2024; 255 is no data
RULE = ("CORINE 2018 class 213 AND (at least 60 m inside the polygon OR JRC occurrence 1-89 %), "
        "minus WorldCover urban (50), JRC permanent water (>= 90 %) and sea")


def corine_rice(clc: gpd.GeoDataFrame, crs, transform, shape: tuple[int, int],
                shrink_m: float = RICE_SHRINK_M) -> np.ndarray:
    """Pixels whose centre lies inside a shrunk CORINE rice polygon."""
    sel = clc[clc["Code_18"].astype(str).isin(CORINE_RICE)].to_crs(crs)
    geoms = [g for g in sel.geometry.buffer(-shrink_m) if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros(shape, bool)
    return rasterize(((g, 1) for g in geoms), out_shape=shape, transform=transform,
                     fill=0, dtype="uint8").astype(bool)


def rice_mask(rice: np.ndarray, rice_deep: np.ndarray, worldcover: np.ndarray, jrc: np.ndarray,
              sea: np.ndarray) -> np.ndarray:
    """Boolean rice-field mask from arrays on one grid.

    rice: inside a CORINE rice polygon; rice_deep: at least 60 m inside one.
    """
    if not (rice.shape == rice_deep.shape == worldcover.shape == jrc.shape == sea.shape):
        raise ValueError("Layers must share one grid")
    permanent = (jrc >= JRC_PERMANENT_MIN) & (jrc != 255)
    seasonal = (jrc >= 1) & (jrc < JRC_PERMANENT_MIN)
    return rice & (rice_deep | seasonal) & (worldcover != WORLDCOVER_URBAN) & ~permanent & (sea == 0)


def build(site_name: str, out_path: Path, context_dir: Path = CONTEXT_DIR, labels_dir: Path = LABELS_DIR) -> dict:
    """Write the mask as a uint8 GeoTIFF (1 rice, 0 other) and return its statistics."""
    paths = {k: context_dir / f"{site_name}_{k}_20m.tif" for k in ("worldcover_2021", "jrc_occurrence", "sea")}
    corine = labels_dir / f"{site_name}_clc2018.geojson"
    missing = [str(p) for p in [*paths.values(), corine] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing layers (python -m pipeline.context, python -m pipeline.ml.corine): {missing}")
    arrays, profile = {}, None
    for key, path in paths.items():
        with rasterio.open(path) as src:
            arrays[key] = src.read(1)
            if profile is None:
                profile = src.profile.copy()
            elif (src.transform, src.crs, src.shape) != (profile["transform"], profile["crs"], (profile["height"], profile["width"])):
                raise ValueError(f"{path.name} is not on the site grid")
    shape = (profile["height"], profile["width"])
    clc = gpd.read_file(corine)
    rice = corine_rice(clc, profile["crs"], profile["transform"], shape, shrink_m=0.0)
    deep = corine_rice(clc, profile["crs"], profile["transform"], shape)
    mask = rice_mask(rice, deep, arrays["worldcover_2021"], arrays["jrc_occurrence"], arrays["sea"])
    profile.update(dtype="uint8", count=1, nodata=None, compress="deflate")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mask.astype("uint8"), 1)
    return {
        "file": out_path.name,
        "rule": RULE,
        "sources": [corine.name, *(p.name for p in paths.values())],
        "attribution": "CORINE: (c) European Union, Copernicus Land Monitoring Service 2018, EEA",
        "pixels": int(mask.sum()),
        "area_ha": round(float(mask.sum()) * PIXEL_HA, 1),
        "corine_rice_ha": round(float(rice.sum()) * PIXEL_HA, 1),
        "corine_rice_deep_ha": round(float(deep.sum()) * PIXEL_HA, 1),
        "edge_never_water_dropped_ha": round(float((rice & ~deep & ~((arrays["jrc_occurrence"] >= 1)
                                                    & (arrays["jrc_occurrence"] < JRC_PERMANENT_MIN))).sum()) * PIXEL_HA, 1),
        "removed_ha": {
            "urban": round(float((rice & (arrays["worldcover_2021"] == WORLDCOVER_URBAN)).sum()) * PIXEL_HA, 1),
            "permanent_water": round(float((rice & (arrays["jrc_occurrence"] >= JRC_PERMANENT_MIN)
                                            & (arrays["jrc_occurrence"] != 255)).sum()) * PIXEL_HA, 1),
            "sea": round(float((rice & (arrays["sea"] == 1)).sum()) * PIXEL_HA, 1),
        },
        "grid": {"crs": str(profile["crs"]), "width": profile["width"], "height": profile["height"],
                 "transform": list(profile["transform"])[:6]},
    }


def load(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        return src.read(1).astype(bool), {"crs": src.crs, "transform": src.transform,
                                          "width": src.width, "height": src.height}
