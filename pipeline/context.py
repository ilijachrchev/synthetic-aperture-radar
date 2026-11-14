"""Helper data around the NISAR scenes (public sources, no login).

Rasters are clipped around each site's stack grid and saved under
data/raw/context/ (not committed; rerun this module to rebuild them), then
resampled onto the exact 20 m stack grid of the site and saved to data/context/
(committed, small): <site>_worldcover_2021_20m.tif (mode resampling, class codes
kept), <site>_jrc_occurrence_20m.tif (bilinear, percent) and <site>_sea_20m.tif
(permanent water connected to the sea edge, 1 sea, 0 not sea). Small tables go to
data/context/ too.

- ESA WorldCover 2021 v200 land cover, 10 m (CC BY 4.0), for CV and ML.
- JRC Global Surface Water v1.5 occurrence 1984 to 2024, 30 m: how often
  each pixel was water (0 to 100 %), for ML (permanent vs seasonal water).
- GNSS station LOR1 (Nevada Geodetic Laboratory) daily vertical position,
  for the Lorca forecast.
- USGS record of the Panama M7.7 earthquake.

Only the site windows are read from the remote Cloud-Optimized GeoTIFFs,
never whole tiles.

Usage:
    python -m pipeline.context

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
import requests
from scipy import ndimage
from rasterio import Env as GDALConfig
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject, transform_bounds

from pipeline.config import DATA_DIR, PIXEL_SIZE_M, RAW_DIR, SITES, Site
from pipeline.stack import site_grid

CONTEXT_RAW = RAW_DIR / "context"
CONTEXT_DIR = DATA_DIR / "context"
TIMEOUT_S = 180

WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
JRC_OCCURRENCE_URL = "https://storage.googleapis.com/water-world/download2024/VER1-5/occurrence/occurrence_{tile}_v1_5_2024.tif"
LOR1_URL = "https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/EU/LOR1.EU.tenv3"
PANAMA_USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us6000u18k&format=geojson"

# Read only what we need from remote GeoTIFFs: no directory listings, keep requests to .tif.
REMOTE_READ = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif"}


def worldcover_tiles(bbox: tuple[float, float, float, float]) -> list[str]:
    """WorldCover 3 x 3 degree tile names (named by south-west corner) covering bbox."""
    west, south, east, north = bbox
    names = []
    for lat in range(math.floor(south / 3) * 3, math.ceil(north / 3) * 3, 3):
        for lon in range(math.floor(west / 3) * 3, math.ceil(east / 3) * 3, 3):
            ns = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
            ew = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
            names.append(ns + ew)
    return names


def jrc_tiles(bbox: tuple[float, float, float, float]) -> list[str]:
    """JRC GSW 10 x 10 degree tile names (west edge, north edge) covering bbox."""
    west, south, east, north = bbox
    names = []
    for top in range(math.floor(south / 10) * 10 + 10, math.ceil(north / 10) * 10 + 1, 10):
        for left in range(math.floor(west / 10) * 10, math.ceil(east / 10) * 10, 10):
            ew = f"{abs(left)}{'E' if left >= 0 else 'W'}"
            ns = f"{abs(top)}{'N' if top >= 0 else 'S'}"
            names.append(f"{ew}_{ns}")
    return names


def clip_remote(urls: list[str], bbox: tuple[float, float, float, float], out_path: Path) -> Path:
    """Mosaic and clip remote COG tiles to bbox, reading only the needed windows."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with GDALConfig(**REMOTE_READ):
        sources = [rasterio.open(f"/vsicurl/{u}") for u in urls]
        try:
            data, transform = merge(sources, bounds=bbox)
            profile = sources[0].profile.copy()
        finally:
            for src in sources:
                src.close()
    profile.update(
        driver="GTiff", height=data.shape[1], width=data.shape[2], transform=transform,
        compress="deflate", tiled=True, blockxsize=512, blockysize=512,
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data)
    return out_path


def grid_bbox_wgs84(site: Site, margin_deg: float = 0.005) -> tuple[float, float, float, float]:
    """WGS84 box that contains the site's whole stack grid, plus a small margin.

    The stack grid is snapped outward in UTM, so its corners reach a little past
    the site box; clipping helper data to this box leaves no empty edges.
    """
    g = site_grid(site)
    left, top = g.transform.c, g.transform.f
    right, bottom = left + g.width * PIXEL_SIZE_M, top - g.height * PIXEL_SIZE_M
    w, s, e, n = transform_bounds(site.crs, "EPSG:4326", left, bottom, right, top, densify_pts=21)
    return (w - margin_deg, s - margin_deg, e + margin_deg, n + margin_deg)


def fetch_rasters(site: Site) -> None:
    bbox = grid_bbox_wgs84(site)
    wc = [WORLDCOVER_URL.format(tile=t) for t in worldcover_tiles(bbox)]
    path = clip_remote(wc, bbox, CONTEXT_RAW / f"{site.name}_worldcover_2021.tif")
    print(f"{site.name}: WorldCover from {len(wc)} tile(s) -> {path.relative_to(DATA_DIR.parent)}")
    jrc = [JRC_OCCURRENCE_URL.format(tile=t) for t in jrc_tiles(bbox)]
    path = clip_remote(jrc, bbox, CONTEXT_RAW / f"{site.name}_jrc_occurrence_v1_5.tif")
    print(f"{site.name}: JRC occurrence from {len(jrc)} tile(s) -> {path.relative_to(DATA_DIR.parent)}")


def warp_to_grid(src_path: Path, site: Site, resampling: Resampling, nodata: int) -> np.ndarray:
    """One raw helper raster resampled onto the site's stack grid (uint8, nodata where uncovered)."""
    grid = site_grid(site)
    out = np.full((grid.height, grid.width), nodata, dtype="float32")
    with rasterio.open(src_path) as src:
        reproject(
            source=rasterio.band(src, 1), destination=out,
            src_nodata=src.nodata if src.nodata is not None else nodata,
            dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=nodata, resampling=resampling,
        )
    return np.clip(np.rint(out), 0, 255).astype("uint8")


def context_on_grid(site: Site) -> list[Path]:
    """WorldCover and JRC occurrence on the exact 20 m stack grid of the site (committed files)."""
    grid = site_grid(site)
    layers = [
        # raw clip, output, resampling, nodata: WorldCover codes stay codes (0 is its no-data),
        # JRC occurrence stays 0..100 % (255 is its no-data)
        (f"{site.name}_worldcover_2021.tif", f"{site.name}_worldcover_2021_20m.tif", Resampling.mode, 0),
        (f"{site.name}_jrc_occurrence_v1_5.tif", f"{site.name}_jrc_occurrence_20m.tif", Resampling.bilinear, 255),
    ]
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for raw, out_name, resampling, nodata in layers:
        data = warp_to_grid(CONTEXT_RAW / raw, site, resampling, nodata)
        path = CONTEXT_DIR / out_name
        with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=1,
                           dtype="uint8", crs=grid.crs, transform=grid.transform, nodata=nodata,
                           compress="deflate", tiled=True, blockxsize=512, blockysize=512) as dst:
            dst.write(data, 1)
        print(f"{site.name}: {out_name} on the {grid.width} x {grid.height} stack grid, "
              f"{100 * float(np.mean(data != nodata)):.1f}% covered")
        written.append(path)
    return written


def sea_mask(water: np.ndarray, edges: tuple[str, ...], cut_px: int = 2) -> np.ndarray:
    """Sea = permanent water connected to the given grid edges.

    Thin links (canals, harbour mouths up to about 2 * cut_px pixels wide) are cut
    first, so a lagoon joined to the sea by a canal stays separate. Pixels outside
    the grid count as water while cutting, so the edge itself is not eroded away.
    """
    if not edges:
        return np.zeros(water.shape, dtype=bool)
    core = ndimage.binary_erosion(water, iterations=cut_px, border_value=1)
    labels, _ = ndimage.label(core, structure=np.ones((3, 3)))
    edge_pixels = {"east": labels[:, -1], "west": labels[:, 0], "north": labels[0, :], "south": labels[-1, :]}
    touching = np.unique(np.concatenate([edge_pixels[e] for e in edges]))
    sea_core = np.isin(labels, touching[touching > 0])
    return water & ndimage.binary_dilation(sea_core, iterations=cut_px + 1)


def sea_on_grid(site: Site) -> Path:
    """Sea mask on the site's 20 m stack grid (1 sea, 0 not sea), from the grid-aligned context layers."""
    grid = site_grid(site)
    with rasterio.open(CONTEXT_DIR / f"{site.name}_worldcover_2021_20m.tif") as wc, \
            rasterio.open(CONTEXT_DIR / f"{site.name}_jrc_occurrence_20m.tif") as jrc:
        cover, occurrence = wc.read(1), jrc.read(1)
    water = (cover == 80) | ((occurrence >= 90) & (occurrence != 255))
    sea = sea_mask(water, site.sea_edges)
    path = CONTEXT_DIR / f"{site.name}_sea_20m.tif"
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="uint8",
                       crs=grid.crs, transform=grid.transform, compress="deflate", tiled=True,
                       blockxsize=512, blockysize=512) as dst:
        dst.write(sea.astype("uint8"), 1)
    print(f"{site.name}: {path.name}, sea {100 * sea.mean():.1f}% of the grid, other permanent water "
          f"{100 * (water & ~sea).mean():.1f}%")
    return path


MJD_EPOCH = date(1858, 11, 17)  # Modified Julian Date day 0


def mjd_to_date(mjd: int) -> date:
    """Calendar date of a Modified Julian Date (exact; used instead of decimal years)."""
    return MJD_EPOCH + timedelta(days=mjd)


def fetch_lor1() -> Path:
    """Daily vertical position of GNSS station LOR1 as a small CSV.

    Columns: date, decimal year, up (m), its 1-sigma (m) and the antenna height
    (m). The antenna height is kept because a change in it (one happened on
    2023-08-03) can put a step into the series.
    """
    resp = requests.get(LOR1_URL, timeout=TIMEOUT_S)
    resp.raise_for_status()
    lines = [ln.split() for ln in resp.text.splitlines() if ln.strip()]
    header, rows = lines[0], lines[1:]
    col = {name: header.index(name) for name in ("__MJD", "yyyy.yyyy", "u0(m)", "____up(m)", "sig_u(m)", "_ant(m)")}
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTEXT_DIR / "lorca_gnss_LOR1_up.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "decimal_year", "up_m", "sigma_up_m", "antenna_height_m"])
        for r in rows:
            up = float(r[col["u0(m)"]]) + float(r[col["____up(m)"]])
            writer.writerow([
                mjd_to_date(int(r[col["__MJD"]])).isoformat(), r[col["yyyy.yyyy"]], f"{up:.5f}",
                r[col["sig_u(m)"]], r[col["_ant(m)"]],
            ])
    print(f"LOR1: {len(rows)} daily positions -> {out.relative_to(DATA_DIR.parent)}")
    return out


def fetch_panama_event() -> Path:
    resp = requests.get(PANAMA_USGS_URL, timeout=TIMEOUT_S)
    resp.raise_for_status()
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTEXT_DIR / "panama_usgs_us6000u18k.geojson"
    out.write_bytes(resp.content)
    print(f"Panama USGS event -> {out.relative_to(DATA_DIR.parent)}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", action="append", choices=[s for s in SITES if s != "panama"],
                        help="only these sites (repeatable); default every site plus LOR1 and Panama")
    args = parser.parse_args()
    for site in SITES.values():
        if site.name == "panama" or (args.site and site.name not in args.site):
            continue  # land cover and water history are for the European sites
        fetch_rasters(site)
        context_on_grid(site)
        sea_on_grid(site)
    if not args.site:
        fetch_lor1()
        fetch_panama_event()


if __name__ == "__main__":
    main()
