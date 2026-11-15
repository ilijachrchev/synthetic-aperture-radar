"""Height above drainage (ASF GLO-30 HAND), elevation (Copernicus GLO-30) and slope on the site grid.

Both sources are 30 m public COGs on AWS, no account needed. Putting them on the
20 m grid aligns them with the other layers; it adds no terrain detail.
HAND: https://registry.opendata.aws/glo-30-hand/ (ASF, from Copernicus DEM GLO-30).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject

from pipeline.config import DATA_DIR, RAW_DIR, PIXEL_SIZE_M, Site
from pipeline.stack import Grid

SOURCES = {
    "hand": "https://glo-30-hand.s3.us-west-2.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_{t}_HAND.tif",
    "dem": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{t}_DEM/Copernicus_DSM_COG_10_{t}_DEM.tif",
}
INTERIM = DATA_DIR / "interim" / "spatial"   # rebuildable, not committed (data/interim is git-ignored)


def tile_names(bbox: tuple[float, float, float, float]) -> list[str]:
    """1-degree tile names (``N39_00_W001_00``) touching a (west, south, east, north) box."""
    w, s, e, n = bbox
    out = []
    for lat in range(math.floor(s), math.floor(n) + 1):
        for lon in range(math.floor(w), math.floor(e) + 1):
            ns = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00"
            ew = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00"
            out.append(f"{ns}_{ew}")
    return out


def fetch(kind: str, tile: str, raw_dir: Path = RAW_DIR) -> Path | None:
    """Download one tile once; None where the source has no tile (open sea)."""
    path = raw_dir / kind / f"{tile}.tif"
    if path.exists():
        return path
    resp = requests.get(SOURCES[kind].format(t=tile), timeout=300)
    if resp.status_code in (403, 404):
        return None
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(resp.content)
    tmp.replace(path)
    return path


def on_grid(paths: list[Path], grid: Grid) -> np.ndarray:
    """Bilinear mosaic of the tiles on the grid, NaN where no tile has data."""
    out = np.full((grid.height, grid.width), np.nan, dtype="float32")
    for path in paths:
        tile = np.full_like(out, np.nan)
        with rasterio.open(path) as src:
            reproject(source=rasterio.band(src, 1), destination=tile, src_nodata=src.nodata,
                      dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
        take = np.isnan(out) & np.isfinite(tile)
        out[take] = tile[take]
    return out


def slope_deg(elevation: np.ndarray, pixel_m: float = PIXEL_SIZE_M) -> np.ndarray:
    dy, dx = np.gradient(elevation.astype("float64"), pixel_m)
    return np.degrees(np.arctan(np.hypot(dx, dy))).astype("float32")


def write(array: np.ndarray, grid: Grid, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="float32",
                       crs=grid.crs, transform=grid.transform, nodata=np.nan, compress="deflate", tiled=True) as dst:
        dst.write(array.astype("float32"), 1)


def static_dir(site: str) -> Path:
    return INTERIM / site


def prepare(site: Site, grid: Grid) -> dict:
    """Fetch and write hand_m.tif, elevation_m.tif and slope_deg.tif for one site."""
    tiles = tile_names(site.bbox)
    out = {}
    layers = {}
    for kind, name in (("hand", "hand_m"), ("dem", "elevation_m")):
        paths = [p for p in (fetch(kind, t) for t in tiles) if p is not None]
        if not paths:
            raise RuntimeError(f"No {kind} tile for {site.name}")
        layers[name] = on_grid(paths, grid)
        out[name] = {"tiles": [p.stem for p in paths], "source": SOURCES[kind]}
    layers["slope_deg"] = slope_deg(layers["elevation_m"])
    for name, arr in layers.items():
        write(arr, grid, static_dir(site.name) / f"{name}.tif")
        out.setdefault(name, {})["valid_share"] = round(float(np.isfinite(arr).mean()), 4)
    return out
