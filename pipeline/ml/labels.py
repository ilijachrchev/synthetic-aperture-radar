"""Turn the label sources into one training-label raster on the stack grid.

Sources, lowest to highest priority (a later source overwrites an earlier one):

1. ESA WorldCover 2021      -> forest / urban / other_crops_shrub
2. JRC water occurrence     -> permanent_water where occurrence >= 90 %; water
   that JRC calls seasonal (1 to 89 %) is left unlabeled: it may be rice
3. EFFIS burnt area         -> burned
4. Hand-drawn polygons      -> any class, from a `class` column (GeoJSON or GeoPackage)

The sea is never a label: it would swamp the permanent-water class and it is
not part of the land story.

Defaults (default_sources) are the files the shared pipeline commits:
data/context/<site>_worldcover_2021_20m.tif, data/context/<site>_jrc_occurrence_20m.tif,
data/context/<site>_sea_20m.tif, data/labels/<site>_effis_burnt_area.geojson,
and our data/labels/<site>_drawn.geojson.

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
from pipeline.context import sea_mask as shared_sea_mask
from pipeline.stack import Grid

from . import config


def default_sources(site: str) -> dict[str, Path | None]:
    """The label files that exist for a site, None where there is none."""
    candidates = {
        "worldcover": config.CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif",
        "jrc_occurrence": config.CONTEXT_DIR / f"{site}_jrc_occurrence_20m.tif",
        "effis": config.LABELS_DIR / f"{site}_effis_burnt_area.geojson",
        "polygons": config.LABELS_DIR / f"{site}_drawn.geojson",
        "sea": config.CONTEXT_DIR / f"{site}_sea_20m.tif",
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


def sea_mask(worldcover: np.ndarray | None, jrc_occurrence: np.ndarray | None,
             edges: tuple[str, ...] = ("east",)) -> np.ndarray:
    """Sea computed from in-memory layers, with the shared rule in pipeline.context.

    Only a fallback: on the site grids the committed data/context/<site>_sea_20m.tif
    (same rule: thin canals cut so the Albufera lagoon stays inland) is read instead.
    """
    water = None
    if worldcover is not None:
        water = worldcover == config.WORLDCOVER_WATER
    if jrc_occurrence is not None:
        jrc_water = np.nan_to_num(jrc_occurrence, nan=0) >= config.JRC_PERMANENT_MIN
        water = jrc_water if water is None else (water | jrc_water)
    if water is None:
        raise ValueError("sea_mask needs WorldCover or JRC")
    return shared_sea_mask(water, edges)


def build_labels(
    grid: Grid,
    worldcover: str | Path | None = None,
    jrc_occurrence: str | Path | None = None,
    effis: str | Path | None = None,
    polygons: str | Path | None = None,
    sea: str | Path | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (labels int16 with UNLABELED, sea bool).

    sea: a 1 = sea raster (data/context/<site>_sea_20m.tif). Without it the sea
    is computed from WorldCover / JRC with the same shared rule.
    """
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

    if sea is not None:
        sea_px = read_on_grid(sea, grid, Resampling.nearest) == 1
    elif wc is not None or occ is not None:
        sea_px = sea_mask(wc, occ)
    else:
        sea_px = np.zeros(shape, bool)
    labels[sea_px] = config.UNLABELED
    return labels, sea_px


def label_counts(labels: np.ndarray) -> dict[str, int]:
    return {name: int((labels == i).sum()) for i, name in enumerate(config.CLASSES)}
