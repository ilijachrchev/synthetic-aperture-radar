"""Write one prediction (a replay or a rain scenario) as rasters plus forecast.json."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio

from pipeline.ml.export import _write_cog
from pipeline.stack import Grid

EVIDENCE = {
    0: "prediction from terrain, rain and the previous water map",
    1: "permanent water (JRC occurrence >= 90 %): context, not flooding",
    2: "built-up land: radar water maps are unreliable here, so nothing was learned from towns; the value is extrapolated from fields",
    3: "no water map before the issue time: new water cannot be told from old",
    4: "rarely or never mapped by Sentinel-1 (terrain mask, shadow): extrapolated",
    255: "sea or outside the land grid",
}
PIXEL_HA = 0.04


def evidence(static: dict, freq: np.ndarray, state: np.ndarray, idx: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    ev = np.full(shape[0] * shape[1], 255, dtype="uint8")
    e = np.zeros(idx.size, dtype="uint8")
    e[np.isnan(state)] = 3
    e[np.isnan(freq)] = 4
    e[static["urban"].ravel()[idx]] = 2
    e[static["permanent"].ravel()[idx]] = 1
    ev[idx] = e
    return ev.reshape(shape)


def _float_tif(array: np.ndarray, grid: Grid, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="float32",
                       crs=grid.crs, transform=grid.transform, nodata=np.nan, compress="deflate", predictor=3,
                       tiled=True, blockxsize=256, blockysize=256) as dst:
        dst.write(np.round(array, 3).astype("float32"), 1)


def write(out_dir: Path, grid: Grid, score: np.ndarray, state: np.ndarray, ev: np.ndarray, idx: np.ndarray,
          meta: dict, thresholds: dict) -> dict:
    """score, state: per pixel of idx. Returns the forecast.json content."""
    shape = (grid.height, grid.width)
    like = np.full(shape[0] * shape[1], np.nan, dtype="float32")
    like[idx] = score
    new = np.full_like(like, np.nan)
    dry_before = state == 0
    new[idx[dry_before]] = score[dry_before]
    like, new = like.reshape(shape), new.reshape(shape)
    new[ev == 1] = np.nan
    _float_tif(like, grid, out_dir / "water_likelihood_utm.tif")
    _float_tif(new, grid, out_dir / "new_water_likelihood_utm.tif")
    with rasterio.open(out_dir / "evidence_utm.tif", "w", driver="GTiff", height=grid.height, width=grid.width, count=1,
                       dtype="uint8", crs=grid.crs, transform=grid.transform, nodata=255, compress="deflate") as dst:
        dst.write(ev, 1)
    for name, arr in (("water_likelihood_web.tif", like), ("new_water_likelihood_web.tif", new)):
        u8 = np.where(np.isfinite(arr), np.clip(np.round(arr * 100), 0, 100), 255).astype("uint8")
        _write_cog(u8, grid, out_dir / name, web_optimized=True)
    trusted = ev == 0
    doc = {
        **meta,
        "score": "relative water likelihood 0-1 learned from Sentinel-1 water maps; not a calibrated flood probability",
        "files": {"water_likelihood_utm.tif": "float32 0-1, NaN outside land, EPSG:32630 20 m",
                  "new_water_likelihood_utm.tif": "the same, only where the previous water map says dry",
                  "evidence_utm.tif": "uint8 flags, see evidence",
                  "water_likelihood_web.tif": "uint8 0-100, 255 no data, Web Mercator COG",
                  "new_water_likelihood_web.tif": "uint8 0-100, 255 no data, Web Mercator COG"},
        "evidence": {str(k): v for k, v in EVIDENCE.items()},
        "thresholds": thresholds,
        "area_ha": {
            "likely_water": round(float((like[trusted] >= thresholds["water"]).sum()) * PIXEL_HA, 1),
            "likely_new_water": round(float((np.nan_to_num(new[trusted], nan=-1) >= thresholds["new_water"]).sum()) * PIXEL_HA, 1),
            "counted_on": "evidence 0 pixels only",
        },
        "native_resolution": {"rain": "ECMWF IFS 9 km, one value per site and day", "terrain": "30 m", "water_maps": "30 m"},
        "attribution": "OPERA DSWx-S1 (NASA JPL), Open-Meteo / ECMWF IFS (CC BY 4.0), ASF GLO-30 HAND, Copernicus DEM GLO-30, "
                       "ESA WorldCover 2021, JRC Global Surface Water",
    }
    (out_dir / "forecast.json").write_text(json.dumps(doc, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return doc
