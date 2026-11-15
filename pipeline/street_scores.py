"""Street by street: which method pointed to the streets that really flooded in the 2024 DANA.

DANA of 29 Oct 2024, the 10 towns of pipeline.streets (L'Horta Sud and Chiva).
OpenStreetMap streets as they were on 28 Oct 2024 are cut into pieces of about
25 m; each piece is judged by two answer keys (EMSR773 observed flood or a
surveyed water mark within 10 m; the UPV street depth map) and flagged or not
by each method of PR #39 (official zones, terrain, the SIMULATED run). The
rules are in docs/STREETS.md, section "Street by street", committed before any
score was computed.

Steps (in this order):
    python -m pipeline.street_scores fetch     # OSM streets (Overpass, 28 Oct 2024) and the UPV depth map (WCS)
    python -m pipeline.street_scores score     # pieces, keys, methods, metrics: into data/streets/results.json
    python -m pipeline.street_scores report    # the tables of docs/STREETS.md, printed from results.json

Needs the rasters of `python -m pipeline.streets terrain` and `simulate` (in
data/interim/streets/) and the downloads of pipeline.zones (PR #36).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import requests

from pipeline.config import DATA_DIR
from pipeline.streets import (
    CELL_M,
    CRS,
    GRID_BOUNDS,
    INTERIM_DIR,
    SI_LINE,
    STREETS_DIR,
    TOWNS,
    ZONES_INTERIM_DIR,
    _now,
    grid_shape,
    grid_transform,
    load_manifest,
    load_towns,
    save_grid,
    save_manifest,
)

OSM_DIR = INTERIM_DIR / "osm"
UPV_DIR = INTERIM_DIR / "upv"
USER_AGENT = "sar-pipeline street-scores (research, NASA Space Apps 2026)"

# ---------------------------------------------------------------- OpenStreetMap

# The street network as it was the day before the flood (Overpass attic query).
OSM_DATE = "2024-10-28T00:00:00Z"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
OSM_MARGIN_DEG = 0.002  # about 200 m around each municipality's bounding box


def overpass_query(bbox: tuple[float, float, float, float], date: str = OSM_DATE) -> str:
    """Every way tagged highway in a lon/lat box, as mapped on `date`, with its tags and geometry."""
    w, s, e, n = bbox
    return f'[out:json][timeout:900][date:"{date}"];way["highway"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});out tags geom;'


def fetch_osm(manifest: dict, zones_dir: Path) -> None:
    """One Overpass request per municipality box (raw JSON in data/interim/streets/osm/)."""
    towns = load_towns(zones_dir).to_crs("EPSG:4326")
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    for name, ine, geom in zip(towns["name"], towns["ine"], towns.geometry):
        path = OSM_DIR / f"highways_{ine}.json"
        key = f"osm_highways_{ine}"
        if path.exists() and key in manifest:
            print(f"{name}: have {path.name}", flush=True)
            continue
        w, s, e, n = geom.bounds
        bbox = (w - OSM_MARGIN_DEG, s - OSM_MARGIN_DEG, e + OSM_MARGIN_DEG, n + OSM_MARGIN_DEG)
        query = overpass_query(bbox)
        last = None
        for attempt in range(6):
            url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
            t0 = time.time()
            try:
                resp = requests.post(url, data={"data": query}, timeout=1200, headers={"User-Agent": USER_AGENT})
                if resp.status_code == 200 and resp.content.lstrip().startswith(b"{"):
                    doc = resp.json()
                    if "remark" in doc and "error" in str(doc["remark"]).lower():
                        raise RuntimeError(doc["remark"])
                    break
                last = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last = repr(exc)
            print(f"{name}: attempt {attempt + 1} at {url} failed ({last}), retrying", flush=True)
            time.sleep(20 + 20 * attempt)
        else:
            raise RuntimeError(f"Overpass failed for {name}: {last}")
        path.write_bytes(resp.content)
        manifest[key] = {
            "url": url, "query": query, "osm_date": OSM_DATE, "town": name,
            "file": path.relative_to(DATA_DIR.parent).as_posix(), "bytes": len(resp.content),
            "sha256": hashlib.sha256(resp.content).hexdigest(), "retrieved_utc": _now(),
            "ways": len(doc.get("elements", [])), "osm3s": doc.get("osm3s"), "seconds": round(time.time() - t0, 1),
            "licence": "ODbL 1.0, (c) OpenStreetMap contributors",
        }
        save_manifest(manifest)
        print(f"{name}: {manifest[key]['ways']} ways, {len(resp.content) / 1e6:.1f} MB, "
              f"{manifest[key]['seconds']} s", flush=True)


# ---------------------------------------------------------------- UPV street depth map

UPV = {
    "title": "Mapa d'inundació carrer a carrer de l'Horta Sud 2024 (maximum water depth, 29 Oct 2024)",
    "publisher": "Grup de Cartografia GeoAmbiental i Teledetecció (CGAT), Universitat Politècnica de València",
    "viewer": "https://dana2024.upvusig.car.upv.es",
    "news": "https://www.upv.es/noticias-upv/noticia-15013-mapa-de-inunda-en.html",
    "wms": "https://dana2024.gisserver.car.upv.es/geoserver/dana2024/wms",
    "wcs": "https://dana2024.gisserver.car.upv.es/geoserver/dana2024/wcs",
    "wfs": "https://dana2024.gisserver.car.upv.es/geoserver/dana2024/wfs",
    "coverage": "dana2024__H_lamina",
    "coverage_note": "water depth with buildings not masked (the viewer's 'Altura làmina (sense retallar edificis)'); "
                     "the default layer H_lamina_sense_edificis is the same surface with building footprints removed",
    "outlines": {"cgat": "dana2024:Delimitació CGAT", "extra": "dana2024:delimitació zona extra"},
    "version": "result updated 05/11/2026; 6,483 field points updated 20/06/2026 (viewer text)",
    "method": "flood marks measured with a staff on walls (Nov 2024 and May 2025), turned into water levels on the "
              "2023 LiDAR terrain (IGN, 3rd coverage), interpolated into a water surface, minus the terrain",
    "cite": "Roch Talens, A., Pardo-Pascual, J. E., Almonacid-Caballer, J., Fernández-Sarría, A., Palomar-Vázquez, "
            "J., Cabezas-Rabadán, C. (2025): Mapa de calados máximos de las inundaciones del 29 de octubre de 2024 en "
            "l'Horta Sud y la Ribera, Cuadernos de Geografía 114-115: 347-374, doi:10.7203/CGUV.114-15.32144",
    "licence": "no licence named; the viewer says 'The data are freely available through the WMS server' and asks to "
               "cite the article above; the GeoServer capabilities (WMS, WCS, WFS) say Fees NONE, AccessConstraints "
               "NONE. Used here for derived numbers only; the raster is not redistributed (it stays in "
               "data/interim, not in git)",
}
UPV_TILE_M = 1000.0
UPV_PIXEL_M = 0.5


def upv_outlines(manifest: dict) -> dict:
    """The surveyed area (red, CGAT) and the extra zones (blue) of the UPV map, as GeoJSON in EPSG:25830."""
    UPV_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for key, type_name in UPV["outlines"].items():
        params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": type_name,
                  "outputFormat": "application/json", "srsName": CRS}
        resp = requests.get(UPV["wfs"], params=params, timeout=300, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        path = UPV_DIR / f"outline_{key}.geojson"
        path.write_bytes(resp.content)
        manifest[f"upv_outline_{key}"] = {"url": resp.url, "file": path.relative_to(DATA_DIR.parent).as_posix(),
                                          "bytes": len(resp.content), "sha256": hashlib.sha256(resp.content).hexdigest(),
                                          "retrieved_utc": _now()}
        out[key] = path
    return out


def load_upv_outline():
    """Union of the UPV outlines (surveyed area and extra zones), EPSG:25830."""
    import shapely
    from shapely.geometry import shape

    geoms = []
    for key in UPV["outlines"]:
        doc = json.loads((UPV_DIR / f"outline_{key}.geojson").read_text(encoding="utf-8"))
        geoms += [shape(f["geometry"]) for f in doc["features"]]
    return shapely.union_all(geoms)


def upv_coverage_extent() -> tuple[float, float, float, float]:
    """The coverage's envelope from WCS DescribeCoverage (west, south, east, north)."""
    import re

    params = {"service": "WCS", "version": "2.0.1", "request": "DescribeCoverage", "coverageId": UPV["coverage"]}
    resp = requests.get(UPV["wcs"], params=params, timeout=300, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    lo = re.search(r"<gml:lowerCorner>([\d.]+) ([\d.]+)</gml:lowerCorner>", resp.text)
    hi = re.search(r"<gml:upperCorner>([\d.]+) ([\d.]+)</gml:upperCorner>", resp.text)
    (UPV_DIR / "describe_coverage.xml").write_text(resp.text, encoding="utf-8")
    return float(lo.group(1)), float(lo.group(2)), float(hi.group(1)), float(hi.group(2))


def upv_tiles(towns_union, outline, extent) -> list[tuple[float, float, float, float]]:
    """1 km tiles (edges on multiples of 1 km) that meet a town, the UPV outline and the coverage."""
    import shapely
    from shapely.geometry import box

    area = shapely.intersection(towns_union.buffer(10.0), outline.buffer(10.0)).intersection(box(*extent))
    w, s, e, n = area.bounds
    tiles = []
    for x0 in np.arange(np.floor(w / UPV_TILE_M) * UPV_TILE_M, e, UPV_TILE_M):
        for y0 in np.arange(np.floor(s / UPV_TILE_M) * UPV_TILE_M, n, UPV_TILE_M):
            t = box(x0, y0, x0 + UPV_TILE_M, y0 + UPV_TILE_M)
            if t.intersects(area):
                tiles.append((float(x0), float(y0), float(x0 + UPV_TILE_M), float(y0 + UPV_TILE_M)))
    return tiles


def pick_cell_centres(tile_bytes: bytes, out: np.ndarray, tile: tuple[float, float, float, float]) -> int:
    """Write into `out` (the 5 m analysis grid) the native 0.5 m pixel holding each cell centre of the tile.

    No value (NaN or the coverage's nodata) is written as NaN. Returns the number of cells written.
    """
    from rasterio.io import MemoryFile

    with MemoryFile(tile_bytes) as mem, mem.open() as src:
        a = src.read(1).astype(np.float32)
        t = src.transform
        nod = src.nodata
    if nod is not None:
        a[a == np.float32(nod)] = np.nan
    a[~np.isfinite(a) | (a < -1e30)] = np.nan
    gw, gs, ge, gn = GRID_BOUNDS
    x0, y0, x1, y1 = tile
    cols = np.arange(int(round((x0 - gw) / CELL_M)), int(round((x1 - gw) / CELL_M)))
    rows = np.arange(int(round((gn - y1) / CELL_M)), int(round((gn - y0) / CELL_M)))
    rows = rows[(rows >= 0) & (rows < out.shape[0])]
    cols = cols[(cols >= 0) & (cols < out.shape[1])]
    if rows.size == 0 or cols.size == 0:
        return 0
    xc = gw + (cols + 0.5) * CELL_M
    yc = gn - (rows + 0.5) * CELL_M
    pc = np.floor((xc - t.c) / t.a).astype(np.int64)
    pr = np.floor((yc - t.f) / t.e).astype(np.int64)
    okc = (pc >= 0) & (pc < a.shape[1])
    okr = (pr >= 0) & (pr < a.shape[0])
    sub = np.full((rows.size, cols.size), np.nan, dtype=np.float32)
    sub[np.ix_(okr, okc)] = a[np.ix_(pr[okr], pc[okc])]
    block = out[np.ix_(rows, cols)]
    take = np.isnan(block) & np.isfinite(sub)
    block[take] = sub[take]
    out[np.ix_(rows, cols)] = block
    return int(np.isfinite(sub).sum())


def fetch_upv(manifest: dict, zones_dir: Path, workers: int = 2) -> dict:
    """UPV depth at every 5 m cell centre of the analysis grid inside the 10 towns and the UPV outline.

    Native 0.5 m tiles of 1 km from the WCS; each cell centre takes the pixel that holds it. The tiles
    are not kept (about 17 MB each); their checksums are listed in data/interim/streets/upv/tiles.json.
    """
    import shapely
    from concurrent.futures import ThreadPoolExecutor

    upv_outlines(manifest)
    outline = load_upv_outline()
    extent = upv_coverage_extent()
    towns = load_towns(zones_dir)
    tiles = upv_tiles(shapely.union_all(list(towns.geometry)), outline, extent)
    print(f"UPV: {len(tiles)} tiles of 1 km", flush=True)
    out = np.full(grid_shape(), np.nan, dtype=np.float32)
    log = []

    def get(tile):
        x0, y0, x1, y1 = tile
        x0, y0, x1, y1 = max(x0, extent[0]), max(y0, extent[1]), min(x1, extent[2]), min(y1, extent[3])
        url = (f"{UPV['wcs']}?service=WCS&version=2.0.1&request=GetCoverage&coverageId={UPV['coverage']}"
               f"&format=image/tiff&subset=E({x0:.1f},{x1:.1f})&subset=N({y0:.1f},{y1:.1f})")
        for attempt in range(4):
            try:
                resp = requests.get(url, timeout=600, headers={"User-Agent": USER_AGENT})
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/tiff"):
                    return tile, url, resp.content
                err = f"HTTP {resp.status_code} {resp.text[:200]}"
            except requests.RequestException as exc:
                err = repr(exc)
            print(f"tile {tile}: attempt {attempt + 1} failed ({err})", flush=True)
            time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"UPV tile {tile} failed")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (tile, url, content) in enumerate(pool.map(get, tiles)):
            n = pick_cell_centres(content, out, tile)
            log.append({"tile": tile, "url": url, "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(), "cells_with_value": n})
            if (i + 1) % 10 == 0:
                print(f"UPV: {i + 1}/{len(tiles)} tiles, {time.time() - t0:.0f} s", flush=True)
    path = save_grid("upv_depth5", out, nodata=np.nan, folder=UPV_DIR)
    (UPV_DIR / "tiles.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    combined = hashlib.sha256("".join(t["sha256"] for t in log).encode()).hexdigest()
    manifest["upv_depth"] = {
        **{k: v for k, v in UPV.items() if k not in ("outlines",)},
        "url_template": f"{UPV['wcs']}?service=WCS&version=2.0.1&request=GetCoverage&coverageId={UPV['coverage']}"
                        "&format=image/tiff&subset=E(x0,x1)&subset=N(y0,y1)",
        "coverage_extent_epsg25830": list(extent), "native_pixel_m": UPV_PIXEL_M,
        "tiles": len(log), "tile_bytes": int(sum(t["bytes"] for t in log)), "tiles_sha256_combined": combined,
        "file": path.relative_to(DATA_DIR.parent).as_posix(),
        "rule": "each 5 m cell centre of the analysis grid takes the native 0.5 m pixel that holds it; NaN = no value",
        "cells_with_value": int(np.isfinite(out).sum()), "retrieved_utc": _now(),
        "seconds": round(time.time() - t0, 1),
    }
    save_manifest(manifest)
    print(json.dumps({k: manifest["upv_depth"][k] for k in ("tiles", "tile_bytes", "cells_with_value", "seconds")}))
    return manifest["upv_depth"]


def fetch(manifest: dict, zones_dir: Path, what: str = "all") -> None:
    if what in ("all", "upv"):
        fetch_upv(manifest, zones_dir)
    if what in ("all", "osm"):
        fetch_osm(manifest, zones_dir)


STEPS = ("fetch", "fetch-osm", "fetch-upv", "score", "report")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline.street_scores", description=__doc__.split("\n\n")[0])
    parser.add_argument("step", choices=STEPS)
    parser.add_argument("--zones-interim", type=Path, default=ZONES_INTERIM_DIR,
                        help="downloads of pipeline.zones (PR #36): municipalities, SNCZI, EMSR773")
    args = parser.parse_args(argv)
    manifest = load_manifest()
    if args.step == "fetch":
        fetch(manifest, args.zones_interim)
    elif args.step == "fetch-osm":
        fetch(manifest, args.zones_interim, "osm")
    elif args.step == "fetch-upv":
        fetch(manifest, args.zones_interim, "upv")


if __name__ == "__main__":
    main()
