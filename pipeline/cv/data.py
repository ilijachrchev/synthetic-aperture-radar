"""Load the shared stack and put labels on its grid.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from scipy.ndimage import uniform_filter

DSWX_FILL = 255


def open_stack(path: str | Path) -> xr.Dataset:
    """Load a stack written by pipeline.stack into memory, keeping its CRS and transform.

    Loaded eagerly (a stack is tens of MB) so the file is closed right away and
    can be rebuilt while a notebook still holds the data.
    """
    return xr.load_dataset(path, engine="h5netcdf", decode_coords="all")


def to_db(power: np.ndarray) -> np.ndarray:
    """Linear power to dB (10*log10); NaN where power is not positive or missing."""
    out = np.full(power.shape, np.nan, dtype="float32")
    ok = np.isfinite(power) & (power > 0)
    out[ok] = 10.0 * np.log10(power[ok])
    return out


def boxcar_power(power: np.ndarray, valid: np.ndarray, size: int = 5, min_share: float = 0.5) -> np.ndarray:
    """Speckle filter: mean of valid pixels in a size x size window, in linear power.

    Invalid pixels never leak into their neighbours (normalized convolution).
    Output is NaN where fewer than min_share of the window was valid, or where
    the centre pixel itself is not valid.
    """
    valid = valid.astype(bool) & np.isfinite(power)
    num = uniform_filter(np.where(valid, power, 0.0).astype("float64"), size=size, mode="constant")
    den = uniform_filter(valid.astype("float64"), size=size, mode="constant")
    out = np.full(power.shape, np.nan, dtype="float32")
    ok = valid & (den >= min_share)
    out[ok] = (num[ok] / den[ok]).astype("float32")
    return out


def grid_of(ds: xr.Dataset) -> tuple[str, rasterio.Affine, tuple[int, int]]:
    """CRS, transform and (rows, cols) of a stack."""
    return ds["HH"].rio.crs.to_string(), ds["HH"].rio.transform(), (ds.sizes["y"], ds.sizes["x"])


def rasterize_on(ds: xr.Dataset, gdf: gpd.GeoDataFrame, all_touched: bool = False) -> np.ndarray:
    """Burn polygons onto the stack grid: 1 inside, 0 outside."""
    crs, transform, shape = grid_of(ds)
    geoms = [g for g in gdf.to_crs(crs).geometry if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros(shape, dtype="uint8")
    return rasterize(((g, 1) for g in geoms), out_shape=shape, transform=transform, fill=0,
                     dtype="uint8", all_touched=all_touched)


def dswx_on_grid(ds: xr.Dataset, tile_paths: list[str | Path]) -> np.ndarray:
    """DSWx-S1 B01_WTR tiles of one pass mosaicked onto the stack grid (nearest).

    Tiles can sit in different UTM zones; the first valid (non-fill) value wins
    where they overlap. Fill (255) remains where no tile has data.
    """
    crs, transform, shape = grid_of(ds)
    out = np.full(shape, DSWX_FILL, dtype="uint8")
    for path in tile_paths:
        with rasterio.open(path) as src:
            tile = np.full(shape, DSWX_FILL, dtype="uint8")
            reproject(rasterio.band(src, 1), tile, src_nodata=src.nodata if src.nodata is not None else DSWX_FILL,
                      dst_transform=transform, dst_crs=crs, dst_nodata=DSWX_FILL, resampling=Resampling.nearest)
        take = (out == DSWX_FILL) & (tile != DSWX_FILL)
        out[take] = tile[take]
    return out
