"""Where did the water run in the towns? Terrain flow against the official flood zones.

DANA of 29 Oct 2024, L'Horta Sud and Chiva (the 10 towns of pipeline.zones). In
the towns, radar at 20 m cannot see water between buildings, so the "where will
the water go" answer has to come from the terrain. This module tests, on the
same 5 m pixels, whether a terrain flow map that needs no training points to
where the 2024 water ran better than the official flood zones (SNCZI).

The rules (area, methods, metrics, thresholds) are written in docs/STREETS.md
before any score was computed, and nothing is tuned on 2024: thresholds come
from the literature or are fixed to the official zones' area.

Steps (in this order):
    python -m pipeline.streets fetch      # downloads into data/interim/streets/ (not in git), about 12 GB
                                          # streamed one terrain sheet at a time (about 2 GB on disk at once)
    python -m pipeline.streets terrain    # 5 m terrain, depressions filled, flow, HAND (about 10 minutes, 4 GB RAM)
    python -m pipeline.streets simulate   # rain on terrain at 25 m, SIMULATED (numba venv: about 20 minutes)
    python -m pipeline.streets score      # every method on the same pixels: data/streets/results.json
    python -m pipeline.streets layers     # small web layers in data/streets/
    python -m pipeline.streets depth      # flood depth ESTIMATED from the outlines and terrain (2024, 2026)
    python -m pipeline.streets report     # the tables of docs/STREETS.md, printed from results.json

The simulation runs fast with numba, which is not in the shared stack: make a
separate venv for it (see docs/STREETS.md); without it the numpy version runs
(the same scheme, hours instead of minutes).

Needs the downloads of pipeline.zones (PR #36: `python -m pipeline.zones fetch`,
into data/interim/flood-zones/) for the municipalities, the SNCZI zones and the
EMSR773 products; `--zones-interim` points elsewhere.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.windows import Window

from pipeline.config import DATA_DIR

INTERIM_DIR = DATA_DIR / "interim" / "streets"
ZONES_INTERIM_DIR = DATA_DIR / "interim" / "flood-zones"
STREETS_DIR = DATA_DIR / "streets"
CRS = "EPSG:25830"  # ETRS89 / UTM 30N, native CRS of the terrain, SNCZI and ICV layers
TIMEOUT_S = 300
USER_AGENT = "Mozilla/5.0 (sar-pipeline streets)"
SI_LINE = "Written with SI assistance (Claude Code), reviewed by the team."

# The analysis grid: 5 m cells aligned to multiples of 5 m, covering the 10
# municipalities and the catchment of the Poyo, Pozalet and Saleta ravines
# (ICV layer DANA2024.AVSRE.Cuencas, code 29: x 683,344 to 731,650,
# y 4,358,877 to 4,380,109; the municipalities: x 678,746 to 730,012,
# y 4,360,607 to 4,380,667).
CELL_M = 5.0
GRID_BOUNDS = (678000.0, 4357000.0, 732000.0, 4381500.0)  # west, south, east, north

# ---------------------------------------------------------------- terrain source

# ICV, Modelo Digital del Terreno (MDT) de LIDAR de 1 metro de resolucion de la
# provincia de Valencia 2015: ground class of the PNOA-LiDAR 2015 flight
# (1 Oct to 30 Nov 2015), reclassified and edited by hand, with breaklines;
# float32 GeoTIFF by MTN50 sheet ("Producto derivado de LIDAR-PNOA 2015", the
# national LiDAR programme that IGN's MDT02 and MDT05 also come from). IGN's own
# 5 m web service returns whole metres, too coarse here. Averaged here to 5 m.
DTM = {
    "key": "icv_mdt_2015_1m",
    "title": "Modelo Digital del Terreno (MDT) de LIDAR de 1 metro de resolución de la provincia de Valencia 2015",
    "publisher": "Institut Cartogràfic Valencià (ICV), Generalitat Valenciana",
    "catalogue": "https://dadesobertes.gva.es/dataset/modelo-digital-del-terreno-mdt-de-lidar-de-1-metro-de-resolucion-de-la-provincia-de-valenc-2015",
    "sheet_index_wfs": "https://terramapas.icv.gva.es/030201_2015PVAL0100_hojas",
    "url": ("https://descargas.icv.gva.es/dcd/03_mde/02_mdt/2015_PVAL_0100/01_Malla/"
            "01_25830_01_Hoja_CV50_03_TIF/030201_MDT_2015PVAL0100_25830_01_Hoja_CV50_{sheet}.tif"),
    "lidar_flight": "PNOA-LiDAR 2015, 1 Oct to 30 Nov 2015 (catalogue temporal extent)",
    "licence": "CC BY 4.0",
    "credit": "Obra derivada de LIDAR-PNOA 2015 CC-BY 4.0 scne.es; MDT 1 m, Institut Cartogràfic Valencià",
}
# MTN50 sheets that touch the analysis grid, the towns first.
DTM_SHEETS = ("0722", "0721", "0696", "0695", "0720", "0694")
DTM_NODATA = -9999.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _manifest_path() -> Path:
    return INTERIM_DIR / "manifest.json"


def load_manifest() -> dict:
    path = _manifest_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_manifest(manifest: dict) -> None:
    """Write the manifest, keeping entries another step wrote meanwhile (fetch steps can run side by side)."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    merged = {**load_manifest(), **manifest}
    manifest.update(merged)
    _manifest_path().write_text(json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")


def record(manifest: dict, key: str, url: str, path: Path, data_bytes: int, sha256: str, **extra) -> None:
    manifest[key] = {"url": url, "file": path.relative_to(DATA_DIR.parent).as_posix(),
                     "bytes": data_bytes, "sha256": sha256, "retrieved_utc": _now(), **extra}


def download(url: str, path: Path, chunk: int = 8 << 20) -> tuple[int, str]:
    """Stream a URL to a file; returns (bytes, sha256)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with requests.get(url, stream=True, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}) as resp:
        resp.raise_for_status()
        with open(path, "wb") as fh:
            for block in resp.iter_content(chunk_size=chunk):
                fh.write(block)
                digest.update(block)
                size += len(block)
    return size, digest.hexdigest()


def block_mean(a: np.ndarray, factor: int, nodata: float, min_valid: int | None = None) -> np.ndarray:
    """Mean of factor x factor blocks, ignoring nodata; nodata where fewer than
    min_valid cells (default: more than half) are valid. Shape must divide."""
    rows, cols = a.shape
    if rows % factor or cols % factor:
        raise ValueError(f"shape {a.shape} is not a multiple of {factor}")
    min_valid = factor * factor // 2 + 1 if min_valid is None else min_valid
    valid = a != nodata
    blocks = np.where(valid, a, 0.0).astype(np.float64).reshape(rows // factor, factor, cols // factor, factor)
    count = valid.reshape(rows // factor, factor, cols // factor, factor).sum(axis=(1, 3))
    total = blocks.sum(axis=(1, 3))
    out = np.full(count.shape, nodata, dtype=np.float32)
    ok = count >= min_valid
    out[ok] = (total[ok] / count[ok]).astype(np.float32)
    return out


def aggregate_sheet(src_path: Path, dst_path: Path, factor: int = 5, rows_per_read: int = 2000) -> dict:
    """Average a 1 m sheet to 5 m, reading it in bands of rows (the file is striped)."""
    with rasterio.open(src_path) as src:
        nodata = src.nodata if src.nodata is not None else DTM_NODATA
        t = src.transform
        if (t.a, t.e) != (1.0, -1.0):
            raise RuntimeError(f"{src_path.name}: expected 1 m cells, got {t.a} x {t.e}")
        if (t.c % CELL_M) or (t.f % CELL_M) or (src.width % factor) or (src.height % factor):
            raise RuntimeError(f"{src_path.name}: grid not aligned to {CELL_M} m")
        profile = {
            "driver": "GTiff", "dtype": "float32", "nodata": DTM_NODATA, "crs": src.crs,
            "width": src.width // factor, "height": src.height // factor, "count": 1,
            "transform": rasterio.Affine(CELL_M, 0, t.c, 0, -CELL_M, t.f),
            "tiled": True, "blockxsize": 512, "blockysize": 512, "compress": "deflate", "predictor": 3,
        }
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as dst:
            for row in range(0, src.height, rows_per_read):
                n = min(rows_per_read, src.height - row)
                a = src.read(1, window=Window(0, row, src.width, n))
                out = block_mean(a, factor, nodata)
                out[out == nodata] = DTM_NODATA
                dst.write(out, 1, window=Window(0, row // factor, out.shape[1], out.shape[0]))
        return {"width_1m": src.width, "height_1m": src.height, "bounds": list(src.bounds),
                "aggregation": f"mean of {factor} x {factor} cells, nodata if half or fewer are valid"}


def fetch_dtm(manifest: dict, sheets: tuple[str, ...] = DTM_SHEETS, keep_1m: bool = False) -> None:
    """Download each 1 m sheet, average it to 5 m, delete the 1 m file (about 2 GB each)."""
    out_dir = INTERIM_DIR / "dtm"
    for sheet in sheets:
        dst = out_dir / f"dtm5_2015_{sheet}.tif"
        key = f"dtm_2015_{sheet}"
        if dst.exists() and key in manifest:
            print(f"DTM sheet {sheet}: done before")
            continue
        url = DTM["url"].format(sheet=sheet)
        tmp = out_dir / f"_1m_{sheet}.tif"
        print(f"DTM sheet {sheet}: downloading {url}", flush=True)
        size, sha = download(url, tmp)
        info = aggregate_sheet(tmp, dst)
        record(manifest, key, url, dst, size, sha, source_sha256_is_of="the 1 m file as downloaded", **info)
        save_manifest(manifest)
        if not keep_1m:
            tmp.unlink()
        print(f"DTM sheet {sheet}: {size / 1e9:.2f} GB, averaged to 5 m", flush=True)


# ---------------------------------------------------------------- other sources

ICV_DANA2024_WFS = "https://terramapas.icv.gva.es/2702_DANA2024"
ICV_LAYERS = {
    "footprint": "DANA2024.ZonasInundadas.HuellaInundacion",
    "marks_upv": "DANA2024.ZonasInundadas.AlturaAgua.UPV",
    "marks_ive": "DANA2024.ZonasInundadas.AlturaAgua.IVE",
    "marks_sgrt": "DANA2024.ZonasInundadas.AlturaAgua.SGRT",
    "marks_town_halls": "DANA2024.ZonasInundadas.AlturaAgua.AyuntamientosOtros",
    "catchments": "DANA2024.AVSRE.Cuencas",
}
WATER_MARK_LAYERS = ("marks_upv", "marks_ive", "marks_sgrt", "marks_town_halls")

CATASTRO_ATOM = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/46/ES.SDGC.bu.atom_46.xml"
# Catastro's own municipality codes (not INE), from the ATOM feed titles.
CATASTRO_CODES = {
    "Paiporta": "46188", "Massanassa": "46167", "Sedaví": "46225", "Catarroja": "46096",
    "Alfafar": "46022", "Benetússer": "46054", "Picanya": "46195", "Aldaia": "46021",
    "Chiva": "46113", "Torrent": "46246",
}

WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_N39W003_Map.tif")
WORLDCOVER_BBOX = (-0.95, 39.33, -0.27, 39.58)  # lon, lat; holds the analysis grid
WORLDCOVER_WATER = 80  # "Permanent water bodies"

RAIN_SOURCES = {
    "perez_cueva_2025": "https://repositorio.aemet.es/bitstream/20.500.11765/17270/1/IG_Perez_2025.pdf",
    "chj_report_2025": "https://saih.chj.es/docs/20241029-1104Informe-Episodio-C-version2.pdf",
    "aemet_report_2024": "https://repositorio.aemet.es/bitstream/20.500.11765/16360/1/informe_episodio_dana_29_oct_2024_.pdf",
}


def fetch_icv(manifest: dict) -> None:
    """The ICV DANA 2024 layers as GML (the format every layer of the service offers)."""
    for key, layer in ICV_LAYERS.items():
        params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": f"ms:{layer}",
                  "srsName": "urn:ogc:def:crs:EPSG::25830", "outputFormat": "text/xml; subtype=gml/3.1.1"}
        resp = requests.get(ICV_DANA2024_WFS, params=params, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        path = INTERIM_DIR / "icv" / f"{layer}.gml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        record(manifest, f"icv_{key}", resp.url, path, len(resp.content), hashlib.sha256(resp.content).hexdigest(),
               layer=layer)
        print(f"ICV {layer}: {len(resp.content) / 1e6:.1f} MB")


def fetch_catastro(manifest: dict) -> None:
    """Catastro INSPIRE building outlines of the 10 municipalities (zipped GML, from the ATOM feed)."""
    import re

    atom = requests.get(CATASTRO_ATOM, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    atom.raise_for_status()
    text = atom.text
    for name, code in CATASTRO_CODES.items():
        hrefs = sorted(set(re.findall(rf'href="(https?://[^"]*/{code}-[^"]*/A\.ES\.SDGC\.BU\.{code}\.zip)"', text)))
        if len(hrefs) != 1:
            raise RuntimeError(f"Catastro {name} ({code}): {len(hrefs)} building downloads in the ATOM feed")
        path = INTERIM_DIR / "catastro" / f"A.ES.SDGC.BU.{code}.zip"
        size, sha = download(hrefs[0], path)
        record(manifest, f"catastro_{code}", hrefs[0], path, size, sha, municipality=name, atom=CATASTRO_ATOM)
        print(f"Catastro {name}: {size / 1e6:.1f} MB")


def fetch_worldcover(manifest: dict) -> None:
    """Clip of ESA WorldCover 2021 (10 m) around the grid, read remotely from the public bucket."""
    from rasterio.windows import from_bounds

    path = INTERIM_DIR / "worldcover_2021_clip.tif"
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(f"/vsicurl/{WORLDCOVER_URL}") as src:
            win = from_bounds(*WORLDCOVER_BBOX, transform=src.transform).round_offsets().round_lengths()
            data = src.read(1, window=win)
            profile = {"driver": "GTiff", "dtype": "uint8", "count": 1, "crs": src.crs, "nodata": 0,
                       "width": data.shape[1], "height": data.shape[0],
                       "transform": src.window_transform(win), "compress": "deflate"}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    raw = path.read_bytes()
    record(manifest, "worldcover_2021", WORLDCOVER_URL, path, len(raw), hashlib.sha256(raw).hexdigest(),
           bbox_lonlat=list(WORLDCOVER_BBOX), note="window of the 10 m tile N39W003")
    print(f"WorldCover clip: {data.shape}")


def fetch_rain_sources(manifest: dict) -> None:
    for key, url in RAIN_SOURCES.items():
        path = INTERIM_DIR / "rain" / Path(url).name
        size, sha = download(url, path)
        record(manifest, f"rain_{key}", url, path, size, sha)
        print(f"{key}: {size / 1e6:.1f} MB")


def fetch(manifest: dict) -> None:
    fetch_icv(manifest)
    save_manifest(manifest)
    fetch_catastro(manifest)
    save_manifest(manifest)
    fetch_worldcover(manifest)
    save_manifest(manifest)
    fetch_rain_sources(manifest)
    save_manifest(manifest)
    fetch_dtm(manifest)
    fetch_pego_dtm(manifest)
    save_manifest(manifest)


# ---------------------------------------------------------------- grid

TERRAIN_DIR = INTERIM_DIR / "terrain"

TOWNS = ("Paiporta", "Massanassa", "Sedaví", "Catarroja", "Alfafar", "Benetússer",
         "Picanya", "Aldaia", "Chiva", "Torrent")
TOWN_INE = {"Paiporta": "46186", "Massanassa": "46165", "Sedaví": "46223", "Catarroja": "46094",
            "Alfafar": "46022", "Benetússer": "46054", "Picanya": "46193", "Aldaia": "46021",
            "Chiva": "46111", "Torrent": "46244"}


def grid_shape() -> tuple[int, int]:
    w, s, e, n = GRID_BOUNDS
    return int(round((n - s) / CELL_M)), int(round((e - w) / CELL_M))


def grid_transform(cell: float = CELL_M, bounds: tuple[float, float, float, float] | None = None) -> rasterio.Affine:
    w, s, e, n = GRID_BOUNDS if bounds is None else bounds
    return rasterio.Affine(cell, 0.0, w, 0.0, -cell, n)


def save_grid(name: str, a: np.ndarray, nodata=None, cell: float = CELL_M, folder: Path | None = None,
              bounds: tuple[float, float, float, float] | None = None) -> Path:
    folder = TERRAIN_DIR if folder is None else folder
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.tif"
    profile = {"driver": "GTiff", "dtype": a.dtype.name if a.dtype != bool else "uint8", "nodata": nodata,
               "crs": CRS, "width": a.shape[1], "height": a.shape[0], "count": 1,
               "transform": grid_transform(cell, bounds), "tiled": True, "blockxsize": 512, "blockysize": 512,
               "compress": "deflate", "BIGTIFF": "IF_SAFER"}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(a.astype(np.uint8) if a.dtype == bool else a, 1)
    return path


def load_grid(name: str, folder: Path | None = None) -> np.ndarray:
    with rasterio.open((TERRAIN_DIR if folder is None else folder) / f"{name}.tif") as src:
        return src.read(1)


def mosaic_dtm() -> np.ndarray:
    """The 5 m sheets placed on the analysis grid (the first sheet wins where two overlap)."""
    rows, cols = grid_shape()
    out = np.full((rows, cols), DTM_NODATA, dtype=np.float32)
    for sheet in DTM_SHEETS:
        with rasterio.open(INTERIM_DIR / "dtm" / f"dtm5_2015_{sheet}.tif") as src:
            t = src.transform
            col0 = int(round((t.c - GRID_BOUNDS[0]) / CELL_M))
            row0 = int(round((GRID_BOUNDS[3] - t.f) / CELL_M))
            r0, c0 = max(0, row0), max(0, col0)
            r1, c1 = min(rows, row0 + src.height), min(cols, col0 + src.width)
            if r1 <= r0 or c1 <= c0:
                continue
            sub = src.read(1, window=Window(c0 - col0, r0 - row0, c1 - c0, r1 - r0))
        dst = out[r0:r1, c0:c1]
        take = (dst == DTM_NODATA) & (sub != DTM_NODATA)
        dst[take] = sub[take]
    return out


def burn(geoms, cell: float = CELL_M, bounds: tuple[float, float, float, float] | None = None) -> np.ndarray:
    """Cells whose centre lies inside any of the geometries (all_touched=False)."""
    import shapely
    from rasterio.features import rasterize

    w, s, e, n = GRID_BOUNDS if bounds is None else bounds
    rows, cols = int(round((n - s) / cell)), int(round((e - w) / cell))
    shapes = []
    for g in geoms:
        if g is None or g.is_empty:
            continue
        g = shapely.clip_by_rect(g, w, s, e, n)
        if not g.is_empty:
            shapes.append((g, 1))
    if not shapes:
        return np.zeros((rows, cols), dtype=bool)
    return rasterize(shapes, out_shape=(rows, cols), transform=grid_transform(cell, bounds), fill=0,
                     dtype="uint8", all_touched=False).astype(bool)


def cells_of_points(x: np.ndarray, y: np.ndarray, bounds: tuple[float, float, float, float] | None = None
                    ) -> np.ndarray:
    """Flat grid index of the cell holding each point; -1 outside the grid."""
    w, s, e, n = GRID_BOUNDS if bounds is None else bounds
    rows, cols = int(round((n - s) / CELL_M)), int(round((e - w) / CELL_M))
    c = np.floor((x - w) / CELL_M).astype(np.int64)
    r = np.floor((n - y) / CELL_M).astype(np.int64)
    ok = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
    return np.where(ok, r * cols + c, -1)


def water_mask() -> np.ndarray:
    """Permanent water (ESA WorldCover 2021 class 80) on the grid, nearest cell."""
    from rasterio.warp import Resampling, reproject

    out = np.zeros(grid_shape(), dtype=np.uint8)
    with rasterio.open(INTERIM_DIR / "worldcover_2021_clip.tif") as src:
        reproject(src.read(1), out, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=grid_transform(), dst_crs=CRS, resampling=Resampling.nearest)
    return out == WORLDCOVER_WATER


# ---------------------------------------------------------------- terrain

DRAINAGE_M2 = 0.5e6               # MERIT Hydro's HAND drainage: upstream area above 0.5 km2
DRAINAGE_SENSITIVITY_M2 = (0.05e6, 5e6)
HAND_NATIVE_M = 15.0              # Twele et al. 2016: HAND of 15 m or more is non-flood prone
BUILDING_RAISE_M = 10.0           # buildings as obstacles: footprints raised for routing only


def catastro_buildings():
    import geopandas as gpd

    frames = []
    for name, code in CATASTRO_CODES.items():
        path = INTERIM_DIR / "catastro" / f"A.ES.SDGC.BU.{code}.zip"
        g = gpd.read_file(f"/vsizip/{path.as_posix()}/A.ES.SDGC.BU.{code}.building.gml")
        g = g.set_crs(CRS, allow_override=True) if g.crs is None else g.to_crs(CRS)
        frames.append(g[["geometry"]].assign(municipality=name))
    return gpd.pd.concat(frames, ignore_index=True)


def flow(zroute: np.ndarray, valid: np.ndarray, sinks: np.ndarray, label: str) -> dict:
    """Fill, D8, flats and accumulation on one routing surface; saves code, filled surface and upstream area."""
    import time

    from pipeline import terrain_flow as tf

    t0 = time.time()
    outlets = tf.outlet_cells(valid, sinks)
    zf = tf.fill_depressions(zroute, valid, outlets)
    save_grid(f"zfill_{label}", zf, nodata=DTM_NODATA)
    code = tf.d8_directions(zf, valid, outlets)
    code[sinks] = tf.NO_DIR  # water reaching permanent water leaves the grid there
    code, flats = tf.drain_flats(zf, code, valid, outlets)
    del zf, outlets
    save_grid(f"code_{label}", code, nodata=None)
    rec = tf.receivers(code)
    del code
    upa = (tf.accumulate(rec, valid) * CELL_M * CELL_M).astype(np.float32)
    save_grid(f"upa_{label}", upa, nodata=None)
    info = {"label": label, "flat_cells": flats["flat_cells"], "flat_rounds": flats["rounds"],
            "left_undrained": flats["left_undrained"], "seconds": round(time.time() - t0, 1)}
    print(f"flow {label}: {info}", flush=True)
    return {"rec": rec, "upa": upa, "info": info}


def hand_maps(rec: np.ndarray, upa: np.ndarray, sinks: np.ndarray, valid: np.ndarray,
              heights: np.ndarray, label: str, thresholds=(DRAINAGE_M2, *DRAINAGE_SENSITIVITY_M2)) -> dict:
    """HAND for each drainage threshold. Permanent water counts as drainage too (HAND 0 there)."""
    from pipeline import terrain_flow as tf

    out = {}
    for thr in thresholds:
        drainage = ((upa > thr) | sinks) & valid
        h, _ = tf.hand(heights, rec, drainage)
        h[~valid] = np.nan
        name = f"hand_{label}_d{thr / 1e6:g}km2".replace(".", "p")
        save_grid(name, h.astype(np.float32), nodata=np.nan)
        out[name] = {"drainage_km2": thr / 1e6, "drainage_cells": int(drainage.sum()),
                     "nan_cells_in_valid": int(np.isnan(h[valid]).sum())}
        del h, drainage
    return out


LAKE_MIN_KM2 = 1.0  # water bodies this large are sinks in the "lake" routing (the sea, the port, the Albufera)


def large_water(water: np.ndarray, min_km2: float = LAKE_MIN_KM2) -> np.ndarray:
    """The connected permanent-water bodies (8-connected) of at least min_km2; drops ponds and quarry lakes."""
    from scipy import ndimage

    lab, _ = ndimage.label(water, structure=np.ones((3, 3), dtype=bool))
    sizes = np.bincount(lab.ravel()) * CELL_M * CELL_M / 1e6
    keep = sizes >= min_km2
    keep[0] = False
    return keep[lab]


def terrain(variants: bool = True, only: str | None = None) -> dict:
    """5 m mosaic, permanent water, flow and HAND (bare terrain; buildings as obstacles; lake-only sinks).

    only="lake" runs just the lake-only routing (sinks: water bodies of at least 1 km2), added after
    the first scores showed that WorldCover ponds acting as sinks cut the Poyo's flow paths.
    """
    info_path = TERRAIN_DIR / "terrain_info.json"
    if only == "lake":
        info = json.loads(info_path.read_text(encoding="utf-8"))
        z = load_grid("dtm5")
        valid = z != DTM_NODATA
        water = load_grid("water5").astype(bool)
        lake = large_water(water)
        save_grid("lake5", lake)
        info["lake_cells"] = int(lake.sum())
        info["lake_rule"] = f"WorldCover class 80 bodies of at least {LAKE_MIN_KM2:g} km2 (8-connected)"
        res = flow(z, valid, lake, "lake")
        info["flow_lake"] = res["info"]
        info["hand_lake"] = hand_maps(res["rec"], res["upa"], lake, valid, load_grid("zfill_lake"), "lake",
                                      thresholds=(DRAINAGE_M2,))
        info_path.write_text(json.dumps(info, indent=1), encoding="utf-8")
        return info
    z = mosaic_dtm()
    valid = z != DTM_NODATA
    save_grid("dtm5", z, nodata=DTM_NODATA)
    sinks = water_mask() & valid
    save_grid("water5", sinks)
    info = {"grid": {"bounds": list(GRID_BOUNDS), "cell_m": CELL_M, "shape": list(z.shape),
                     "valid_cells": int(valid.sum()), "permanent_water_cells": int(sinks.sum())}}
    print(info, flush=True)
    bare = flow(z, valid, sinks, "bare")
    zf_bare = load_grid("zfill_bare")
    info["flow_bare"] = bare["info"]
    info["hand_bare"] = hand_maps(bare["rec"], bare["upa"], sinks, valid, zf_bare, "bare")
    del bare
    if variants:
        bld = burn(catastro_buildings().geometry) & valid
        save_grid("buildings5", bld)
        zb = np.where(bld, z + np.float32(BUILDING_RAISE_M), z).astype(np.float32)
        info["buildings_cells"] = int(bld.sum())
        del bld, z
        obst = flow(zb, valid, sinks, "bldg")
        del zb
        info["flow_bldg"] = obst["info"]
        # heights from the terrain without buildings
        info["hand_bldg"] = hand_maps(obst["rec"], obst["upa"], sinks, valid, zf_bare, "bldg",
                                      thresholds=(DRAINAGE_M2,))
        del obst
    info_path.write_text(json.dumps(info, indent=1), encoding="utf-8")
    if variants:
        info = terrain(only="lake")
    return info


# ---------------------------------------------------------------- references and official zones

EMSR773 = (("EMSR773_AOI03_GRA_PRODUCT", 2), ("EMSR773_AOI03_DEL_PRODUCT", 1), ("EMSR773_AOI01_DEL_PRODUCT", 1))
ZONE_SETS = {"T10": ("fluvial_t10",), "T100": ("fluvial_t100", "marine_t100"),
             "T500": ("fluvial_t500", "marine_t500")}
ZONE_NAMES = ("T10", "T100", "T500", "union")


def load_towns(zones_dir: Path):
    """The 10 municipalities (IGN), checked by name as in pipeline.zones."""
    import geopandas as gpd
    from shapely.geometry import shape

    doc = json.loads((zones_dir / "ign_horta_sud.geojson").read_text(encoding="utf-8"))
    feats = {f["id"]: f for f in doc["features"]}
    rows = []
    for name in TOWNS:
        ine = TOWN_INE[name]
        f = feats[f"AU_ADMINISTRATIVEUNIT_3410{ine[:2]}{ine}"]
        ign = f["properties"]["name"]["GeographicalName"]["spelling"]["SpellingOfName"]["text"]
        if name.casefold() not in [n.strip().casefold() for n in ign.split("/")]:
            raise RuntimeError(f"INE {ine}: IGN calls it {ign!r}, expected {name!r}")
        rows.append({"name": name, "ine": ine, "geometry": shape(f["geometry"])})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4258").to_crs(CRS)


def town_grid(towns) -> np.ndarray:
    """Town number (1 to 10, in TOWNS order) of each cell, 0 outside."""
    from rasterio.features import rasterize

    shapes = [(g, i + 1) for i, g in enumerate(towns.geometry)]
    return rasterize(shapes, out_shape=grid_shape(), transform=grid_transform(), fill=0, dtype="uint8")


def ems_layer(zones_dir: Path, stem: str, version: int, layer: str):
    import geopandas as gpd

    path = zones_dir / "raw" / "emsr773" / f"{stem}_v{version}.zip"
    return gpd.read_file(f"/vsizip/{path.as_posix()}/{stem}_{layer}_v{version}.shp").to_crs(CRS)


def ems_products(zones_dir: Path) -> list[dict]:
    """Per EMSR773 product: where it looked, its flooded area and its flood traces (cell masks)."""
    out = []
    for stem, version in EMSR773:
        aoi = burn(ems_layer(zones_dir, stem, version, "areaOfInterestA").geometry)
        fp = ems_layer(zones_dir, stem, version, "imageFootprintA")
        kind = fp["obj_type"].astype(str)
        images = burn(fp.geometry[kind == "Image Footprint"])
        not_analysed = burn(fp.geometry[kind.str.startswith("Not Analysed")])
        obs = ems_layer(zones_dir, stem, version, "observedEventA")
        unknown = set(obs["notation"]) - {"Flooded area", "Flood trace"}
        if unknown:
            raise RuntimeError(f"{stem}: unexpected observed classes {sorted(unknown)}")
        out.append({"name": f"{stem}_v{version}", "analysed": aoi & images & ~not_analysed,
                    "flooded_area": burn(obs.geometry[obs["notation"] == "Flooded area"]),
                    "flood_trace": burn(obs.geometry[obs["notation"] == "Flood trace"])})
        del aoi, images, not_analysed
    return out


def zone_grids(zones_dir: Path) -> dict[str, np.ndarray]:
    import geopandas as gpd

    layers = {}
    for keys in ZONE_SETS.values():
        for key in keys:
            gdf = gpd.read_file(zones_dir / f"snczi_horta_sud_{key}.geojson")
            gdf = gdf.set_crs("EPSG:25830") if gdf.crs is None else gdf.to_crs(CRS)
            layers[key] = burn(gdf.geometry)
    out = {name: np.logical_or.reduce([layers[k] for k in keys]) for name, keys in ZONE_SETS.items()}
    out["union"] = out["T10"] | out["T100"] | out["T500"]
    return out


def icv_layer(key: str):
    import geopandas as gpd

    g = gpd.read_file(INTERIM_DIR / "icv" / f"{ICV_LAYERS[key]}.gml")
    return g.set_crs(CRS, allow_override=True)


def water_marks() -> dict:
    """Surveyed water heights above 0 m (ICV): cell index, source layer and height."""
    import pandas as pd

    frames = []
    for key in WATER_MARK_LAYERS:
        g = icv_layer(key)
        h = pd.to_numeric(g["altura_agua_m"], errors="coerce")
        frames.append(pd.DataFrame({"x": g.geometry.x, "y": g.geometry.y, "height_m": h, "layer": key}))
    df = pd.concat(frames, ignore_index=True)
    n_all = len(df)
    df = df[df["height_m"] > 0]
    return {"cell": cells_of_points(df["x"].to_numpy(), df["y"].to_numpy()), "layer": df["layer"].to_numpy(),
            "height_m": df["height_m"].to_numpy(), "points_read": n_all, "points_above_0": len(df)}


def graded_buildings(zones_dir: Path, towns) -> dict:
    """EMSR773 AOI03 grading map points (possibly damaged, damaged, destroyed) inside the 10 towns."""
    import geopandas as gpd

    stem, version = EMSR773[0]
    pts = ems_layer(zones_dir, stem, version, "builtUpP")
    joined = gpd.sjoin(pts[["damage_gra", "geometry"]], towns[["name", "geometry"]], how="inner", predicate="within")
    joined = joined[~joined.index.duplicated()]
    return {"cell": cells_of_points(joined.geometry.x.to_numpy(), joined.geometry.y.to_numpy()),
            "town": joined["name"].to_numpy(), "damage": joined["damage_gra"].astype(str).to_numpy(),
            "points_in_product": len(pts)}


# ---------------------------------------------------------------- scoring


def pct(num: float, den: float) -> float | None:
    return None if den <= 0 else round(100.0 * num / den, 1)


def metrics(sel: np.ndarray, refs: dict, b_pos: np.ndarray, m_pos: np.ndarray) -> dict:
    """The metrics of one method on one set of scored pixels (all arrays over those pixels).

    b_pos, m_pos: positions (in the same pixel set) of the graded buildings and water marks.
    """
    n = sel.size
    k = int(sel.sum())
    obs = refs["observed"]
    out = {
        "area_ha": round(k * CELL_M * CELL_M / 1e4, 1),
        "area_pct_of_scored": pct(k, n),
        "buildings_covered_pct": pct(int(sel[b_pos].sum()), b_pos.size),
        "buildings": int(b_pos.size),
        "flood_trace_covered_pct": pct(int((sel & refs["flood_trace"]).sum()), int(refs["flood_trace"].sum())),
        "observed_covered_pct": pct(int((sel & obs).sum()), int(obs.sum())),
        "flooded_area_covered_pct": pct(int((sel & refs["flooded_area"]).sum()), int(refs["flooded_area"].sum())),
        "own_area_flooded_pct": pct(int((sel & obs).sum()), k),
        "generalitat_footprint_covered_pct": pct(int((sel & refs["icv"]).sum()), int(refs["icv"].sum())),
        "own_area_in_generalitat_footprint_pct": pct(int((sel & refs["icv"]).sum()), k),
        "water_marks_covered_pct": pct(int(sel[m_pos].sum()), m_pos.size),
        "water_marks": int(m_pos.size),
        "lower_bound_observed_covered_pct": pct(int((sel & refs["lb_observed"]).sum()), int(refs["lb_observed"].sum())),
        "lower_bound_own_area_flooded_pct": pct(int((sel & refs["lb_observed"]).sum()), k),
    }
    out["chance_own_area_flooded_pct"] = pct(int(obs.sum()), n)
    return out


def ranked(hand_s: np.ndarray, upa_s: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """Positions ordered for the equal-area cut: lowest HAND first, larger upstream area, then grid order."""
    from pipeline.terrain_flow import equal_area_pick

    return positions[equal_area_pick(hand_s[positions], upa_s[positions], positions.size)]


def first_k(order: np.ndarray, k: int, n: int) -> np.ndarray:
    sel = np.zeros(n, dtype=bool)
    sel[order[:k]] = True
    return sel


def score(zones_dir: Path, zones_json: Path | None = None) -> dict:
    """Every method on the same scored pixels; writes data/streets/results.json."""
    towns = load_towns(zones_dir)
    tid = town_grid(towns).ravel()
    valid = (load_grid("dtm5") != DTM_NODATA).ravel()
    water = load_grid("water5").astype(bool).ravel()
    products = ems_products(zones_dir)
    analysed = np.logical_or.reduce([p["analysed"] for p in products]).ravel()
    scored = (tid > 0) & analysed & ~water & valid
    idx = np.flatnonzero(scored)
    n = idx.size
    town_s = tid[idx]
    print(f"scored pixels: {n} ({n * 25 / 1e4:.1f} ha)", flush=True)

    # references on the scored pixels
    fa = np.logical_or.reduce([p["flooded_area"] for p in products]).ravel()
    ft = np.logical_or.reduce([p["flood_trace"] for p in products]).ravel() & ~fa
    decided = np.zeros(fa.size, dtype=bool)
    lb = np.zeros(fa.size, dtype=bool)
    for p in products:  # sharpest map first
        region = p["analysed"].ravel() & ~decided
        lb |= (p["flooded_area"].ravel() | p["flood_trace"].ravel()) & region
        decided |= region
    del products, decided
    refs = {"flooded_area": fa[idx], "flood_trace": ft[idx], "observed": (fa | ft)[idx], "lb_observed": lb[idx],
            "icv": burn(icv_layer("footprint").geometry).ravel()[idx]}
    zone_full = zone_grids(zones_dir)
    inside = tid > 0
    # the same sums on every cell of the municipalities (permanent water included), to compare with PR #36
    in_munis = {
        "municipalities_ha": round(int(inside.sum()) * 25 / 1e4, 1),
        "observed_ha": round(int(((fa | ft) & inside).sum()) * 25 / 1e4, 1),
        "flood_trace_ha": round(int((ft & inside).sum()) * 25 / 1e4, 1),
        "flooded_area_ha": round(int((fa & inside).sum()) * 25 / 1e4, 1),
        "lower_bound_observed_ha": round(int((lb & inside).sum()) * 25 / 1e4, 1),
        "union_zone_pct_of_municipalities": pct(int((zone_full["union"].ravel() & inside).sum()), int(inside.sum())),
        "observed_ha_by_town": {t: round(int(((fa | ft) & (tid == i + 1)).sum()) * 25 / 1e4, 1)
                                for i, t in enumerate(TOWNS)},
    }
    del fa, ft, lb
    zones = {k: v.ravel()[idx] for k, v in zone_full.items()}
    del zone_full

    pos_of = np.full(tid.size, -1, dtype=np.int64)
    pos_of[idx] = np.arange(n)
    bld = graded_buildings(zones_dir, towns)
    b_cell_ok = bld["cell"] >= 0
    b_pos_all = np.where(b_cell_ok, pos_of[np.where(b_cell_ok, bld["cell"], 0)], -1)
    marks = water_marks()
    m_ok = marks["cell"] >= 0
    m_pos_all = np.where(m_ok, pos_of[np.where(m_ok, marks["cell"], 0)], -1)
    in_b = b_pos_all >= 0
    in_m = m_pos_all >= 0
    b_pos = b_pos_all[in_b]
    m_pos = m_pos_all[in_m]
    town_names = np.array(TOWNS)
    b_town = town_names[town_s[b_pos] - 1]  # the town of the building's cell (same pixels as everything else)

    # terrain rasters on the scored pixels
    hand_files = {
        "bare": "hand_bare_d0p5km2", "bare_d0p05": "hand_bare_d0p05km2", "bare_d5": "hand_bare_d5km2",
        "bldg": "hand_bldg_d0p5km2", "lake": "hand_lake_d0p5km2",
    }
    hand = {k: load_grid(f).ravel()[idx] for k, f in hand_files.items() if (TERRAIN_DIR / f"{f}.tif").exists()}
    upa = {v: load_grid(f"upa_{v}").ravel()[idx] for v in ("bare", "bldg", "lake")
           if (TERRAIN_DIR / f"upa_{v}.tif").exists()}
    upa_of = {k: upa[k if k in ("bldg", "lake") else "bare"] for k in hand}

    # methods: boolean selections over the scored pixels
    methods: dict[str, np.ndarray] = {}
    describe: dict[str, str] = {}
    for z in ZONE_NAMES:
        methods[f"official_{z}"] = zones[z]
        describe[f"official_{z}"] = f"Method 1: SNCZI {z if z != 'union' else 'union of T10, T100 and T500'} as mapped"
    for k, h in hand.items():
        methods[f"terrain_{k}_hand_below_15m"] = np.isfinite(h) & (h < HAND_NATIVE_M)
        describe[f"terrain_{k}_hand_below_15m"] = f"Method 2 ({k}): HAND below {HAND_NATIVE_M:g} m (Twele et al. 2016)"
    town_pos = {t: np.flatnonzero(town_s == i + 1) for i, t in enumerate(TOWNS)}
    for k, h in hand.items():
        orders = {t: ranked(h, upa_of[k], p) for t, p in town_pos.items()}
        for z in ZONE_NAMES:
            sel = np.zeros(n, dtype=bool)
            for t, p in town_pos.items():
                sel[orders[t][:int(zones[z][p].sum())]] = True
            name = f"terrain_{k}_equal_area_{z}"
            methods[name] = sel
            describe[name] = (f"Method 3 ({k}): lowest HAND cells of each town, as many as the town's "
                              f"cells in the official {z} area")
        pooled = ranked(h, upa_of[k], np.arange(n))
        name = f"terrain_{k}_equal_area_union_pooled"
        methods[name] = first_k(pooled, int(zones["union"].sum()), n)
        describe[name] = f"Method 3 ({k}), pooled: lowest HAND cells of the 10 towns together, union area"

    sim_dir = INTERIM_DIR / "simulation"
    simulation = None
    if (sim_dir / "sim_hmax_25m.tif").exists():
        f = int(SIM_CELL_M // CELL_M)
        hm = load_grid("sim_hmax_25m", folder=sim_dir)
        hm5 = np.repeat(np.repeat(hm, f, axis=0), f, axis=1).ravel()[idx]
        del hm
        neg = -hm5.astype(np.float64)  # deepest first
        sim_orders = {t: ranked(neg, upa["bare"], p) for t, p in town_pos.items()}
        for z in ZONE_NAMES:
            sel = np.zeros(n, dtype=bool)
            for t, p in town_pos.items():
                sel[sim_orders[t][:int(zones[z][p].sum())]] = True
            name = f"simulated_rain_equal_area_{z}"
            methods[name] = sel
            describe[name] = (f"Method 4, SIMULATED: deepest simulated cells of each town (25 m run), as many as "
                              f"the town's cells in the official {z} area")
        simulation = json.loads((sim_dir / "simulation_info.json").read_text(encoding="utf-8"))
        simulation["wet_share_of_scored_pct"] = pct(int((hm5 > 0.0).sum()), n)

    # per town: the references, buildings and water marks on its own pixels (computed once)
    town_refs, town_b, town_m = {}, {}, {}
    lp = np.full(n, -1, dtype=np.int64)
    for t, p in town_pos.items():
        town_refs[t] = {r: v[p] for r, v in refs.items()}
        lp[p] = np.arange(p.size)
        tb = lp[b_pos[b_town == t]]
        tm = lp[m_pos[town_s[m_pos] == TOWNS.index(t) + 1]]
        town_b[t], town_m[t] = tb[tb >= 0], tm[tm >= 0]
        lp[p] = -1

    results = {}
    for name, sel in methods.items():
        block = {"what": describe[name], "total": metrics(sel, refs, b_pos, m_pos), "towns": {}}
        for t, p in town_pos.items():
            block["towns"][t] = metrics(sel[p], town_refs[t], town_b[t], town_m[t])
        results[name] = block
        tot = block["total"]
        print(f"{name}: area {tot['area_pct_of_scored']} %, buildings {tot['buildings_covered_pct']} %, "
              f"traces {tot['flood_trace_covered_pct']} %, own area flooded {tot['own_area_flooded_pct']} %",
              flush=True)

    # diagnostics: how high above the nearest drainage the water stood (bare terrain HAND)
    hb = hand["bare"]
    eq = methods["terrain_bare_equal_area_union"]

    def hand_stats(values: np.ndarray) -> dict | None:
        v = values[np.isfinite(values)]
        if v.size == 0:
            return None
        q = np.percentile(v, [25, 50, 75, 90])
        return {"n": int(values.size), "p25_m": round(float(q[0]), 2), "median_m": round(float(q[1]), 2),
                "p75_m": round(float(q[2]), 2), "p90_m": round(float(q[3]), 2),
                "share_below_1m_pct": pct(int((v < 1).sum()), v.size), "share_below_3m_pct": pct(int((v < 3).sum()), v.size),
                "share_15m_or_more_pct": pct(int((v >= 15).sum()), v.size)}

    diagnostics = {"what": "HAND (bare terrain, drainage above 0.5 km2) of the flooded cells, the flood traces, the "
                           "graded buildings and all scored cells, and the HAND at which the equal-area cut stops",
                   "towns": {}}
    # descriptive, not a method: how much land the terrain ranking (bare, per town) needs to catch as
    # much as the official union does. Each town's budget is scaled by one factor f (capped at the town).
    k_town = {t: int(zones["union"][p].sum()) for t, p in town_pos.items()}
    entry = np.full(n, np.inf)
    for t, p in town_pos.items():
        if k_town[t] > 0:
            entry[ranked(hb, upa["bare"], p)] = (np.arange(p.size) + 1) / k_town[t]

    def land_for(target_pct: float, entries: np.ndarray) -> dict:
        e = np.sort(entries)
        need = int(np.ceil(target_pct / 100.0 * e.size))
        f = float(e[max(need - 1, 0)]) if e.size else float("nan")
        land = sum(min(f * k_town[t], p.size) for t, p in town_pos.items())
        return {"budget_factor": round(f, 2), "land_pct_of_scored": pct(land, n),
                "official_union_land_pct_of_scored": pct(sum(k_town.values()), n)}

    off_tot = results["official_union"]["total"]
    diagnostics["land_needed_for_the_official_hit_rate"] = {
        "what": "descriptive only: the terrain ranking (bare HAND, per town) with every town's budget scaled by "
                "the same factor until it catches as much as the official union",
        "buildings": {"target_pct": off_tot["buildings_covered_pct"], **land_for(off_tot["buildings_covered_pct"], entry[b_pos])},
        "flood_traces": {"target_pct": off_tot["flood_trace_covered_pct"],
                         **land_for(off_tot["flood_trace_covered_pct"], entry[refs["flood_trace"]])},
    }
    for t, p in [*town_pos.items(), ("total", np.arange(n))]:
        bp = b_pos if t == "total" else b_pos[b_town == t]
        cut = hb[p][eq[p]]
        low = np.isfinite(hb[p]) & (hb[p] < 3.0)
        diagnostics["towns"][t] = {
            "land_hand_below_3m_ha": round(int(low.sum()) * 25 / 1e4, 1),
            "land_hand_below_3m_observed_flooded_pct": pct(int((low & refs["observed"][p]).sum()), int(low.sum())),
            "observed_flood": hand_stats(hb[p][refs["observed"][p]]),
            "flood_traces": hand_stats(hb[p][refs["flood_trace"][p]]),
            "graded_buildings": hand_stats(hb[bp]),
            "all_scored": hand_stats(hb[p]),
            "equal_area_cut_stops_at_hand_m": round(float(np.nanmax(cut)), 2) if cut.size and np.isfinite(cut).any() else None,
        }

    scored_by_town = {t: {"cells": int(p.size), "ha": round(p.size * 25 / 1e4, 1),
                          "observed_ha": round(int(refs["observed"][p].sum()) * 25 / 1e4, 1),
                          "flood_trace_ha": round(int(refs["flood_trace"][p].sum()) * 25 / 1e4, 1),
                          "union_zone_ha": round(int(zones["union"][p].sum()) * 25 / 1e4, 1),
                          "graded_buildings": int((b_town == t).sum())}
                      for t, p in town_pos.items()}
    checks = {
        "rasters_on_every_cell_of_the_municipalities": in_munis,
        "graded_buildings_in_towns": int(bld["cell"].size),
        "graded_buildings_on_scored_pixels": int(b_pos.size),
        "water_marks_read": marks["points_read"], "water_marks_above_0m": marks["points_above_0"],
        "water_marks_on_scored_pixels": int(m_pos.size),
        "water_marks_on_scored_pixels_by_layer": {k: int((marks["layer"][in_m] == k).sum()) for k in WATER_MARK_LAYERS},
        "observed_ha_on_scored_pixels": round(int(refs["observed"].sum()) * 25 / 1e4, 1),
        "flood_trace_ha_on_scored_pixels": round(int(refs["flood_trace"].sum()) * 25 / 1e4, 1),
        "flooded_area_ha_on_scored_pixels": round(int(refs["flooded_area"].sum()) * 25 / 1e4, 1),
        "union_zone_ha_on_scored_pixels": round(int(zones["union"].sum()) * 25 / 1e4, 1),
        "generalitat_footprint_ha_on_scored_pixels": round(int(refs["icv"].sum()) * 25 / 1e4, 1),
        "scored_pixels_without_hand": {k: int((~np.isfinite(h)).sum()) for k, h in hand.items()},
        "note_without_hand": "cells whose flow path leaves the grid before it meets a drainage cell; "
                             "they rank last in the equal-area cut and are never flood-prone in method 2",
    }
    if zones_json is not None and zones_json.exists():
        z = json.loads(zones_json.read_text(encoding="utf-8"))["events"]["dana_2024_horta_sud"]
        checks["pr36_exact_geometry"] = {
            "source": "data/zones/zones_vs_floods.json (PR #36), events.dana_2024_horta_sud",
            "observed_ha": z["total"]["flooded_ha"],
            "flood_trace_ha": z["total"]["by_observed_class"]["flood_trace"]["flooded_ha"],
            "flooded_area_ha": z["total"]["by_observed_class"]["flooded_area"]["flooded_ha"],
            "lower_bound_observed_ha": z.get("sensitivity", {}).get("sharpest_map_first", {}).get("total", {})
            .get("flooded_ha"),
            "graded_buildings": z["graded_buildings"]["total"]["buildings"],
            "observed_ha_by_town": {mu["name"]: mu["flooded_ha"] for mu in z["municipalities"]}
            if isinstance(z.get("municipalities"), list) and z["municipalities"] and "name" in z["municipalities"][0]
            else None,
        }
    out = {
        "title": "Terrain flow (HAND, no training) against the official flood zones, DANA of 29 Oct 2024, "
                 "10 towns of L'Horta Sud and Chiva",
        "note": SI_LINE,
        "created_utc": _now(),
        "rules": "docs/STREETS.md, section Rules (committed before any score: git log docs/STREETS.md)",
        "grid": {"crs": CRS, "cell_m": CELL_M, "bounds": list(GRID_BOUNDS)},
        "scored_pixels": {"cells": int(n), "ha": round(n * 25 / 1e4, 1), "towns": scored_by_town,
                          "rule": "cell centre in one of the 10 municipalities, in the area at least one EMSR773 "
                                  "product analysed, not permanent water (ESA WorldCover 2021 class 80)"},
        "checks": checks,
        "methods": results,
        "diagnostics": diagnostics,
        "simulation": simulation,
        "inputs": input_files(zones_dir),
    }
    STREETS_DIR.mkdir(parents=True, exist_ok=True)
    path = STREETS_DIR / "results.json"
    if path.exists():  # keep the depth estimates of the depth step
        old = json.loads(path.read_text(encoding="utf-8"))
        if "flood_depth" in old:
            out["flood_depth"] = old["flood_depth"]
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path}")
    return out


def input_files(zones_dir: Path) -> dict:
    """What every number rests on: the downloads (with URLs and checksums) and the derived rasters."""
    manifest = load_manifest()
    zones_manifest = zones_dir / "manifest.json"
    terrain_info = TERRAIN_DIR / "terrain_info.json"
    return {
        "downloads": manifest,
        "pipeline_zones_downloads": json.loads(zones_manifest.read_text(encoding="utf-8")) if zones_manifest.exists() else None,
        "terrain": json.loads(terrain_info.read_text(encoding="utf-8")) if terrain_info.exists() else None,
        "derived_rasters": sorted(p.relative_to(DATA_DIR.parent).as_posix() for p in TERRAIN_DIR.glob("*.tif")),
    }


# ---------------------------------------------------------------- rain on terrain (SIMULATED)

SIM_CELL_M = 25.0
SIM_N_MANNING = 0.05
SIM_START_LOCAL = "2024-10-29T05:00"   # start of PH06 (rain of 05:01 to 06:00)
SIM_HOURS = 25                         # to 30 Oct 06:00 local
# Perez Cueva et al. (2025), Investigaciones Geograficas 84, Tables 5 and 6: hourly rain volumes
# (hm3) reconstructed from AEMET, AVAMET, SAIH-CHJ, IVIA and other gauges, hours PH06 to PH24
# (PHnn = rain of the hour before nn:00, official time).
RAIN_TABLE = {
    "poyo_upstream_of_gauge": {
        "table": "Table 6, Poyo hasta Aforo", "area_km2": 183.0,
        "hm3": [0.1, 0.9, 3.5, 7.4, 4.4, 2.1, 0.2, 0.2, 0.2, 0.7, 3.5, 6.6, 12.4, 10.3, 13.0, 5.9, 3.8, 3.4, 0.4]},
    "poyo_gauge_to_apex": {
        "table": "Table 6, Poyo post Aforo", "area_km2": 168.5,
        "hm3": [0.2, 0.7, 2.7, 4.7, 1.3, 0.5, 0.0, 0.0, 0.0, 0.4, 4.8, 11.2, 16.5, 16.3, 6.8, 0.2, 0.2, 1.6, 0.3]},
    "possalet_saleta": {
        "table": "Table 5, Possalet-Saleta", "area_km2": 74.6,
        "hm3": [0.0, 0.1, 0.4, 0.2, 0.2, 0.1, 0.0, 0.0, 0.0, 0.0, 0.6, 1.7, 3.2, 2.4, 0.8, 0.0, 0.0, 0.0, 0.2]},
}
POYO_APEX_KM2 = 351.5  # Table 6, "Poyo en Torrent": the Poyo up to its fan apex between Torrent and Picanya
GAUGE_CHECK = {"q_m3s": 2282.9, "time_local": "18:55",
               "source": "CHJ, Informe del episodio de lluvias y avenidas del 28 de octubre al 4 de noviembre de "
                         "2024 (15 Jan 2025), table 2.1, Rambla del Poyo at the A-3, Riba-roja: last reading "
                         "before the sensor was lost"}


def rain_zones(rec: np.ndarray, upa: np.ndarray) -> dict:
    """The three rain zones on the 5 m flow directions, from the documented sub-basin areas.

    Gauge: the cell of the Poyo-Pozalet-Saleta catchment (ICV) whose upstream area is
    closest to 183.0 km2. Apex: on the gauge's flow path, the cell closest to 351.5 km2.
    Saleta: outside the apex catchment, the catchment cell closest to 74.6 km2.
    """
    from pipeline.terrain_flow import follow_to, upstream_of

    cat = icv_layer("catchments")
    basin = burn(cat.geometry[cat["cod_cuenca"].astype(str).str.strip() == "29"]).ravel()
    u = upa.ravel().astype(np.float64)

    def closest(mask: np.ndarray, km2: float) -> int:
        cand = np.flatnonzero(mask)
        return int(cand[np.argmin(np.abs(u[cand] - km2 * 1e6))])

    gauge = closest(basin, RAIN_TABLE["poyo_upstream_of_gauge"]["area_km2"])
    path = [gauge]
    while rec[path[-1]] >= 0 and len(path) < 200000:
        path.append(int(rec[path[-1]]))
    path = np.array(path)
    apex = int(path[np.argmin(np.abs(u[path] - POYO_APEX_KM2 * 1e6))])
    up_gauge = upstream_of(rec, gauge)
    up_apex = upstream_of(rec, apex)
    saleta = closest(basin & ~up_apex, RAIN_TABLE["possalet_saleta"]["area_km2"])
    up_saleta = upstream_of(rec, saleta)
    del follow_to
    cols = grid_shape()[1]

    def where(cell: int) -> dict:
        r, c = divmod(cell, cols)
        return {"x": GRID_BOUNDS[0] + (c + 0.5) * CELL_M, "y": GRID_BOUNDS[3] - (r + 0.5) * CELL_M,
                "upstream_km2": round(u[cell] / 1e6, 2)}

    zones = {"poyo_upstream_of_gauge": up_gauge, "poyo_gauge_to_apex": up_apex & ~up_gauge,
             "possalet_saleta": up_saleta & ~up_apex}
    info = {"gauge_cell": where(gauge), "apex_cell": where(apex), "saleta_cell": where(saleta),
            "zone_km2": {k: round(int(v.sum()) * CELL_M * CELL_M / 1e6, 1) for k, v in zones.items()}}
    return {"masks": zones, "info": info}


def simulate(numba_python: Path | None = None) -> dict:
    """Rain on terrain at 25 m (SIMULATED); scored at equal area like method 3; written into results.json."""
    import subprocess

    from pipeline import terrain_flow as tf

    # the lake-only routing: WorldCover ponds are not sinks (one on the Poyo near Cheste drains 157.6 km2)
    rec = tf.receivers(load_grid("code_lake"))
    upa = load_grid("upa_lake")
    zones = rain_zones(rec, upa)
    print(json.dumps(zones["info"], indent=1), flush=True)
    del rec
    f = int(SIM_CELL_M // CELL_M)
    z5 = load_grid("dtm5")
    z25 = block_mean(z5, f, DTM_NODATA)
    del z5
    water25 = block_mean(load_grid("lake5").astype(np.float32), f, -1.0, min_valid=1) >= 0.5
    rows, cols = z25.shape
    sinks = (z25 == DTM_NODATA) | water25
    sinks[0, :] = sinks[-1, :] = sinks[:, 0] = sinks[:, -1] = True
    z25 = np.where(z25 == DTM_NODATA, 0.0, z25)  # the sea at 0 m
    names = list(RAIN_TABLE)
    frac = np.stack([block_mean(zones["masks"][k].reshape(grid_shape()).astype(np.float32), f, -1.0, min_valid=1)
                     for k in names]).astype(np.float32)
    # 1 hm3 over 1 km2 is 1 m of water: depth (m) = hm3 / km2, spread over the hour
    rates = np.array([[v / RAIN_TABLE[k]["area_km2"] / 3600.0 for v in RAIN_TABLE[k]["hm3"]] for k in names])
    hours = len(RAIN_TABLE[names[0]]["hm3"])
    inp = {"z": z25.astype(np.float64), "sinks": sinks, "zone_frac": frac, "zone_rates": rates,
           "hour_edges_s": np.arange(hours + 1) * 3600.0, "t_end_s": SIM_HOURS * 3600.0, "dx": SIM_CELL_M,
           "n_manning": SIM_N_MANNING, "alpha": 0.7, "dt_max": 10.0, "record_every_s": 300.0,
           "gauge_mask": frac[0] >= 0.5}
    sim_dir = INTERIM_DIR / "simulation"
    sim_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(sim_dir / "inputs.npz", **inp)
    engine = "numpy (pipeline.inertial.run_numpy)"
    if numba_python is not None and numba_python.exists():
        kernel = Path(__file__).with_name("inertial_kernel.py")
        subprocess.run([str(numba_python), "-I", str(kernel), str(sim_dir / "inputs.npz"), str(sim_dir / "outputs.npz")],
                       check=True)
        out = dict(np.load(sim_dir / "outputs.npz"))
        engine = "numba (pipeline/inertial_kernel.py, same scheme as pipeline.inertial, checked in tests)"
    else:
        from pipeline.inertial import run_numpy

        out = run_numpy(inp)
        np.savez_compressed(sim_dir / "outputs.npz", **out)
    save_grid("sim_hmax_25m", out["hmax"], nodata=None, cell=SIM_CELL_M, folder=sim_dir)
    t = out["gauge_t_s"]
    q = out["gauge_q_m3s"]
    clock = lambda s: f"{(5 + int(s // 3600)) % 24:02d}:{int(s % 3600 // 60):02d}"  # noqa: E731
    i_1855 = int(np.argmin(np.abs(t - (18 * 3600 + 55 * 60 - 5 * 3600))))
    info = {
        "label": "SIMULATED",
        "engine": engine,
        "cell_m": SIM_CELL_M, "manning_n": SIM_N_MANNING, "infiltration": "none (all rain runs off: an upper bound)",
        "start_local": SIM_START_LOCAL, "hours": SIM_HOURS, "steps": int(out["steps"]),
        "wall_s": round(float(out["wall_s"]), 1),
        "rain_zones": zones["info"],
        "rain_table": {k: {**v, "total_hm3_listed_hours": round(sum(v["hm3"]), 1)} for k, v in RAIN_TABLE.items()},
        "rain_source": "Perez Cueva et al. (2025), Investigaciones Geograficas 84, 9-29, doi:10.14198/INGEO.30056, "
                       "Tables 5 and 6",
        "volumes_hm3": {"rain": round(float(out["rain_volume_m3"]) / 1e6, 2),
                        "left_at_sinks": round(float(out["sink_volume_m3"]) / 1e6, 2),
                        "on_the_ground_at_end": round(float(out["stored_volume_m3"]) / 1e6, 2)},
        "gauge_check": {
            "model_q_m3s_at_18_55": round(float(q[i_1855]), 1),
            "model_peak_q_m3s": round(float(q.max()), 1), "model_peak_time_local": clock(float(t[np.argmax(q)])),
            "observed": GAUGE_CHECK,
            "note": "a check only: nothing in the model was adjusted to it",
            "series_every_15_min": [[clock(float(a)), round(float(b), 1)] for a, b in zip(t, q)
                                    if round(float(a)) % 900 == 0],
        },
    }
    (sim_dir / "simulation_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("steps", "wall_s", "volumes_hm3", "rain_zones")}, indent=1))
    print(json.dumps({k: v for k, v in info["gauge_check"].items() if k != "series_every_15_min"}, indent=1))
    return info


# ---------------------------------------------------------------- web layers

WEB_FLOW_MIN_KM2 = 5.0  # web layer: only the larger flow paths, so the file stays small


def _write_geojson(gdf, name: str, decimals: int = 5) -> Path:
    STREETS_DIR.mkdir(parents=True, exist_ok=True)
    path = STREETS_DIR / f"{name}.geojson"
    gdf.to_crs("EPSG:4326").to_file(path, driver="GeoJSON", COORDINATE_PRECISION=decimals)
    print(f"{path.relative_to(DATA_DIR.parent)}: {path.stat().st_size / 1e6:.2f} MB, {len(gdf)} features")
    return path


def flow_path_lines(min_km2: float = WEB_FLOW_MIN_KM2):
    """D8 flow paths with an upstream area above min_km2 as merged, simplified lines."""
    import geopandas as gpd
    import shapely

    from pipeline import terrain_flow as tf

    # the lake-only routing, so the Poyo is one line from Chiva to the Albufera (display only)
    code = load_grid("code_lake")
    rec = tf.receivers(code)
    del code
    upa = load_grid("upa_lake").ravel()
    rows, cols = grid_shape()
    cells = np.flatnonzero((upa > min_km2 * 1e6) & (rec >= 0))
    dst = rec[cells]
    keep = upa[dst] > min_km2 * 1e6
    cells, dst = cells[keep], dst[keep]

    def xy(i):
        r, c = np.divmod(i, cols)
        return GRID_BOUNDS[0] + (c + 0.5) * CELL_M, GRID_BOUNDS[3] - (r + 0.5) * CELL_M

    x0, y0 = xy(cells)
    x1, y1 = xy(dst)
    # one line per class of upstream area, merged and simplified
    bins = [min_km2, 20.0, 50.0, 100.0, 200.0, 1e9]
    rows_out = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (upa[cells] >= lo * 1e6) & (upa[cells] < hi * 1e6)
        if not m.any():
            continue
        segs = shapely.linestrings(np.stack([np.stack([x0[m], y0[m]], 1), np.stack([x1[m], y1[m]], 1)], 1))
        merged = shapely.line_merge(shapely.union_all(segs))
        rows_out.append({"upstream_km2_from": lo, "upstream_km2_to": None if hi >= 1e9 else hi,
                         "geometry": shapely.simplify(merged, 7.5)})
    return gpd.GeoDataFrame(rows_out, geometry="geometry", crs=CRS)


def mask_polygons(mask: np.ndarray, value_grid: np.ndarray | None = None, simplify_m: float = 5.0, cell: float = CELL_M,
                  bounds: tuple[float, float, float, float] | None = None):
    """Polygons of a cell mask (optionally split by an integer grid), simplified."""
    import geopandas as gpd
    import shapely
    from rasterio.features import shapes

    vals = np.where(mask, value_grid if value_grid is not None else 1, 0).astype(np.int32)
    geoms, keys = [], []
    for geom, v in shapes(vals, mask=vals > 0, transform=grid_transform(cell, bounds), connectivity=4):
        geoms.append(shapely.geometry.shape(geom))
        keys.append(int(v))
    gdf = gpd.GeoDataFrame({"value": keys}, geometry=geoms, crs=CRS).dissolve(by="value", as_index=False)
    gdf["geometry"] = gdf.geometry.simplify(simplify_m, preserve_topology=True)
    return gdf


def layers(zones_dir: Path) -> None:
    """Small web layers: flow paths, the terrain map at the official zones' area, the simulated depth."""
    import geopandas as gpd

    res = json.loads((STREETS_DIR / "results.json").read_text(encoding="utf-8"))
    lines = flow_path_lines()
    lines["what"] = (f"terrain flow paths (D8 on the ICV MDT 2015 at 5 m, only water bodies of 1 km2 or more "
                     f"as sinks), upstream area above {WEB_FLOW_MIN_KM2:g} km2; drainage for HAND starts at 0.5 km2")
    _write_geojson(lines, "flow_paths")

    towns = load_towns(zones_dir)
    tid = town_grid(towns)
    valid = load_grid("dtm5") != DTM_NODATA
    water = load_grid("water5").astype(bool)
    products = ems_products(zones_dir)
    analysed = np.logical_or.reduce([p["analysed"] for p in products])
    del products
    scored = (tid > 0) & analysed & ~water & valid
    idx = np.flatnonzero(scored.ravel())
    zones = {k: v.ravel()[idx] for k, v in zone_grids(zones_dir).items()}
    hand = load_grid("hand_bare_d0p5km2").ravel()[idx]
    upa = load_grid("upa_bare").ravel()[idx]
    town_s = tid.ravel()[idx]
    sel = np.zeros(idx.size, dtype=bool)
    for i, _ in enumerate(TOWNS):
        p = np.flatnonzero(town_s == i + 1)
        sel[ranked(hand, upa, p)[:int(zones["union"][p].sum())]] = True
    grid_sel = np.zeros(tid.size, dtype=bool)
    grid_sel[idx[sel]] = True
    gdf = mask_polygons(grid_sel.reshape(tid.shape), tid)
    gdf["municipality"] = [TOWNS[v - 1] for v in gdf["value"]]
    tot = res["methods"]["terrain_bare_equal_area_union"]["towns"]
    gdf["area_ha"] = [tot[m]["area_ha"] for m in gdf["municipality"]]
    gdf["what"] = ("terrain flow map (HAND, no training): the lowest cells of each town above the nearest "
                   "drainage, as much land as the official zones (union) cover there")
    _write_geojson(gdf.drop(columns="value"), "terrain_equal_area")

    sim = INTERIM_DIR / "simulation" / "sim_hmax_25m.tif"
    if sim.exists():
        hm = load_grid("sim_hmax_25m", folder=sim.parent)
        cls = np.digitize(hm, [0.3, 1.0, 2.0]).astype(np.int32)  # 0: below 0.3 m
        bounds_cls = {1: "0.3 to 1 m", 2: "1 to 2 m", 3: "above 2 m"}
        # only around the towns and their ravines: the scored area's bounding box, 1 km margin
        rows, cols = np.nonzero(scored)
        r0, r1 = max(0, rows.min() // 5 - 40), rows.max() // 5 + 40
        c0, c1 = max(0, cols.min() // 5 - 40), cols.max() // 5 + 40
        box = np.zeros(hm.shape, dtype=bool)
        box[r0:r1, c0:c1] = True
        g = mask_polygons((cls > 0) & box, cls, simplify_m=SIM_CELL_M, cell=SIM_CELL_M)
        # drop specks smaller than 4 cells of 25 m, so the web file stays small
        parts = g.explode(index_parts=False)
        parts = parts[parts.geometry.area >= 4 * SIM_CELL_M * SIM_CELL_M]
        g = parts.dissolve(by="value", as_index=False)
        g["max_depth"] = [bounds_cls[v] for v in g["value"]]
        g["what"] = "SIMULATED maximum water depth, rain on terrain at 25 m (see docs/STREETS.md)"
        _write_geojson(g.drop(columns="value"), "simulated_max_depth")


# ---------------------------------------------------------------- report


def _cell(v) -> str:
    return "n/a" if v is None else f"{v:.1f} %"


def report() -> str:
    res = json.loads((STREETS_DIR / "results.json").read_text(encoding="utf-8"))
    m = res["methods"]
    lines = []
    off, ter = m["official_union"], m["terrain_bare_equal_area_union"]
    lines += ["Headline: the official zones (union) against the terrain map at the same area, per town.", "",
              "| Town | Land in the zones | Buildings: zones | Buildings: terrain | Flood traces: zones | "
              "Flood traces: terrain | Own area flooded: zones | Own area flooded: terrain | Own area flooded: chance |",
              "|---|---|---|---|---|---|---|---|---|"]
    for t in [*TOWNS, "total"]:
        a = off["total"] if t == "total" else off["towns"][t]
        b = ter["total"] if t == "total" else ter["towns"][t]
        nb = a["buildings"]
        lines.append(f"| {'**Total**' if t == 'total' else t} | {_cell(a['area_pct_of_scored'])} | "
                     f"{_cell(a['buildings_covered_pct'])} | {_cell(b['buildings_covered_pct'])} | "
                     f"{_cell(a['flood_trace_covered_pct'])} | {_cell(b['flood_trace_covered_pct'])} | "
                     f"{_cell(a['own_area_flooded_pct'])} | {_cell(b['own_area_flooded_pct'])} | "
                     f"{_cell(a['chance_own_area_flooded_pct'])} |" + ("" if nb else ""))
    lines += ["", "Every method, the 10 towns together:", "",
              "| Method | Area (ha) | Area (% of scored) | Buildings | Flood traces | Observed flood | Own area flooded | "
              "Generalitat footprint | Own area in footprint | Water marks |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for name, blk in m.items():
        a = blk["total"]
        lines.append(f"| `{name}` | {a['area_ha']:,.1f} | {_cell(a['area_pct_of_scored'])} | "
                     f"{_cell(a['buildings_covered_pct'])} | {_cell(a['flood_trace_covered_pct'])} | "
                     f"{_cell(a['observed_covered_pct'])} | {_cell(a['own_area_flooded_pct'])} | "
                     f"{_cell(a['generalitat_footprint_covered_pct'])} | "
                     f"{_cell(a['own_area_in_generalitat_footprint_pct'])} | {_cell(a['water_marks_covered_pct'])} |")
    text = "\n".join(lines)
    print(text)
    return text


# ---------------------------------------------------------------- flood depth, ESTIMATED from outline and terrain

DEPTH_LABEL = ("ESTIMATED from the flood outline and terrain (FwDET rule, Cohen et al. 2018), not measured; "
               "says nothing about future storms")
DEPTH_EDGES_M = (0.2, 1.0, 2.0)
DEPTH_CLASSES = ("below 0.2 m", "0.2 to 1 m", "1 to 2 m", "above 2 m")
DEPTH_DIR = INTERIM_DIR / "depth"
LABELS_DIR = DATA_DIR / "labels"
PEGO_SHEET = "0796"
PEGO_BOUNDS = (743500.0, 4301990.0, 762000.0, 4320490.0)  # inside sheet 0796; holds 99.8 % of EMSR935's outline
PEGO_TOWNS = {"Pego": "03102", "Oliva": "46181"}


def aggregate_remote(url: str, bounds: tuple[float, float, float, float], dst: Path, factor: int = 5,
                     rows_per_read: int = 2000) -> dict:
    """Average a window of a remote 1 m sheet to 5 m, reading it over HTTP (nothing is stored but the result)."""
    with rasterio.Env(GDAL_HTTP_USERAGENT=USER_AGENT, GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_CHUNK_SIZE="10485760"):
        with rasterio.open(f"/vsicurl/{url}") as src:
            t = src.transform
            nodata = src.nodata if src.nodata is not None else DTM_NODATA
            col0, row0 = int(round(bounds[0] - t.c)), int(round(t.f - bounds[3]))
            width, height = int(round(bounds[2] - bounds[0])), int(round(bounds[3] - bounds[1]))
            if col0 < 0 or row0 < 0 or col0 + width > src.width or row0 + height > src.height:
                raise RuntimeError(f"{bounds} is not inside the sheet {src.bounds}")
            out = np.full((height // factor, width // factor), DTM_NODATA, dtype=np.float32)
            for r in range(0, height, rows_per_read):
                n = min(rows_per_read, height - r)
                a = src.read(1, window=Window(col0, row0 + r, width, n))
                b = block_mean(a, factor, nodata)
                b[b == nodata] = DTM_NODATA
                out[r // factor:(r + n) // factor] = b
    save_grid(dst.stem, out, nodata=DTM_NODATA, folder=dst.parent, bounds=bounds)
    return {"window_bounds": list(bounds), "aggregation": f"mean of {factor} x {factor} cells, read remotely"}


def fetch_pego_dtm(manifest: dict) -> None:
    """The 1 m sheet 0796 (2015) around Pego-Oliva, averaged to 5 m while it is read (about 1.2 GB over HTTP)."""
    url = DTM["url"].format(sheet=PEGO_SHEET)
    head = requests.head(url, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    head.raise_for_status()
    dst = INTERIM_DIR / "dtm" / f"dtm5_2015_{PEGO_SHEET}_pego_oliva.tif"
    info = aggregate_remote(url, PEGO_BOUNDS, dst)
    raw = dst.read_bytes()
    record(manifest, f"dtm_2015_{PEGO_SHEET}_pego_oliva", url, dst, len(raw), hashlib.sha256(raw).hexdigest(),
           source_sha256_is_of="the 5 m result (the 1 m file was read remotely, not stored)",
           source_last_modified=head.headers.get("Last-Modified"), source_etag=head.headers.get("ETag"),
           source_bytes=int(head.headers.get("Content-Length", 0)), **info)
    print(f"Pego-Oliva DTM: {dst.relative_to(DATA_DIR.parent)}")


def water_marks_all() -> dict:
    """Every surveyed water height of the ICV DANA 2024 service (0 m included), with its layer."""
    import pandas as pd

    frames = []
    for key in WATER_MARK_LAYERS:
        g = icv_layer(key)
        frames.append(pd.DataFrame({"x": g.geometry.x, "y": g.geometry.y, "layer": key,
                                    "height_m": pd.to_numeric(g["altura_agua_m"], errors="coerce")}))
    return pd.concat(frames, ignore_index=True)


def depth_stats(depth: np.ndarray, where: np.ndarray, dist: np.ndarray) -> dict:
    """Area per class, depth percentiles and distance to the edge used, for the flooded cells in `where`."""
    d = depth[where & np.isfinite(depth)]
    if d.size == 0:
        return {"flooded_ha": 0.0}
    cls = np.digitize(d, DEPTH_EDGES_M)
    q = np.percentile(d, [25, 50, 75, 90, 99])
    e = dist[where & np.isfinite(depth)]
    return {
        "flooded_ha": round(d.size * CELL_M * CELL_M / 1e4, 1),
        "ha_by_class": {name: round(int((cls == i).sum()) * CELL_M * CELL_M / 1e4, 1) for i, name in enumerate(DEPTH_CLASSES)},
        "pct_by_class": {name: pct(int((cls == i).sum()), d.size) for i, name in enumerate(DEPTH_CLASSES)},
        "depth_m": {"mean": round(float(d.mean()), 2), "p25": round(float(q[0]), 2), "median": round(float(q[1]), 2),
                    "p75": round(float(q[2]), 2), "p90": round(float(q[3]), 2), "p99": round(float(q[4]), 2)},
        "distance_to_the_edge_used_m": {"median": round(float(np.median(e)), 1), "p90": round(float(np.percentile(e, 90)), 1)},
    }


def mark_errors(est: np.ndarray, meas: np.ndarray) -> dict | None:
    if est.size == 0:
        return None
    err = est - meas
    r = float(np.corrcoef(est, meas)[0, 1]) if est.size > 2 and est.std() > 0 and meas.std() > 0 else None
    return {"marks": int(est.size), "measured_median_m": round(float(np.median(meas)), 2),
            "estimated_median_m": round(float(np.median(est)), 2), "bias_m": round(float(err.mean()), 2),
            "mae_m": round(float(np.abs(err).mean()), 2), "rmse_m": round(float(np.sqrt((err ** 2).mean())), 2),
            "median_abs_error_m": round(float(np.median(np.abs(err))), 2),
            "within_0p5m_pct": pct(int((np.abs(err) <= 0.5).sum()), est.size),
            "pearson_r": None if r is None else round(r, 2)}


def depth_classes_layer(depth: np.ndarray, keep: np.ndarray, bounds=None):
    cls = np.where(np.isfinite(depth) & keep, np.digitize(np.nan_to_num(depth), DEPTH_EDGES_M) + 1, 0).astype(np.int32)
    # display only (the numbers come from the 5 m cells): simplified by 10 m, specks under 400 m2 dropped
    g = mask_polygons(cls > 0, cls, simplify_m=2 * CELL_M, bounds=bounds)
    parts = g.explode(index_parts=False)
    parts = parts[parts.geometry.area >= 16 * CELL_M * CELL_M]
    g = parts.dissolve(by="value", as_index=False)
    g["depth"] = [DEPTH_CLASSES[v - 1] for v in g["value"]]
    g["what"] = DEPTH_LABEL
    return g.drop(columns="value")


def depth(zones_dir: Path) -> dict:
    """Estimated depth of the 2024 and 2026 floods; layers in data/streets/, numbers in results.json."""
    import geopandas as gpd
    from rasterio.warp import Resampling, reproject

    from pipeline import terrain_flow as tf

    out = {"label": DEPTH_LABEL, "classes": list(DEPTH_CLASSES),
           "method": "water surface of each flooded cell = ground of its nearest flood-edge cell; depth = surface "
                     "- ground, at least 0; edges only where the flood touches mapped dry land with terrain that "
                     "is not permanent water; no smoothing (docs/STREETS.md)"}

    # 2024 DANA: EMSR773 maximum observed extent on the whole analysis grid
    dem = load_grid("dtm5")
    valid = dem != DTM_NODATA
    water = load_grid("water5").astype(bool)
    products = ems_products(zones_dir)
    analysed = np.logical_or.reduce([p["analysed"] for p in products])
    fa = np.logical_or.reduce([p["flooded_area"] for p in products])
    ft = np.logical_or.reduce([p["flood_trace"] for p in products])
    del products
    flood = (fa | ft) & valid & ~water
    del fa, ft
    est, dist, info = tf.fwdet_depth(dem, flood, valid & analysed & ~water, CELL_M)
    save_grid("depth_estimated_dana_2024", est, nodata=np.nan, folder=DEPTH_DIR)
    towns = load_towns(zones_dir)
    tid = town_grid(towns)
    in_towns = tid > 0
    y24 = {"outline": "EMSR773 maximum observed extent (flooded area plus flood traces, three products), whole grid",
           "terrain": "ICV MDT 1 m 2015 averaged to 5 m (not filled)", **info,
           "ten_towns": depth_stats(est, in_towns, dist),
           "towns": {t: depth_stats(est, tid == i + 1, dist) for i, t in enumerate(TOWNS)},
           "whole_grid": depth_stats(est, np.ones(est.shape, dtype=bool), dist)}
    marks = water_marks_all()
    cell = cells_of_points(marks["x"].to_numpy(), marks["y"].to_numpy())
    ok = cell >= 0
    m = marks[ok].assign(cell=cell[ok])
    flat_flood, flat_est, flat_tid = flood.ravel(), est.ravel(), tid.ravel()
    m = m.assign(inside=flat_flood[m["cell"]], est=flat_est[m["cell"]], town=flat_tid[m["cell"]])
    wet = m[m["height_m"] > 0]
    inside = wet[wet["inside"]]
    check = {"source": "ICV DANA2024.ZonasInundadas.AlturaAgua.* (UPV, IVE, SGRT, town halls): water heights "
                       "surveyed after the flood",
             "marks_on_the_grid": int(len(m)), "marks_above_0m": int(len(wet)),
             "marks_above_0m_inside_the_outline": int(len(inside)),
             "marks_above_0m_outside_the_outline": int((~wet["inside"]).sum()),
             "measured_median_m_of_marks_outside_the_outline": round(float(wet.loc[~wet["inside"], "height_m"].median()), 2)
             if (~wet["inside"]).any() else None,
             "all_inside": mark_errors(inside["est"].to_numpy(), inside["height_m"].to_numpy()),
             "by_survey": {k: mark_errors(g["est"].to_numpy(), g["height_m"].to_numpy())
                           for k, g in inside.groupby("layer")},
             "ten_towns_inside": mark_errors(inside.loc[inside["town"] > 0, "est"].to_numpy(),
                                             inside.loc[inside["town"] > 0, "height_m"].to_numpy())}
    zero = m[(m["height_m"] == 0) & m["inside"]]
    check["marks_at_0m_inside_the_outline"] = int(len(zero))
    check["marks_at_0m_inside_estimated_below_0p2m_pct"] = pct(int((zero["est"] < 0.2).sum()), len(zero))
    y24["check_against_water_marks"] = check
    # is the error from edges along building walls? (a check made after seeing the errors: it is not)
    bld = load_grid("buildings5").astype(bool)
    shore = valid & analysed & ~water
    edges = tf.flood_edges(flood, shore)
    edges_not_walls = tf.flood_edges(flood, shore & ~bld)
    y24["edges_in_the_ten_towns"] = {
        "edge_cells": int((edges & in_towns).sum()),
        "touching_only_building_cells_pct": pct(int((edges & ~edges_not_walls & in_towns).sum()),
                                                int((edges & in_towns).sum())),
        "flooded_cells_on_building_footprints_pct": pct(int((flood & bld & in_towns).sum()), int((flood & in_towns).sum())),
        "note": "checked after seeing the errors; building walls are not the main source of error"}
    del bld, edges, edges_not_walls
    out["dana_2024_horta_sud"] = y24
    lay = depth_classes_layer(est, in_towns)
    a_ = check["all_inside"]
    lay["check"] = (f"against {a_['marks']} surveyed water marks inside the outline: median {a_['estimated_median_m']} m "
                    f"estimated, {a_['measured_median_m']} m measured, mean absolute error {a_['mae_m']} m; "
                    f"not reliable street by street")
    _write_geojson(lay, "estimated_depth_dana_2024")
    del dem, valid, water, analysed, flood, est, dist

    # 2026 DANA Adam, Pego-Oliva: EMSR935 on sheet 0796
    dem_path = INTERIM_DIR / "dtm" / f"dtm5_2015_{PEGO_SHEET}_pego_oliva.tif"
    with rasterio.open(dem_path) as src:
        dem_p = src.read(1)
    valid_p = dem_p != DTM_NODATA
    wc = np.zeros(dem_p.shape, dtype=np.uint8)
    with rasterio.open(DATA_DIR / "context" / "pego_oliva_worldcover_2021_20m.tif") as src:
        reproject(src.read(1), wc, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=grid_transform(CELL_M, PEGO_BOUNDS), dst_crs=CRS, resampling=Resampling.nearest)
    water_p = wc == WORLDCOVER_WATER
    fl = gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_flood.geojson").to_crs(CRS)
    aoi = gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_aoi.geojson").to_crs(CRS)
    flood_p = burn(fl.geometry, bounds=PEGO_BOUNDS) & valid_p & ~water_p
    mapped = burn(aoi.geometry, bounds=PEGO_BOUNDS)
    est_p, dist_p, info_p = tf.fwdet_depth(dem_p, flood_p, valid_p & mapped & ~water_p, CELL_M)
    save_grid("depth_estimated_dana_adam_2026", est_p, nodata=np.nan, folder=DEPTH_DIR, bounds=PEGO_BOUNDS)
    full = gpd.GeoSeries(fl.geometry, crs=CRS).union_all()
    inside_box = gpd.GeoSeries([full], crs=CRS).clip(PEGO_BOUNDS).area.sum()
    ign = json.loads((zones_dir / "ign_pego_oliva.geojson").read_text(encoding="utf-8"))
    feats = {f["id"]: f for f in ign["features"]}
    from shapely.geometry import shape as _shape

    pego_munis = gpd.GeoDataFrame(
        [{"name": n, "geometry": _shape(feats[f"AU_ADMINISTRATIVEUNIT_3410{c[:2]}{c}"]["geometry"])}
         for n, c in PEGO_TOWNS.items()], crs="EPSG:4258").to_crs(CRS)
    y26 = {"outline": "EMSR935 (data/labels/pego_oliva_emsr935_flood.geojson), flooded area plus flood traces",
           "terrain": f"ICV MDT 1 m 2015 sheet {PEGO_SHEET} averaged to 5 m (not filled)",
           "outline_ha": round(float(full.area) / 1e4, 1),
           "outline_inside_the_terrain_box_pct": pct(float(inside_box), float(full.area)), **info_p,
           "whole_box": depth_stats(est_p, np.ones(est_p.shape, dtype=bool), dist_p),
           "towns": {r["name"]: depth_stats(est_p, burn([r.geometry], bounds=PEGO_BOUNDS), dist_p)
                     for _, r in pego_munis.iterrows()}}
    pts = gpd.read_file(LABELS_DIR / "pego_oliva_water_depth_points.geojson").to_crs(CRS)
    h = gpd.pd.to_numeric(pts["AlturaAguam"], errors="coerce")
    inside_pts = pts.within(full)
    near = pts.distance(full) <= 50.0
    y26["check_against_water_marks"] = {
        "source": "ICV 2702_DANAAdam2026 surveyed water depths (data/labels/pego_oliva_water_depth_points.geojson, "
                  "SGRT)", "marks": int(len(pts)), "marks_above_0m": int((h > 0).sum()),
        "inside_the_outline": int(inside_pts.sum()), "within_50m_of_the_outline": int(near.sum()),
        "result": "no check: no surveyed mark lies inside the EMSR935 outline" if not inside_pts.any() else None}
    out["dana_adam_2026_pego_oliva"] = y26
    lay26 = depth_classes_layer(est_p, np.ones(est_p.shape, dtype=bool), PEGO_BOUNDS)
    lay26["check"] = "no check: no surveyed water mark lies inside the EMSR935 outline"
    _write_geojson(lay26, "estimated_depth_dana_adam_2026")

    path = STREETS_DIR / "results.json"
    res = json.loads(path.read_text(encoding="utf-8"))
    res["flood_depth"] = out
    path.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in y24.items() if k in ("ten_towns", "check_against_water_marks")}, indent=1))
    print(json.dumps({k: v for k, v in y26.items() if k in ("whole_box", "check_against_water_marks")}, indent=1))
    return out


STEPS = ("fetch", "fetch-dtm", "fetch-other", "fetch-pego", "terrain", "simulate", "score", "layers", "depth",
         "report")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline.streets", description=__doc__.split("\n\n")[0])
    parser.add_argument("step", choices=STEPS)
    parser.add_argument("--no-variants", action="store_true", help="terrain: skip the buildings variant")
    parser.add_argument("--only", choices=["lake"], default=None,
                        help="terrain: run only the lake-only routing (after the main terrain step)")
    parser.add_argument("--zones-interim", type=Path, default=ZONES_INTERIM_DIR,
                        help="downloads of pipeline.zones (PR #36): municipalities, SNCZI, EMSR773")
    parser.add_argument("--zones-json", type=Path, default=DATA_DIR / "zones" / "zones_vs_floods.json",
                        help="PR #36 results, for the cross-check of areas")
    parser.add_argument("--numba-python", type=Path, default=INTERIM_DIR / "venv-numba" / "Scripts" / "python.exe",
                        help="simulate: an interpreter with numpy and numba (else the slow numpy version runs)")
    args = parser.parse_args(argv)
    manifest = load_manifest()
    if args.step == "fetch":
        fetch(manifest)
    elif args.step == "fetch-dtm":
        fetch_dtm(manifest)
    elif args.step == "fetch-other":
        for fn in (fetch_icv, fetch_catastro, fetch_worldcover, fetch_rain_sources):
            fn(manifest)
            save_manifest(manifest)
    elif args.step == "terrain":
        terrain(variants=not args.no_variants, only=args.only)
    elif args.step == "score":
        score(args.zones_interim, args.zones_json)
    elif args.step == "simulate":
        simulate(args.numba_python)
    elif args.step == "layers":
        layers(args.zones_interim)
    elif args.step == "fetch-pego":
        fetch_pego_dtm(manifest)
        save_manifest(manifest)
    elif args.step == "depth":
        depth(args.zones_interim)
    elif args.step == "report":
        report()


if __name__ == "__main__":
    main()
