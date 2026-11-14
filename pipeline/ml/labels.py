"""Turn the label sources into one training-label raster on the stack grid.

Sources, lowest to highest priority (a later source overwrites an earlier one):

1. ESA WorldCover 2021      -> forest / urban / other_crops_shrub. With CORINE,
   tree cover is split into orchard (CORINE 221-223) and forest (311-313) and
   left unlabeled elsewhere
2. JRC water occurrence     -> permanent_water where occurrence >= 90 %; water
   that JRC calls seasonal (1 to 89 %) is left unlabeled: it may be rice
3. CORINE 2018 rice (213), shrunk by 60 m -> rice_paddy, except on pixels
   already labelled urban or permanent water (villages, canals)
4. EFFIS burnt area         -> burned
5. Hand-drawn polygons      -> any class, from a `class` column (GeoJSON or GeoPackage)

The sea is never a label: it would swamp the permanent-water class and it is
not part of the land story.

Defaults (default_sources) are the files the shared pipeline commits:
data/context/<site>_worldcover_2021_20m.tif, data/context/<site>_jrc_occurrence_20m.tif,
data/context/<site>_sea_20m.tif, data/labels/<site>_effis_burnt_area.geojson,
and our data/labels/<site>_clc2018.geojson and data/labels/<site>_drawn.geojson.

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

ORCHARD_RULES = ("trees", "drop_conflict", "polygon")
ORCHARD_POLYGON_WC = (20, 30, 40)  # shrub, grass, crop: ground between orchard trees
RICE_SHRINK_M = 60.0  # CORINE rice polygons are shrunk so field edges, paths and canals drop out


def default_sources(site: str) -> dict[str, Path | None]:
    """The label files that exist for a site, None where there is none."""
    candidates = {
        "worldcover": config.CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif",
        "jrc_occurrence": config.CONTEXT_DIR / f"{site}_jrc_occurrence_20m.tif",
        "effis": config.LABELS_DIR / f"{site}_effis_burnt_area.geojson",
        "polygons": config.LABELS_DIR / f"{site}_drawn.geojson",
        "sea": config.CONTEXT_DIR / f"{site}_sea_20m.tif",
        "corine": config.LABELS_DIR / f"{site}_clc2018.geojson",
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


def corine_mask(clc: gpd.GeoDataFrame, grid: Grid, codes: tuple[str, ...], shrink_m: float = 0.0) -> np.ndarray:
    """Pixels whose centre lies inside CORINE polygons with one of the codes."""
    sel = clc[clc["Code_18"].astype(str).isin(codes)].to_crs(grid.crs)
    geoms = sel.geometry.buffer(-shrink_m) if shrink_m else sel.geometry
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros((grid.height, grid.width), bool)
    return rasterize(((g, 1) for g in geoms), out_shape=(grid.height, grid.width),
                     transform=grid.transform, fill=0, dtype="uint8").astype(bool)


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
    corine: str | Path | None = None,
    orchard_shrink_m: float = 0.0,
    forest_shrink_m: float = 0.0,
    orchard_rule: str = "trees",
) -> tuple[np.ndarray, np.ndarray]:
    """Return (labels int16 with UNLABELED, sea bool).

    sea: a 1 = sea raster (data/context/<site>_sea_20m.tif). Without it the sea
    is computed from WorldCover / JRC with the same shared rule.
    corine: CORINE 2018 polygons with a Code_18 column (pipeline.ml.corine).
    orchard_shrink_m, forest_shrink_m: shrink the CORINE orchard / forest polygons
    first (like rice), so 100 m scale edges drop out of the labels.
    orchard_rule (only with CORINE): which pixels inside CORINE orchard polygons
    are labelled. "trees" (default): WorldCover trees -> orchard, the rest keeps
    its WorldCover class (mostly grassland / cropland -> other_crops_shrub, 57 %
    of all other_crops labels at Albufera lie in orchard polygons).
    "drop_conflict": as "trees", but non-tree pixels inside orchard polygons are
    left unlabeled. "polygon": every pixel of an orchard polygon that WorldCover
    calls trees, shrub, grass or crop -> orchard.
    """
    if orchard_rule not in ORCHARD_RULES:
        raise ValueError(f"orchard_rule must be one of {ORCHARD_RULES}")
    shape = (grid.height, grid.width)
    labels = np.full(shape, config.UNLABELED, dtype=np.int16)
    wc = occ = None
    clc = gpd.read_file(corine) if corine is not None else None

    if worldcover is not None:
        # Mode keeps the majority class inside each 20 m pixel if resampling is needed.
        wc = read_on_grid(worldcover, grid, Resampling.mode)
        for code, name in config.WORLDCOVER_TO_CLASS.items():
            labels[wc == code] = config.CLASS_INDEX[name]
        if clc is not None:
            trees = wc == config.WORLDCOVER_TREE
            labels[trees] = config.UNLABELED
            labels[trees & corine_mask(clc, grid, config.CORINE_ORCHARD, orchard_shrink_m)] = config.CLASS_INDEX["orchard"]
            labels[trees & corine_mask(clc, grid, config.CORINE_FOREST, forest_shrink_m)] = config.CLASS_INDEX["forest"]
            if orchard_rule != "trees":
                in_orch = corine_mask(clc, grid, config.CORINE_ORCHARD, orchard_shrink_m)
                farm = np.isin(wc, list(ORCHARD_POLYGON_WC)) & in_orch
                labels[farm & ~trees] = (config.UNLABELED if orchard_rule == "drop_conflict"
                                         else config.CLASS_INDEX["orchard"])

    if jrc_occurrence is not None:
        occ = read_on_grid(jrc_occurrence, grid, Resampling.average)
        permanent = occ >= config.JRC_PERMANENT_MIN       # NaN (no data) compares False
        seasonal = (occ > 0) & ~permanent
        labels[seasonal] = config.UNLABELED
        labels[permanent] = config.CLASS_INDEX["permanent_water"]

    if clc is not None:
        rice = corine_mask(clc, grid, config.CORINE_RICE, shrink_m=RICE_SHRINK_M)
        keep = np.isin(labels, [config.CLASS_INDEX["urban"], config.CLASS_INDEX["permanent_water"]])
        labels[rice & ~keep] = config.CLASS_INDEX["rice_paddy"]

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
