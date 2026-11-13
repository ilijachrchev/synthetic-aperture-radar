"""End-to-end check of the stack builder on a synthetic scene.

The same scene is written once on a UTM 30 grid and once on a UTM 31 grid (as
NISAR frames around Valencia can be), with a known water patch, an invalid
stripe (mask 0) and a fill margin (mask 255). The stack must put both dates on
one grid, keep the water patch in the same place and drop every invalid pixel.

Written with SI assistance (Claude Code).
"""

import json

import numpy as np
import rasterio
import xarray as xr
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from pipeline.config import Site
from pipeline.stack import build_stack, site_grid

SITE = Site("test", "synthetic", (-0.40, 39.30, -0.37, 39.33), "EPSG:32630", ("cv",))
LAND, WATER, HV = 0.1, 0.001, 0.02


def _scene_utm30():
    """A 20 m UTM 30 scene that covers the site with a margin."""
    grid = site_grid(SITE)
    pad = 10
    transform = from_origin(grid.transform.c - pad * 20, grid.transform.f + pad * 20, 20, 20)
    h, w = grid.height + 2 * pad, grid.width + 2 * pad
    hh = np.full((h, w), LAND, dtype="float32")
    hh[60:90, 50:80] = WATER                      # water patch
    mask = np.ones((h, w), dtype="uint8")
    mask[:, 120:123] = 0                          # partially focused stripe
    mask[:, :5] = 255                             # outside the radar footprint
    hh[mask == 255] = np.nan
    hv = np.full((h, w), HV, dtype="float32")
    hv[mask == 255] = np.nan
    looks = np.full((h, w), 12, dtype="float32")
    return transform, {"HHHH": hh, "HVHV": hv, "mask": mask, "numberOfLooks": looks}


def _write(day_dir, crs, transform, layers, stamp):
    day_dir.mkdir(parents=True)
    for name, arr in layers.items():
        nodata = 255 if name == "mask" else np.nan
        with rasterio.open(day_dir / f"{name}.tif", "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                           count=1, dtype=arr.dtype, crs=crs, transform=transform, nodata=nodata) as dst:
            dst.write(arr, 1)
    ur = f"NISAR_L2_PR_GCOV_033_066_D_069_2005_DHDH_M_{stamp}_{stamp}_P05023_N_F_J_001"
    (day_dir / "request.json").write_text(json.dumps({"granule_ur": ur, "crid": "P05023", "maturity": "PROVISIONAL",
                                                      "pols_a": ["HH", "HV"]}))


def _to_utm31(transform, layers):
    """Reproject the scene to a UTM 31 grid, as a second native frame."""
    from rasterio.warp import calculate_default_transform
    h, w = layers["HHHH"].shape
    left, top = transform.c, transform.f
    right, bottom = left + w * 20, top - h * 20
    t31, w31, h31 = calculate_default_transform("EPSG:32630", "EPSG:32631", w, h, left, bottom, right, top, resolution=20)
    out = {}
    for name, arr in layers.items():
        nearest = name == "mask"
        dst = np.full((h31, w31), 255 if nearest else np.nan, dtype=arr.dtype)
        reproject(arr, dst, src_transform=transform, src_crs="EPSG:32630", dst_transform=t31, dst_crs="EPSG:32631",
                  src_nodata=255 if nearest else np.nan, dst_nodata=255 if nearest else np.nan,
                  resampling=Resampling.nearest if nearest else Resampling.bilinear)
        out[name] = dst
    return t31, out


def test_two_native_zones_land_on_one_grid(tmp_path):
    raw = tmp_path / "raw"
    t30, layers = _scene_utm30()
    _write(raw / "test" / "000_D_000" / "20261016", "EPSG:32630", t30, layers, "20261016T185318")
    t31, layers31 = _to_utm31(t30, layers)
    _write(raw / "test" / "000_D_000" / "20261028", "EPSG:32631", t31, layers31, "20261028T185318")

    path = build_stack(SITE, "000_D_000", raw_root=raw, out_dir=tmp_path / "stack")
    ds = xr.open_dataset(path, engine="h5netcdf", decode_coords="all")
    grid = site_grid(SITE)
    assert ds.sizes == {"time": 2, "y": grid.height, "x": grid.width}
    assert ds["HH"].rio.crs.to_epsg() == 32630
    assert ds["HH"].rio.transform() == grid.transform
    assert list(ds["maturity"].values) == ["PROVISIONAL", "PROVISIONAL"]

    hh, valid = ds["HH"].values, ds["valid"].values.astype(bool)
    # Every valid pixel is finite and positive; every invalid one is NaN.
    assert np.all(np.isfinite(hh[valid])) and np.all(hh[valid] > 0)
    assert np.all(np.isnan(hh[~valid]))
    # Values survive the trip: land stays near 0.1, water near 0.001 (away from edges).
    for t in range(2):
        v = hh[t][valid[t]]
        assert np.median(v[v > 0.05]) == np.float32(LAND) or abs(np.median(v[v > 0.05]) - LAND) < 1e-3
        assert abs(np.median(v[v < 0.01]) - WATER) < 2e-4
    # The water patch sits in the same place on both dates (UTM 30 vs UTM 31 input).
    # The UTM 31 copy was resampled twice (by this test, then by the stack), which
    # blurs a one-pixel edge ring, so position is checked by centroid (< 0.5 px)
    # and overlap only loosely.
    water = (hh < 0.01) & valid
    c0 = np.argwhere(water[0]).mean(axis=0)
    c1 = np.argwhere(water[1]).mean(axis=0)
    assert np.all(np.abs(c0 - c1) < 0.5)
    both = valid[0] & valid[1]
    inter = np.sum(water[0] & water[1] & both)
    union = np.sum((water[0] | water[1]) & both)
    assert inter / union > 0.85
    # The invalid stripe (mask 0) is excluded on the first date.
    assert valid[0].sum() < valid[0].size
