"""Turn the label sources into one training-label raster on the stack grid.

Sources, lowest to highest priority (a later source overwrites an earlier one):

1. ESA WorldCover 2021      -> forest / urban / other_crops_shrub
2. JRC water occurrence     -> permanent_water where occurrence >= 90 %; water
   that JRC calls seasonal (1 to 89 %) is left unlabeled: it may be rice
3. EFFIS burnt area         -> burned
4. Hand-drawn polygons      -> any class, from a `class` column (GeoJSON or GeoPackage)

The sea is found separately (sea_mask) and is never a label: it would swamp the
permanent-water class and it is not part of the land story.

Defaults (default_sources) are the files Ilija's pipeline commits:
data/context/<site>_worldcover_2021_20m.tif, data/context/<site>_jrc_occurrence_20m.tif,
data/labels/<site>_effis_burnt_area.geojson and our data/labels/<site>_drawn.geojson.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject
from scipy.ndimage import binary_dilation, binary_erosion
from scipy.ndimage import label as connected_components

from pipeline.stack import Grid

from . import config

SEA_CUT_PX = 2  # canals narrower than about 2 x 2 x 20 m = 80 m are cut when finding the sea


def default_sources(site: str) -> dict[str, Path | None]:
    """The label files that exist for a site, None where there is none."""
    candidates = {
        "worldcover": config.CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif",
        "jrc_occurrence": config.CONTEXT_DIR / f"{site}_jrc_occurrence_20m.tif",
        "effis": config.LABELS_DIR / f"{site}_effis_burnt_area.geojson",
        "polygons": config.LABELS_DIR / f"{site}_drawn.geojson",
    }
    return {k: (p if p.exists() else None) for k, p in candidates.items()}


def read_on_grid(path: str | Path, grid: Grid, resampling: Resampling) -> np.ndarray:
    """Band 1 on the grid as float32, NaN where the source has no data.

    The committed context rasters already sit on the site grid, so this is a
    plain read for them; any other raster is resampled.
    """
    out = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_nodata=src.nodata,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            dst_nodata=np.nan,
            resampling=resampling,
        )
    return out


def rasterize_polygons(path: str | Path, grid: Grid, class_name: str | None = None) -> np.ndarray:
    """Burn polygons into an int16 raster of class indices (UNLABELED elsewhere).

    With class_name every polygon gets that class; otherwise each polygon's
    `class` column names it (one of config.CLASSES).
    """
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].to_crs(grid.crs)
    if class_name is None and "class" not in gdf.columns:
        raise ValueError(f"{path}: needs a `class` column naming each polygon's class")
    shapes = []
    for i, geom in enumerate(gdf.geometry):
        name = class_name or str(gdf["class"].iloc[i]).strip()
        if name not in config.CLASS_INDEX:
            raise ValueError(f"{path}: polygon {i} has class {name!r}; use one of {config.CLASSES}")
        shapes.append((geom, config.CLASS_INDEX[name]))
    if not shapes:
        return np.full((grid.height, grid.width), config.UNLABELED, dtype=np.int16)
    return rasterize(shapes, out_shape=(grid.height, grid.width), transform=grid.transform,
                     fill=config.UNLABELED, dtype="int16")


def sea_mask(worldcover: np.ndarray | None, jrc_occurrence: np.ndarray | None) -> np.ndarray:
    """Open water connected to the east edge of the grid.

    Both Valencian sites have the Mediterranean on their east side, so "water
    touching the east edge" is the sea (plus harbours joined to it). The Albufera
    lagoon reaches the sea through canals one or two pixels wide, so the water is
    first shrunk by SEA_CUT_PX pixels (cutting the canals), the east-edge parts are
    taken, and they are grown back by the same amount inside the original water.
    On the committed grids this gives about 28 % sea at Albufera with the
    2,478 ha lagoon kept whole, and 1.8 % at Espadà.
    """
    water = None
    if worldcover is not None:
        water = worldcover == config.WORLDCOVER_WATER
    if jrc_occurrence is not None:
        jrc_water = np.nan_to_num(jrc_occurrence, nan=0) >= config.JRC_PERMANENT_MIN
        water = jrc_water if water is None else (water | jrc_water)
    if water is None:
        raise ValueError("sea_mask needs WorldCover or JRC")
    # border_value=1: the area past the grid edge counts as water, so the shrink
    # does not peel the sea away from the east edge.
    core = binary_erosion(water, iterations=SEA_CUT_PX, border_value=1)
    comps, _ = connected_components(core)
    east = np.unique(comps[:, -1])
    east = east[east > 0]
    return binary_dilation(np.isin(comps, east), iterations=SEA_CUT_PX) & water


def build_labels(
    grid: Grid,
    worldcover: str | Path | None = None,
    jrc_occurrence: str | Path | None = None,
    effis: str | Path | None = None,
    polygons: str | Path | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (labels int16 with UNLABELED, sea bool)."""
    shape = (grid.height, grid.width)
    labels = np.full(shape, config.UNLABELED, dtype=np.int16)
    wc = occ = None

    if worldcover is not None:
        # Mode keeps the majority class inside each 20 m pixel if resampling is needed.
        wc = read_on_grid(worldcover, grid, Resampling.mode)
        for code, name in config.WORLDCOVER_TO_CLASS.items():
            labels[wc == code] = config.CLASS_INDEX[name]

    if jrc_occurrence is not None:
        occ = read_on_grid(jrc_occurrence, grid, Resampling.average)
        permanent = occ >= config.JRC_PERMANENT_MIN       # NaN (no data) compares False
        seasonal = (occ > 0) & ~permanent
        labels[seasonal] = config.UNLABELED
        labels[permanent] = config.CLASS_INDEX["permanent_water"]

    if effis is not None:
        burned = rasterize_polygons(effis, grid, class_name="burned")
        labels[burned != config.UNLABELED] = config.CLASS_INDEX["burned"]

    if polygons is not None:
        drawn = rasterize_polygons(polygons, grid)
        labels[drawn != config.UNLABELED] = drawn[drawn != config.UNLABELED]

    sea = sea_mask(wc, occ) if (wc is not None or occ is not None) else np.zeros(shape, bool)
    labels[sea] = config.UNLABELED
    return labels, sea


def label_counts(labels: np.ndarray) -> dict[str, int]:
    return {name: int((labels == i).sum()) for i, name in enumerate(config.CLASSES)}
