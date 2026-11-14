"""Write class / confidence COGs and upsert entries in data/manifest.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import json
from pathlib import Path

import morecantile
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from pipeline.stack import Grid

from . import config


def _write_cog(
    array: np.ndarray, grid: Grid, path: Path, *, web_optimized: bool,
    colormap: dict | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "height": grid.height, "width": grid.width, "count": 1,
        "dtype": "uint8", "crs": grid.crs, "transform": grid.transform,
        "nodata": config.NODATA_U8,
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(array, 1)
            if colormap:
                dst.write_colormap(1, colormap)
        with mem.open() as src:
            # tms=WebMercatorQuad is what `rio cogeo create --web-optimized` does
            # (the web_optimized flag itself is deprecated in rio-cogeo >= 5.1.2).
            cog_translate(
                src, str(path), cog_profiles.get("deflate"),
                tms=morecantile.tms.get("WebMercatorQuad") if web_optimized else None,
                colormap=colormap,
                resampling="nearest", overview_resampling="nearest",
                quiet=True,
            )


def write_outputs(
    class_map: np.ndarray, confidence: np.ndarray, grid: Grid, out_dir: Path
) -> dict[str, Path]:
    """Analysis COGs on EPSG:32630 plus web-optimized copies for the app.

    confidence is stored as 0-100 (% max class probability), 255 = nodata.
    """
    conf_u8 = np.where(
        np.isfinite(confidence), np.clip(np.round(confidence * 100), 0, 100), config.NODATA_U8
    ).astype(np.uint8)
    cmap = {i: (*config.CLASS_COLORS[n], 255) for i, n in enumerate(config.CLASSES)}
    cmap[config.NODATA_U8] = (0, 0, 0, 0)

    paths = {
        "class": out_dir / "class.tif",
        "class_utm": out_dir / "class_utm.tif",
        "confidence": out_dir / "confidence.tif",
        "confidence_utm": out_dir / "confidence_utm.tif",
    }
    _write_cog(class_map, grid, paths["class_utm"], web_optimized=False, colormap=cmap)
    _write_cog(class_map, grid, paths["class"], web_optimized=True, colormap=cmap)
    _write_cog(conf_u8, grid, paths["confidence_utm"], web_optimized=False)
    _write_cog(conf_u8, grid, paths["confidence"], web_optimized=True)
    return paths


def write_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def upsert_manifest(manifest_path: Path, entries: list[dict]) -> None:
    """Replace entries with the same (model, site, layer, date); keep the rest."""
    existing: list[dict] = []
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = lambda e: (e.get("model"), e.get("site"), e.get("layer"), e.get("date"))  # noqa: E731
    new_keys = {key(e) for e in entries}
    merged = [e for e in existing if key(e) not in new_keys] + entries
    write_json(merged, manifest_path)


def read_back(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1)
