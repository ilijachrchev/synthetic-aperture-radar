"""Checks for putting labels on the stack grid. Written with SI assistance (Claude Code)."""

import geopandas as gpd
import numpy as np
import rasterio
import rioxarray  # noqa: F401
import xarray as xr
from rasterio.transform import from_origin
from shapely.geometry import box

from pipeline.cv.data import DSWX_FILL, dswx_on_grid, rasterize_on

X0, Y0, PX = 720000.0, 4360000.0, 20.0  # a UTM 30 corner near Valencia


def _stack(ny=50, nx=60):
    transform = from_origin(X0, Y0, PX, PX)
    ds = xr.Dataset(
        {"HH": (("y", "x"), np.zeros((ny, nx), "float32"))},
        coords={"y": Y0 - (np.arange(ny) + 0.5) * PX, "x": X0 + (np.arange(nx) + 0.5) * PX},
    )
    return ds.rio.write_crs("EPSG:32630").rio.write_transform(transform)


def test_rasterize_polygon_lands_on_expected_pixels():
    ds = _stack()
    # A polygon covering columns 10..19 and rows 5..14 exactly.
    poly = box(X0 + 10 * PX, Y0 - 15 * PX, X0 + 20 * PX, Y0 - 5 * PX)
    gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:32630").to_crs(4326)  # labels arrive in WGS84
    out = rasterize_on(ds, gdf)
    assert out.sum() == 100
    assert out[5:15, 10:20].all()


def _write_tile(path, crs, transform, arr):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="uint8", crs=crs, transform=transform, nodata=DSWX_FILL) as dst:
        dst.write(arr, 1)


def test_dswx_mosaic_first_valid_wins_and_fill_stays(tmp_path):
    ds = _stack()
    # Tile A (UTM 30, 30 m): open water (1) on the left half of the stack, fill elsewhere.
    a = np.full((40, 40), DSWX_FILL, "uint8")
    a[:, :20] = 1
    _write_tile(tmp_path / "a.tif", "EPSG:32630", from_origin(X0, Y0, 30, 30), a)
    # Tile B: not water (0) everywhere; it should only fill where A has no data.
    b = np.zeros((40, 40), "uint8")
    _write_tile(tmp_path / "b.tif", "EPSG:32630", from_origin(X0, Y0, 30, 30), b)
    out = dswx_on_grid(ds, [tmp_path / "a.tif", tmp_path / "b.tif"])
    assert out[:, :25].max() == 1 and set(np.unique(out[:, :25])) == {1}   # A wins (its 600 m = 30 px)
    assert set(np.unique(out[:, 35:])) == {0}                              # B fills the rest
    # With only tile A, the right side stays fill.
    only_a = dswx_on_grid(ds, [tmp_path / "a.tif"])
    assert set(np.unique(only_a[:, 35:])) == {DSWX_FILL}
