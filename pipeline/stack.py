"""Build the shared NISAR stack for one site and stack id (read by CV and ML).

Reads data/raw/nisar/<site>/<stack>/<YYYYMMDD>/{HHHH,HVHV,mask,numberOfLooks}.tif
(each granule in its native grid, UTM 30 or 31) and reprojects every date once
onto the site grid: the site CRS with 20 m pixels snapped to the 20 m lattice.

Writes data/stack/<site>_<stack>.nc with dims (time, y, x):
    HH, HV   gamma0 in linear power, float32, NaN where not valid
    valid    1 where the pixel is usable, else 0
    looks    number of looks, float32
    per date: granule_ur, crid, maturity, pols

A pixel is valid only if the GCOV mask is 1 to 5 (fully focused; 0 means
partially focused or invalid, 255 is fill; GCOV spec JPL D-102274 Rev F), its HH
is finite and positive, and every source pixel that fed the bilinear resampling
was valid. inputDataExceptionMask is not offered by Harmony, so it is not used.
Power is resampled bilinearly in linear units; the mask with nearest neighbour.

Usage:
    python -m pipeline.stack --site albufera --stack 066_D_069

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
import rioxarray  # noqa: F401  (registers the .rio accessor used to write the CRS)
import xarray as xr
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from pipeline.config import PIXEL_SIZE_M, RAW_DIR, STACK_DIR, Site, get_site

POWER_LAYERS = ("HHHH", "HVHV")
MASK_VALID = range(1, 6)  # subswath numbers of fully focused samples
FULL_SUPPORT = 0.999      # share of valid source pixels required under the bilinear kernel


@dataclass(frozen=True)
class Grid:
    crs: str
    transform: Affine
    width: int
    height: int

    @property
    def x(self) -> np.ndarray:
        return self.transform.c + (np.arange(self.width) + 0.5) * self.transform.a

    @property
    def y(self) -> np.ndarray:
        return self.transform.f + (np.arange(self.height) + 0.5) * self.transform.e


def site_grid(site: Site, pixel: float = PIXEL_SIZE_M) -> Grid:
    """Site bbox in the site CRS, snapped outward to the pixel lattice."""
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", site.crs, *site.bbox, densify_pts=21)
    xmin, ymin = math.floor(xmin / pixel) * pixel, math.floor(ymin / pixel) * pixel
    xmax, ymax = math.ceil(xmax / pixel) * pixel, math.ceil(ymax / pixel) * pixel
    return Grid(site.crs, from_origin(xmin, ymax, pixel, pixel), int(round((xmax - xmin) / pixel)), int(round((ymax - ymin) / pixel)))


def _warp(src_path: Path, grid: Grid, resampling: Resampling, dst_fill: float, dtype: str) -> np.ndarray:
    with rasterio.open(src_path) as src:
        dst = np.full((grid.height, grid.width), dst_fill, dtype=dtype)
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_nodata=src.nodata, dst_transform=grid.transform, dst_crs=grid.crs,
            dst_nodata=dst_fill, resampling=resampling,
        )
    return dst


def _support(src_path: Path, mask_path: Path, grid: Grid) -> np.ndarray:
    """Share of valid source pixels under the bilinear kernel, per output pixel."""
    with rasterio.open(src_path) as src, rasterio.open(mask_path) as msk:
        power = src.read(1)
        mask = msk.read(1)
        ok = (np.isfinite(power) & (power > 0) & np.isin(mask, list(MASK_VALID))).astype("float32")
        dst = np.zeros((grid.height, grid.width), dtype="float32")
        reproject(
            source=ok, destination=dst, src_transform=src.transform, src_crs=src.crs,
            dst_transform=grid.transform, dst_crs=grid.crs, resampling=Resampling.bilinear,
        )
    return dst


def load_date(day_dir: Path, grid: Grid) -> dict[str, np.ndarray]:
    """One acquisition on the site grid: HH, HV (NaN if absent), looks and validity."""
    out: dict[str, np.ndarray] = {}
    for layer in POWER_LAYERS:
        path = day_dir / f"{layer}.tif"
        out[layer] = (_warp(path, grid, Resampling.bilinear, np.nan, "float32") if path.exists()
                      else np.full((grid.height, grid.width), np.nan, dtype="float32"))
    looks = day_dir / "numberOfLooks.tif"
    out["looks"] = (_warp(looks, grid, Resampling.bilinear, np.nan, "float32") if looks.exists()
                    else np.full((grid.height, grid.width), np.nan, dtype="float32"))
    mask = _warp(day_dir / "mask.tif", grid, Resampling.nearest, 255, "uint8")
    support = _support(day_dir / "HHHH.tif", day_dir / "mask.tif", grid)
    hh = out["HHHH"]
    valid = np.isin(mask, list(MASK_VALID)) & np.isfinite(hh) & (hh > 0) & (support >= FULL_SUPPORT)
    out["valid"] = valid.astype("uint8")
    for layer in POWER_LAYERS:
        out[layer][~valid] = np.nan
    return out


def build_stack(site: Site, stack_id: str, raw_root: Path = RAW_DIR / "nisar", out_dir: Path = STACK_DIR) -> Path:
    stack_dir = raw_root / site.name / stack_id
    day_dirs = sorted(d for d in stack_dir.iterdir() if (d / "request.json").exists()) if stack_dir.exists() else []
    if not day_dirs:
        raise FileNotFoundError(f"no fetched dates in {stack_dir}: run python -m pipeline.nisar_fetch first")
    grid = site_grid(site)

    layers = {"HH": [], "HV": [], "valid": [], "looks": []}
    times, meta = [], {"granule_ur": [], "crid": [], "maturity": [], "pols": []}
    for d in day_dirs:
        req = json.loads((d / "request.json").read_text(encoding="utf-8"))
        data = load_date(d, grid)
        layers["HH"].append(data["HHHH"])
        layers["HV"].append(data["HVHV"])
        layers["valid"].append(data["valid"])
        layers["looks"].append(data["looks"])
        stamp = re.search(r"_(\d{8}T\d{6})_", req["granule_ur"]).group(1)  # acquisition start
        times.append(np.datetime64(datetime.strptime(stamp, "%Y%m%dT%H%M%S")))
        meta["granule_ur"].append(req["granule_ur"])
        meta["crid"].append(req.get("crid") or "")
        meta["maturity"].append(req.get("maturity") or "")
        meta["pols"].append("+".join(req.get("pols_a") or []))

    dims = ("time", "y", "x")
    ds = xr.Dataset(
        {name: (dims, np.stack(arrs)) for name, arrs in layers.items()}
        | {name: (("time",), np.array(vals)) for name, vals in meta.items()},
        coords={"time": np.array(times), "y": grid.y, "x": grid.x},
        attrs={
            "site": site.name, "stack_id": stack_id, "pixel_size_m": PIXEL_SIZE_M,
            "power_units": "gamma0, linear power", "valid_rule": "GCOV mask 1..5, HH finite and > 0, full bilinear support",
            "source": "NISAR L2 GCOV via Harmony (ASF DAAC)",
            "note": "Written with SI assistance (Claude Code)",
        },
    )
    ds = ds.rio.write_crs(site.crs).rio.write_transform(grid.transform)
    ds["HH"].attrs.update(long_name="gamma0 HH, linear power", units="1")
    ds["HV"].attrs.update(long_name="gamma0 HV, linear power", units="1")
    ds["valid"].attrs.update(long_name="usable pixel (1) or not (0)")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{site.name}_{stack_id}.nc"
    # Merge compression into each variable's existing encoding: rioxarray keeps the
    # CRS link (grid_mapping) there, and replacing it would drop the CRS on disk.
    encoding = {v: {**ds[v].encoding, "compression": "gzip", "compression_opts": 4} for v in ("HH", "HV", "valid", "looks")}
    ds.to_netcdf(path, engine="h5netcdf", encoding=encoding)
    share = float(np.mean(np.stack(layers["valid"])))
    print(f"{site.name} {stack_id}: {len(day_dirs)} dates on a {grid.width} x {grid.height} grid "
          f"({grid.crs}, {PIXEL_SIZE_M:g} m), {share:.1%} valid -> {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True)
    parser.add_argument("--stack", required=True)
    args = parser.parse_args()
    build_stack(get_site(args.site), args.stack)


if __name__ == "__main__":
    main()
