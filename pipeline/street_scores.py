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


def load_upv_outline(keys: tuple[str, ...] = tuple(UPV["outlines"])):
    """Union of the UPV outlines (by default the surveyed area and the extra zones), EPSG:25830."""
    import shapely
    from shapely.geometry import shape

    geoms = []
    for key in keys:
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


def pick_cell_centres(tile_bytes: bytes, out: np.ndarray, tile: tuple[float, float, float, float],
                      bounds: tuple[float, float, float, float] = GRID_BOUNDS) -> int:
    """Write into `out` (a 5 m grid with these bounds) the native pixel holding each cell centre of the tile.

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
    gw, gs, ge, gn = bounds
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


# ---------------------------------------------------------------- streets into pieces

PIECE_M = 25.0          # pieces of about 25 m
SAMPLE_M = 2.5          # sample points at most 2.5 m apart
MARK_RADIUS_M = 10.0    # key A: a surveyed water mark above 0 m within 10 m
UPV_DEPTH_M = 0.1       # key B: UPV depth above 0.1 m
SIM_EXTENT_M = 0.3      # the SIMULATED run's own extent: maximum depth above 0.3 m
MAJORITY = 0.5          # a piece is in a layer when at least half of its sample points are
# The two newer runs (docs/STREETS.md, "Two more simulations"), scored exactly like the PR #39 run: own extent
# (maximum depth above 0.3 m) and the ranking by median maximum depth cut to the official zones' street length.
EXTRA_SIM_RUNS = {
    "ifs_20241028T12": "simulation_ifs_20241028T12",   # run A, forecast issued 28 Oct 2024 12 UTC
    "ifs_20241029T00": "simulation_ifs_20241029T00",   # run A, forecast issued 29 Oct 2024 00 UTC
    "buildings": "simulation_buildings",               # run B, gauged rain, buildings as obstacles
    "ifs_20241029T06": "simulation_ifs_20241029T06",   # run A3 (amendment), forecast issued 29 Oct 2024 06 UTC
}

ROADS = ("motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
         "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service",
         "road", "busway")
PEDESTRIAN = ("pedestrian", "footway", "path", "steps", "cycleway")
TRACKS = ("track",)
DUPLICATE_WAYS = ("footway", "path", "cycleway")   # drawn as their own way beside or across a street ...
DUPLICATE_VALUES = ("sidewalk", "crossing")        # ... when tagged as a sidewalk or a crossing


def way_reason(tags: dict, tracks: bool = False) -> str:
    """'kept', or why an OSM way is left out of the streets (the rules of docs/STREETS.md)."""
    hw = tags.get("highway")
    if hw not in ROADS + PEDESTRIAN + (TRACKS if tracks else ()):
        return "track" if hw in TRACKS else "other highway value"
    if tags.get("area") == "yes":
        return "area"
    if tags.get("tunnel", "no") != "no":
        return "tunnel"
    if hw in DUPLICATE_WAYS and any(tags.get(k) in DUPLICATE_VALUES for k in DUPLICATE_WAYS):
        return "sidewalk or crossing"
    return "kept"


def load_ways(tracks: bool = False) -> dict:
    """The kept OSM ways of the 10 town boxes, each once, as one array of vertices (EPSG:25830).

    Returns ids, highway values, vertex coordinates (consecutive duplicates removed), the index of
    each way's first vertex and vertex count, and the counts of ways left out by reason.
    """
    from collections import Counter

    from pyproj import Transformer

    seen: dict[int, tuple[str, list]] = {}
    reasons: Counter = Counter()
    read = set()
    for path in sorted(OSM_DIR.glob("highways_*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for el in doc.get("elements", []):
            if el.get("type") != "way" or el["id"] in read:
                continue
            read.add(el["id"])
            tags = el.get("tags", {})
            why = way_reason(tags, tracks)
            pts = [(p["lon"], p["lat"]) for p in (el.get("geometry") or []) if p]
            if why == "kept" and len(pts) < 2:
                why = "no geometry"
            reasons[why] += 1
            if why == "kept":
                seen[el["id"]] = (tags["highway"], pts)
    ids = np.array(sorted(seen), dtype=np.int64)
    lonlat = np.array([p for i in ids for p in seen[i][1]], dtype=np.float64)
    nv = np.array([len(seen[i][1]) for i in ids], dtype=np.int64)
    x, y = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(lonlat[:, 0], lonlat[:, 1])
    xy = np.column_stack([x, y])
    way_of_vertex = np.repeat(np.arange(ids.size), nv)
    # drop a vertex equal to the one before it in the same way (zero-length segments)
    dup = np.zeros(len(xy), dtype=bool)
    dup[1:] = (way_of_vertex[1:] == way_of_vertex[:-1]) & np.all(xy[1:] == xy[:-1], axis=1)
    xy, way_of_vertex = xy[~dup], way_of_vertex[~dup]
    nv = np.bincount(way_of_vertex, minlength=ids.size)
    keep = nv >= 2
    if not keep.all():
        reasons["no geometry"] += int((~keep).sum())
        reasons["kept"] -= int((~keep).sum())
        good = keep[way_of_vertex]
        xy, way_of_vertex = xy[good], way_of_vertex[good]
        remap = np.cumsum(keep) - 1
        way_of_vertex = remap[way_of_vertex]
        ids, nv = ids[keep], nv[keep]
    return {"ids": ids, "highway": np.array([seen[i][0] for i in ids]), "xy": xy, "nv": nv,
            "first": np.cumsum(nv) - nv, "reasons": dict(reasons), "ways_read": len(read)}


def way_measures(xy: np.ndarray, nv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Distance of every vertex from its way's start, and each way's length."""
    way_of_vertex = np.repeat(np.arange(nv.size), nv)
    seg = np.zeros(len(xy))
    seg[1:] = np.hypot(*(xy[1:] - xy[:-1]).T)
    first = np.cumsum(nv) - nv
    seg[first] = 0.0
    cum = np.cumsum(seg)
    cum -= np.repeat(cum[first], nv)
    length = cum[first + nv - 1]
    return cum, length


def pieces_of(length: np.ndarray, piece_m: float = PIECE_M) -> dict:
    """Each way cut into n equal pieces, n = length / piece_m rounded (halves up), at least 1."""
    n = np.maximum(1, np.floor(length / piece_m + 0.5)).astype(np.int64)
    way = np.repeat(np.arange(length.size), n)
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    plen = length[way] / n[way]
    return {"way": way, "k": k, "start": k * plen, "length": plen}


def samples_of(piece_len: np.ndarray, sample_m: float = SAMPLE_M) -> tuple[np.ndarray, np.ndarray]:
    """Sample points of each piece: m = ceil(length / sample_m), at the centres of m equal parts.

    Returns the piece of each sample and its distance from the piece's start.
    """
    m = np.maximum(1, np.ceil(np.round(piece_len / sample_m, 9))).astype(np.int64)
    piece = np.repeat(np.arange(piece_len.size), m)
    i = np.arange(m.sum()) - np.repeat(np.cumsum(m) - m, m)
    return piece, (i + 0.5) * piece_len[piece] / m[piece]


def interpolate(xy: np.ndarray, nv: np.ndarray, cum: np.ndarray, length: np.ndarray, way: np.ndarray,
                dist: np.ndarray) -> np.ndarray:
    """Points at distance `dist` along way `way` (vectorised; distances clipped to the way)."""
    first = np.cumsum(nv) - nv
    span = float(length.max()) + 1.0
    key = cum + np.repeat(np.arange(nv.size), nv) * span
    d = np.clip(dist, 0.0, length[way])
    j = np.searchsorted(key, way * span + d, side="right") - 1
    j = np.clip(j, first[way], first[way] + nv[way] - 2)
    seg = cum[j + 1] - cum[j]
    t = np.where(seg > 0, (d - cum[j]) / np.where(seg > 0, seg, 1.0), 0.0)
    return xy[j] + t[:, None] * (xy[j + 1] - xy[j])


def piece_lines(xy: np.ndarray, nv: np.ndarray, cum: np.ndarray, length: np.ndarray, pieces: dict):
    """Exact piece geometries: start point, the way's vertices strictly inside, end point."""
    import shapely

    way, start, plen = pieces["way"], pieces["start"], pieces["length"]
    end = start + plen
    first = np.cumsum(nv) - nv
    span = float(length.max()) + 1.0
    key = cum + np.repeat(np.arange(nv.size), nv) * span
    lo = np.searchsorted(key, way * span + start, side="right")
    hi = np.searchsorted(key, way * span + end, side="left")
    lo = np.maximum(lo, first[way])
    hi = np.minimum(np.maximum(hi, lo), first[way] + nv[way])
    inner = hi - lo
    count = inner + 2
    owner = np.repeat(np.arange(way.size), count)
    pos = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    coords = np.empty((count.sum(), 2))
    is_start = pos == 0
    is_end = pos == count[owner] - 1
    mid = ~(is_start | is_end)
    coords[is_start] = interpolate(xy, nv, cum, length, way, start)
    coords[is_end] = interpolate(xy, nv, cum, length, way, end)
    coords[mid] = xy[(lo[owner] + pos - 1)[mid]]
    return shapely.linestrings(coords, indices=owner)


def near_points(lines, x: np.ndarray, y: np.ndarray, radius: float = MARK_RADIUS_M) -> np.ndarray:
    """Pieces whose line lies within `radius` of any of the points (planar distance)."""
    import shapely

    out = np.zeros(len(lines), dtype=bool)
    if x.size == 0:
        return out
    tree = shapely.STRtree(lines)
    pairs = tree.query(shapely.points(x, y), predicate="dwithin", distance=radius)
    out[np.unique(pairs[1])] = True
    return out


def share_in(layer_at_sample: np.ndarray, piece: np.ndarray, n: int) -> np.ndarray:
    """Per piece, the share of its (effective) sample points that lie in the layer."""
    total = np.bincount(piece, minlength=n)
    hit = np.bincount(piece, weights=layer_at_sample.astype(np.float64), minlength=n)
    return np.divide(hit, total, out=np.zeros(n), where=total > 0)


def group_median(values: np.ndarray, piece: np.ndarray, n: int) -> np.ndarray:
    """Per piece, the median of its sample values, NaN ignored (NaN when it has none)."""
    import pandas as pd

    med = pd.Series(values.astype(np.float64)).groupby(piece).median()
    out = np.full(n, np.nan)
    out[med.index.to_numpy()] = med.to_numpy()
    return out


def cut_to_length(score: np.ndarray, length: np.ndarray, budget: float) -> np.ndarray:
    """Pieces taken lowest score first (NaN last; ties by index) until their length first reaches budget."""
    sel = np.zeros(score.size, dtype=bool)
    if budget <= 0 or score.size == 0:
        return sel
    s = np.where(np.isfinite(score), score, np.inf)
    order = np.lexsort((np.arange(s.size), s))
    csum = np.cumsum(length[order])
    k = int(np.searchsorted(csum, budget * (1 - 1e-12), side="left")) + 1
    sel[order[:min(k, order.size)]] = True
    return sel


# ---------------------------------------------------------------- scoring


def _km(m: float) -> float:
    return round(float(m) / 1000.0, 2)


def street_metrics(flag: np.ndarray, flood: np.ndarray, length: np.ndarray, domain: np.ndarray | None = None) -> dict:
    """Street length flagged, hit rate and precision of one selection against one key."""
    from pipeline.streets import pct

    d = np.ones(flag.size, dtype=bool) if domain is None else domain
    total = float(length[d].sum())
    fl = float(length[d & flood].sum())
    fg = float(length[d & flag].sum())
    hit = float(length[d & flag & flood].sum())
    return {"street_km": _km(total), "flooded_km": _km(fl), "flagged_km": _km(fg),
            "flagged_pct_of_streets": pct(fg, total), "flagged_and_flooded_km": _km(hit),
            "hit_rate_pct": pct(hit, fl), "precision_pct": pct(hit, fg), "chance_precision_pct": pct(fl, total),
            "pieces_flagged": int((d & flag).sum())}


def by_town(flag, flood, length, town, domain=None) -> dict:
    d = np.ones(flag.size, dtype=bool) if domain is None else domain
    out = {"total": street_metrics(flag, flood, length, d), "towns": {}}
    for i, t in enumerate(TOWNS):
        out["towns"][t] = street_metrics(flag, flood, length, d & (town == i + 1))
    return out


def pixel_layers(zones_dir: Path, sample_cells: np.ndarray) -> dict:
    """The layers of PR #39 read at the given 5 m cells, built one at a time to keep memory low.

    Returns, per cell: scored, town, observed flood, the four official zone layers, bare HAND,
    the PR #39 equal-area cuts (terrain, SIMULATED), the SIMULATED maximum depth and the UPV depth;
    plus checks of the equal-area cuts against results.json.
    """
    import gc

    from pipeline import streets as st

    cells = np.where(sample_cells >= 0, sample_cells, 0)
    on_grid = sample_cells >= 0
    out: dict = {}
    towns = st.load_towns(zones_dir)
    tid = st.town_grid(towns).ravel()
    valid = (st.load_grid("dtm5") != st.DTM_NODATA).ravel()
    water = st.load_grid("water5").astype(bool).ravel()
    products = st.ems_products(zones_dir)
    analysed = np.logical_or.reduce([p["analysed"] for p in products]).ravel()
    fa = np.logical_or.reduce([p["flooded_area"] for p in products]).ravel()
    ft = np.logical_or.reduce([p["flood_trace"] for p in products]).ravel()
    del products
    gc.collect()
    scored = (tid > 0) & analysed & ~water & valid
    del analysed, water, valid
    observed = fa | ft
    del fa, ft
    gc.collect()
    out["scored"] = scored[cells] & on_grid
    out["town"] = np.where(on_grid, tid[cells], 0)
    out["observed"] = observed[cells] & on_grid
    idx = np.flatnonzero(scored)
    town_s = tid[idx]
    obs_s = observed[idx]
    del scored, observed
    gc.collect()
    # position of each sample cell among the scored pixels (-1 if not scored)
    spos = np.searchsorted(idx, cells)
    spos = np.where((spos < idx.size) & (idx[np.minimum(spos, idx.size - 1)] == cells) & on_grid, spos, -1)
    zones = st.zone_grids(zones_dir)
    for z in st.ZONE_NAMES:
        out[f"zone_{z}"] = zones[z].ravel()[cells] & on_grid
    union_s = zones["union"].ravel()[idx]
    del zones
    gc.collect()
    town_pos = {t: np.flatnonzero(town_s == i + 1) for i, t in enumerate(TOWNS)}
    k_town = {t: int(union_s[p].sum()) for t, p in town_pos.items()}

    # the terrain layers and the PR #39 run are optional for `score-runs` (rebuilt later, or not at all)
    has_hand = (st.TERRAIN_DIR / "hand_bare_d0p5km2.tif").exists() and (st.TERRAIN_DIR / "upa_bare.tif").exists()
    has_sim = (INTERIM_DIR / "simulation" / "sim_hmax_25m.tif").exists()
    out["available"] = {"terrain": has_hand, "simulated_pr39": has_sim}
    cuts = {}
    if has_hand:
        hand = st.load_grid("hand_bare_d0p5km2").ravel()
        out["hand"] = np.where(on_grid, hand[cells], np.nan).astype(np.float32)
        hand_s = hand[idx]
        del hand
        gc.collect()
        upa_s = st.load_grid("upa_bare").ravel()[idx]
        gc.collect()
    else:
        out["hand"] = np.full(cells.size, np.nan, dtype=np.float32)
        hand_s = None
        upa_s = np.zeros(idx.size, dtype=np.float32)

    def cut(score_s: np.ndarray) -> np.ndarray:
        sel = np.zeros(idx.size, dtype=bool)
        for t, p in town_pos.items():
            sel[st.ranked(score_s, upa_s, p)[:k_town[t]]] = True
        return sel

    if has_hand:
        cuts["terrain_bare_equal_area_union"] = cut(hand_s)
        out["terrain_equal_area"] = np.where(spos >= 0, cuts["terrain_bare_equal_area_union"][np.maximum(spos, 0)],
                                             False)
        del hand_s
    else:
        out["terrain_equal_area"] = np.zeros(cells.size, dtype=bool)
    f = int(st.SIM_CELL_M // CELL_M)
    cols = grid_shape()[1]
    rr, cc = np.divmod(cells, cols)
    if has_sim:
        hm = st.load_grid("sim_hmax_25m", folder=INTERIM_DIR / "simulation")
        out["sim_depth"] = np.where(on_grid, hm[rr // f, cc // f], np.nan).astype(np.float32)
        ri, ci = np.divmod(idx, cols)
        cuts["simulated_rain_equal_area_union"] = cut(-hm[ri // f, ci // f].astype(np.float64))
        del ri, ci, hm
        out["sim_equal_area"] = np.where(spos >= 0, cuts["simulated_rain_equal_area_union"][np.maximum(spos, 0)],
                                         False)
    else:
        out["sim_depth"] = np.full(cells.size, np.nan, dtype=np.float32)
        out["sim_equal_area"] = np.zeros(cells.size, dtype=bool)
    for run, folder in EXTRA_SIM_RUNS.items():
        if (INTERIM_DIR / folder / "sim_hmax_25m.tif").exists():
            hm_run = st.load_grid("sim_hmax_25m", folder=INTERIM_DIR / folder)
            out[f"simdepth_{run}"] = np.where(on_grid, hm_run[rr // f, cc // f], np.nan).astype(np.float32)
            del hm_run
    del rr, cc
    # checks: the rebuilt cuts against the land flooded per town in results.json (PR #39)
    from pipeline.streets import pct

    res = json.loads((STREETS_DIR / "results.json").read_text(encoding="utf-8"))["methods"]
    check = {}
    for name, sel in cuts.items():
        rows = {}
        for t, p in town_pos.items():
            mine = pct(int((sel[p] & obs_s[p]).sum()), int(sel[p].sum()))
            theirs = res[name]["towns"][t]["own_area_flooded_pct"]
            rows[t] = {"cells": int(sel[p].sum()), "own_land_flooded_pct": mine, "results_json": theirs,
                       "same": mine == theirs and round(int(sel[p].sum()) * 25 / 1e4, 1) == res[name]["towns"][t]["area_ha"]}
        check[name] = {"all_same": all(r["same"] for r in rows.values()), "towns": rows}
    out["checks_equal_area"] = check
    del cuts, upa_s
    gc.collect()
    upv = load_grid_upv()
    out["upv_depth"] = np.where(on_grid, upv[cells], np.nan).astype(np.float32)
    del upv
    gc.collect()
    return out


def load_grid_upv() -> np.ndarray:
    from pipeline.streets import load_grid

    return load_grid("upv_depth5", folder=UPV_DIR).ravel()


def build_pieces(tracks: bool = False) -> dict:
    """Ways, pieces, effective sample points (cells) and piece lines."""
    ways = load_ways(tracks)
    cum, length = way_measures(ways["xy"], ways["nv"])
    pcs = pieces_of(length)
    s_piece, s_off = samples_of(pcs["length"])
    s_xy = interpolate(ways["xy"], ways["nv"], cum, length, pcs["way"][s_piece], pcs["start"][s_piece] + s_off)
    m_xy = interpolate(ways["xy"], ways["nv"], cum, length, pcs["way"], pcs["start"] + pcs["length"] / 2)
    lines = piece_lines(ways["xy"], ways["nv"], cum, length, pcs)
    return {"ways": ways, "way_length": length, "pieces": pcs, "s_piece": s_piece, "s_xy": s_xy, "m_xy": m_xy,
            "lines": lines}


def evaluate(b: dict, lay: dict, marks_xy: np.ndarray, outline, surveyed=None) -> dict:
    """Keys, method flags, rankings and metrics for one set of pieces (b) with its layers (lay).

    lay holds the layer values at the pieces' sample cells followed by their midpoint cells.
    surveyed: the UPV surveyed area alone (CGAT outline), for the post-hoc variant of key B.
    """
    import shapely

    from pipeline.streets import HAND_NATIVE_M

    pcs = b["pieces"]
    n_all = pcs["length"].size
    ns = b["s_piece"].size
    s_scored = lay["scored"][:ns]
    m_scored = lay["scored"][ns:]
    m_town = lay["town"][ns:]
    keep = m_scored & (m_town > 0)                     # scored pieces: midpoint on a scored pixel
    # effective samples: those on scored pixels; a scored piece without any takes its midpoint
    has = np.bincount(b["s_piece"][s_scored], minlength=n_all) > 0
    fallback = np.flatnonzero(keep & ~has)
    e_rows = np.concatenate([np.flatnonzero(s_scored & keep[b["s_piece"]]), ns + fallback])
    e_piece = np.concatenate([b["s_piece"][s_scored & keep[b["s_piece"]]], fallback])
    remap = np.full(n_all, -1, dtype=np.int64)
    remap[keep] = np.arange(int(keep.sum()))
    e_piece = remap[e_piece]
    n = int(keep.sum())
    length = pcs["length"][keep]
    town = m_town[keep]
    hw = b["ways"]["highway"][pcs["way"][keep]]

    def frac(name: str, test=None) -> np.ndarray:
        v = lay[name][e_rows]
        return share_in(v if test is None else test(v), e_piece, n)

    in_obs = frac("observed") >= MAJORITY
    near = near_points(b["lines"][keep], marks_xy[:, 0], marks_xy[:, 1])
    key_a = in_obs | near
    mxy = b["m_xy"][keep]
    shapely.prepare(outline)
    dom_b = shapely.contains_xy(outline, mxy[:, 0], mxy[:, 1])
    upv_v = lay["upv_depth"][e_rows]
    key_b = (share_in(np.where(np.isfinite(upv_v), upv_v, 0.0) > UPV_DEPTH_M, e_piece, n) >= MAJORITY) & dom_b

    flags = {f"official_{z}": frac(f"zone_{z}") >= MAJORITY for z in ("T10", "T100", "T500", "union")}
    flags["terrain_hand_below_15m"] = frac("hand", lambda v: np.isfinite(v) & (v < HAND_NATIVE_M)) >= MAJORITY
    flags["terrain_equal_area_union"] = frac("terrain_equal_area") >= MAJORITY
    flags["simulated_depth_above_0p3m"] = frac("sim_depth", lambda v: np.isfinite(v) & (v > SIM_EXTENT_M)) >= MAJORITY
    flags["simulated_equal_area_union"] = frac("sim_equal_area") >= MAJORITY
    hand_med = group_median(lay["hand"][e_rows], e_piece, n)
    sim_med = group_median(lay["sim_depth"][e_rows], e_piece, n)
    extra = [r for r in EXTRA_SIM_RUNS if f"simdepth_{r}" in lay]
    extra_med = {}
    for r in extra:
        flags[f"simulated_{r}_depth_above_0p3m"] = frac(f"simdepth_{r}",
                                                        lambda v: np.isfinite(v) & (v > SIM_EXTENT_M)) >= MAJORITY
        extra_med[r] = group_median(lay[f"simdepth_{r}"][e_rows], e_piece, n)

    keys = {"A": (key_a, None), "B": (key_b, dom_b)}
    methods = {}
    for name, fl in flags.items():
        methods[name] = {k: by_town(fl, kv, length, town, dom) for k, (kv, dom) in keys.items()}
    # equal street length: each ranking cut, town by town, to the official zones' street length
    official = flags["official_union"]
    rankings = {"terrain_hand": hand_med, "simulated_depth": -sim_med,
                **{f"simulated_{r}_depth": -extra_med[r] for r in extra}}
    eq_sel = {r: np.zeros(n, dtype=bool) for r in rankings}
    budget = {}
    for i, t in enumerate(TOWNS):
        p = np.flatnonzero(town == i + 1)
        budget[t] = float(length[p][official[p]].sum())
        for r, score in rankings.items():
            eq_sel[r][p[cut_to_length(score[p], length[p], budget[t])]] = True
    equal = {"official_union": {k: by_town(official, kv, length, town, dom) for k, (kv, dom) in keys.items()}}
    for r, sel in eq_sel.items():
        equal[r] = {k: by_town(sel, kv, length, town, dom) for k, (kv, dom) in keys.items()}
    # the ceiling (docs/STREETS.md, "Two more simulations": added before any score of those runs): the two answer
    # keys scored against each other on the streets both cover (inside the UPV outlines), as if each were a method;
    # and every method's key A numbers on those same streets, so they can be read against it
    ceiling = {
        "what": "ceiling (two records of the same flood): on the pieces inside the UPV outlines, key B (the UPV map) "
                "scored as a method against key A, and key A against key B; not independent (the UPV marks are part "
                "of key A)",
        "key_b_against_key_a": by_town(key_b, key_a, length, town, dom_b),
        "key_a_against_key_b": by_town(key_a, key_b, length, town, dom_b),
    }
    key_a_inside_upv = {
        "what": "key A, on the pieces inside the UPV outlines only (the streets of the ceiling)",
        "own_length": {name: by_town(fl, key_a, length, town, dom_b) for name, fl in flags.items()},
        "equal_length": {r: by_town(sel, key_a, length, town, dom_b)
                         for r, sel in {"official_union": official, **eq_sel}.items()},
    }
    town_km = {t: _km(length[town == i + 1].sum()) for i, t in enumerate(TOWNS)}
    # descriptive, after the headline: the streets the SIMULATED extent flags outside every official zone
    sim_ext = flags["simulated_depth_above_0p3m"]
    outside = ~official
    descriptive = {
        "what": "descriptive, computed after the headline: flooded streets outside every official zone, and the "
                "streets the SIMULATED extent (above 0.3 m) flags outside every official zone",
        "key_a_flooded_km_outside_every_zone": _km(length[key_a & outside].sum()),
        "key_a_flooded_outside_every_zone_pct": round(100.0 * float(length[key_a & outside].sum())
                                                      / max(float(length[key_a].sum()), 1e-9), 1),
        "key_b_flooded_km_outside_every_zone": _km(length[key_b & outside].sum()),
        "key_b_flooded_outside_every_zone_pct": round(100.0 * float(length[key_b & outside].sum())
                                                      / max(float(length[key_b].sum()), 1e-9), 1),
        "simulated_outside_zones": {"A": by_town(sim_ext & outside, key_a, length, town),
                                    "B": by_town(sim_ext & outside, key_b, length, town, dom_b)},
        "outside_zones_chance_precision": {
            "A": street_metrics(outside, key_a, length, outside)["chance_precision_pct"],
            "B": street_metrics(outside, key_b, length, outside & dom_b)["chance_precision_pct"]},
    }
    for r in extra:
        ext = flags[f"simulated_{r}_depth_above_0p3m"]
        descriptive[f"simulated_{r}_outside_zones"] = {"A": by_town(ext & outside, key_a, length, town),
                                                       "B": by_town(ext & outside, key_b, length, town, dom_b)}
    post_hoc = None
    if surveyed is not None:
        shapely.prepare(surveyed)
        dom_s = shapely.contains_xy(surveyed, mxy[:, 0], mxy[:, 1])
        key_s = key_b & dom_s
        post_hoc = {
            "what": "POST-HOC (added after the check of key B at the water marks, checks.upv_at_marks): key B on "
                    "the pieces inside the UPV surveyed area (CGAT outline) only, where the map has a value at most "
                    "wet marks; in the extra zones it has none at about half of them",
            "inside_km": _km(length[dom_s].sum()), "flooded_km": _km(length[key_s].sum()),
            "inside_km_by_town": {t: _km(length[dom_s & (town == i + 1)].sum()) for i, t in enumerate(TOWNS)},
            "equal_length": {r: by_town(sel, key_s, length, town, dom_s)
                             for r, sel in {"official_union": official, **eq_sel}.items()},
            "own_length": {name: by_town(fl, key_s, length, town, dom_s) for name, fl in flags.items()},
        }
    summary = {
        "pieces": n, "street_km": _km(length.sum()), "street_km_by_town": town_km,
        "street_km_by_highway": {h: _km(length[hw == h].sum()) for h in sorted(set(hw))},
        "pieces_by_town": {t: int((town == i + 1).sum()) for i, t in enumerate(TOWNS)},
        "piece_length_m": {"median": round(float(np.median(length)), 1), "p05": round(float(np.percentile(length, 5)), 1),
                           "p95": round(float(np.percentile(length, 95)), 1)},
        "pieces_on_the_midpoint_only": int(fallback.size),
        "key_a": {"flooded_km": _km(length[key_a].sum()), "in_observed_flood_km": _km(length[in_obs].sum()),
                  "near_a_mark_km": _km(length[near].sum()), "both_km": _km(length[in_obs & near].sum()),
                  "flooded_km_by_town": {t: _km(length[key_a & (town == i + 1)].sum()) for i, t in enumerate(TOWNS)}},
        "key_b": {"inside_outlines_km": _km(length[dom_b].sum()), "flooded_km": _km(length[key_b].sum()),
                  "inside_outlines_km_by_town": {t: _km(length[dom_b & (town == i + 1)].sum()) for i, t in enumerate(TOWNS)},
                  "flooded_km_by_town": {t: _km(length[key_b & (town == i + 1)].sum()) for i, t in enumerate(TOWNS)},
                  "key_a_flooded_km_inside_outlines": _km(length[key_a & dom_b].sum()),
                  "agreement_inside_outlines_pct": round(100.0 * float(length[dom_b & (key_a == key_b)].sum())
                                                         / max(float(length[dom_b].sum()), 1e-9), 1)},
        "equal_length_budget_km": {t: _km(v) for t, v in budget.items()},
    }
    sens = {
        "key_a_emsr773_only": {r: by_town(sel, in_obs, length, town) for r, sel in
                               {"official_union": official, **eq_sel}.items()},
        "key_a_marks_only": {r: by_town(sel, near, length, town) for r, sel in
                             {"official_union": official, **eq_sel}.items()},
    }
    table = {"x": mxy[:, 0].astype(np.float32), "y": mxy[:, 1].astype(np.float32), "length": length.astype(np.float32),
             "town": town.astype(np.uint8), "highway": hw, "key_a": key_a, "in_observed": in_obs, "near_mark": near,
             "key_b": key_b, "inside_upv": dom_b, "hand_median": hand_med.astype(np.float32),
             "sim_median": sim_med.astype(np.float32),
             **{f"sim_median_{r}": v.astype(np.float32) for r, v in extra_med.items()},
             **{f"flag_{k}": v for k, v in flags.items()},
             **{f"equal_{k}": v for k, v in eq_sel.items()}}
    return {"summary": summary, "methods": methods, "equal_length": equal, "key_sensitivity": sens,
            "descriptive": descriptive, "key_b_surveyed_area_only_post_hoc": post_hoc, "ceiling": ceiling,
            "key_a_inside_upv_outlines": key_a_inside_upv, "_table": table}


METHOD_WHAT = {
    "official_T10": "Official zones (SNCZI), T10 as mapped",
    "official_T100": "Official zones (SNCZI), T100 as mapped",
    "official_T500": "Official zones (SNCZI), T500 as mapped",
    "official_union": "Official zones (SNCZI), any zone (union of T10, T100 and T500)",
    "terrain_hand_below_15m": "Terrain: HAND below 15 m (PR #39 method 2, bare terrain, drainage above 0.5 km2)",
    "terrain_equal_area_union": "Terrain: PR #39 equal-area cut (lowest HAND pixels of each town, as many as its "
                                "pixels in any official zone)",
    "simulated_depth_above_0p3m": "SIMULATED rain on terrain (PR #39): its own extent, maximum depth above 0.3 m",
    "simulated_equal_area_union": "SIMULATED rain on terrain (PR #39): equal-area cut (deepest pixels of each town, "
                                  "as many as its pixels in any official zone)",
    "simulated_ifs_20241028T12_depth_above_0p3m": "SIMULATED run A: rain of the ECMWF IFS HRES forecast issued "
                                                  "28 Oct 2024 12 UTC; its own extent, maximum depth above 0.3 m",
    "simulated_ifs_20241029T00_depth_above_0p3m": "SIMULATED run A: rain of the ECMWF IFS HRES forecast issued "
                                                  "29 Oct 2024 00 UTC; its own extent, maximum depth above 0.3 m",
    "simulated_buildings_depth_above_0p3m": "SIMULATED run B: gauged rain, buildings as obstacles (25 m cells at "
                                            "least half Catastro footprint raised by 10 m); its own extent, maximum "
                                            "depth above 0.3 m",
    "simulated_ifs_20241029T06_depth_above_0p3m": "SIMULATED run A3 (amendment): rain of the ECMWF IFS HRES forecast "
                                                  "issued 29 Oct 2024 06 UTC; its own extent, maximum depth above 0.3 m",
}


def _keep_name(name: str, available: dict) -> bool:
    """Entries of the `score-runs` block: the official zones, the newer runs, and what was rebuilt as a check."""
    if name.startswith("official"):
        return True
    if any(name.startswith(f"simulated_{r}_") for r in EXTRA_SIM_RUNS):
        return True
    if name.startswith("terrain"):
        return available["terrain"]
    if name.startswith("simulated_equal_area"):
        # the PR #39 pixel cut breaks its ties (25 cells of 5 m share each 25 m depth) by the bare upstream area
        return available["terrain"] and available["simulated_pr39"]
    if name.startswith("simulated"):
        return available["simulated_pr39"]
    return True


def _filtered(block: dict, available: dict) -> dict:
    """The evaluate() output without the methods whose layers were not rebuilt (their flags would be empty)."""
    keep = lambda d: {k: v for k, v in d.items() if _keep_name(k, available)}  # noqa: E731
    out = {"summary": block["summary"], "methods": keep(block["methods"]), "equal_length": keep(block["equal_length"]),
           "key_sensitivity": {k: keep(v) for k, v in block["key_sensitivity"].items()}}
    desc = dict(block["descriptive"])
    if not available["simulated_pr39"]:
        desc.pop("simulated_outside_zones", None)
    out["descriptive"] = desc
    ph = block.get("key_b_surveyed_area_only_post_hoc")
    if ph is not None:
        out["key_b_surveyed_area_only_post_hoc"] = {**ph, "equal_length": keep(ph["equal_length"]),
                                                    "own_length": keep(ph["own_length"])}
    out["ceiling"] = block["ceiling"]
    ka = block["key_a_inside_upv_outlines"]
    out["key_a_inside_upv_outlines"] = {**ka, "own_length": keep(ka["own_length"]),
                                        "equal_length": keep(ka["equal_length"])}
    return out


def _same_as_pr43(new: dict, old: dict) -> dict:
    """The rebuild against PR #43 (results.json → streets): keys, the official zones, and whatever was rebuilt."""
    rows = {}
    for label in ("main", "with_tracks"):
        if label not in old:
            continue
        a, b = new[label], old[label]
        rows[f"{label}_summary"] = {k: {"rebuilt": a["summary"][k], "pr43": b["summary"][k],
                                        "same": a["summary"][k] == b["summary"][k]}
                                    for k in ("pieces", "street_km", "key_a", "key_b", "equal_length_budget_km")}
        for name in a["methods"]:
            if name in b["methods"]:
                rows[f"{label}_{name}"] = {"same": all(a["methods"][name][k] == b["methods"][name][k] for k in "AB")}
        for name in a["equal_length"]:
            if name in b["equal_length"]:
                rows[f"{label}_equal_length_{name}"] = {
                    "same": all(a["equal_length"][name][k] == b["equal_length"][name][k] for k in "AB")}
    return {"all_same": all(v["same"] if "same" in v else all(x["same"] for x in v.values()) for v in rows.values()),
            "rows": rows}


def score(zones_dir: Path, block: str = "streets") -> dict:
    """Pieces, keys, methods and metrics (with and without tracks); written into results.json → streets.

    block="streets_more_runs" (step `score-runs`): the same scoring with the newer runs, written into its own
    block so the PR #43 numbers in `streets` stay as they were; the rebuilt parts are compared with them.
    """
    import gc

    from pipeline import streets as st
    from pipeline.streets import cells_of_points

    t0 = time.time()
    main_b = build_pieces(tracks=False)
    track_b = build_pieces(tracks=True)
    print(f"pieces: {main_b['pieces']['length'].size} (with tracks {track_b['pieces']['length'].size}), "
          f"{time.time() - t0:.0f} s", flush=True)
    # one lookup for both piece sets: sample cells then midpoint cells, main first
    parts = []
    for b in (main_b, track_b):
        parts += [cells_of_points(b["s_xy"][:, 0], b["s_xy"][:, 1]), cells_of_points(b["m_xy"][:, 0], b["m_xy"][:, 1])]
    sizes = [p.size for p in parts]
    lay_all = pixel_layers(zones_dir, np.concatenate(parts))
    print(f"layers read, {time.time() - t0:.0f} s", flush=True)
    bounds = np.cumsum([0, *sizes])
    marks = st.water_marks_all()
    marks = marks[marks["height_m"] > 0]
    marks_xy = marks[["x", "y"]].to_numpy()
    outline = load_upv_outline()
    surveyed = load_upv_outline(("cgat",))
    results = {}
    for j, (label, b) in enumerate((("main", main_b), ("with_tracks", track_b))):
        lo, hi = bounds[2 * j], bounds[2 * j + 2]
        lay = {k: v[lo:hi] for k, v in lay_all.items() if isinstance(v, np.ndarray)}
        results[label] = evaluate(b, lay, marks_xy, outline, surveyed)
        table = results[label].pop("_table")
        suffix = "" if block == "streets" else "_more_runs"
        np.savez_compressed(INTERIM_DIR / f"street_pieces_{label}{suffix}.npz", **table)
        results[label]["summary"]["ways"] = {"read": b["ways"]["ways_read"], "by_reason": b["ways"]["reasons"]}
        print(f"{label}: {results[label]['summary']['pieces']} scored pieces, "
              f"{results[label]['summary']['street_km']} km, {time.time() - t0:.0f} s", flush=True)
        gc.collect()
    # check for key B: what the UPV map holds at the surveyed marks (0 m: dry spots; above 0 m)
    allm = st.water_marks_all()
    mc = cells_of_points(allm["x"].to_numpy(), allm["y"].to_numpy())
    upv = load_grid_upv()
    import shapely

    shapely.prepare(outline)
    inside = shapely.contains_xy(outline, allm["x"].to_numpy(), allm["y"].to_numpy()) & (mc >= 0)
    v = np.where(mc >= 0, upv[np.maximum(mc, 0)], np.nan)
    del upv
    h = allm["height_m"].to_numpy()
    upv_check = {}
    for label, sel in (("marks_0m", inside & (h == 0)), ("marks_above_0m", inside & (h > 0)),
                       ("marks_above_0p1m", inside & (h > UPV_DEPTH_M))):
        vv = v[sel]
        upv_check[label] = {"marks_inside_outlines": int(sel.sum()),
                            "with_a_value_pct": st.pct(int(np.isfinite(vv).sum()), vv.size),
                            "depth_above_0p1m_pct": st.pct(int((np.nan_to_num(vv) > UPV_DEPTH_M).sum()), vv.size)}
    in_cgat = shapely.contains_xy(surveyed, allm["x"].to_numpy(), allm["y"].to_numpy()) & (mc >= 0)
    for label, sel in (("marks_above_0m_surveyed_area", in_cgat & (h > 0)),
                       ("marks_above_0m_extra_zones_only", inside & ~in_cgat & (h > 0))):
        vv = v[sel]
        upv_check[label] = {"marks": int(sel.sum()), "with_a_value_pct": st.pct(int(np.isfinite(vv).sum()), vv.size),
                            "depth_above_0p1m_pct": st.pct(int((np.nan_to_num(vv) > UPV_DEPTH_M).sum()), vv.size)}
    both = inside & (h > 0) & np.isfinite(v)
    if both.any():
        err = v[both] - h[both]
        upv_check["marks_above_0m_with_a_value"] = {
            "n": int(both.sum()), "median_mark_m": round(float(np.median(h[both])), 2),
            "median_map_m": round(float(np.median(v[both])), 2), "mean_abs_diff_m": round(float(np.mean(np.abs(err))), 2),
            "median_abs_diff_m": round(float(np.median(np.abs(err))), 2),
            "corr": round(float(np.corrcoef(v[both], h[both])[0, 1]), 2)}
    manifest = load_manifest()
    out = {
        "title": "Street by street: which method pointed to the streets that flooded, DANA of 29 Oct 2024, "
                 "10 towns of L'Horta Sud and Chiva",
        "note": SI_LINE, "created_utc": _now(),
        "rules": "docs/STREETS.md, section 'Street by street' (committed before any street score: commit 6e9bd5c)",
        "what": {"methods": METHOD_WHAT,
                 "key_A": "flooded: in the EMSR773 observed flood (majority of sample points) or within 10 m of a "
                          "surveyed water mark above 0 m (ICV)",
                 "key_B": "flooded: UPV maximum depth above 0.1 m (majority of sample points); only on pieces "
                          "whose midpoint lies inside the UPV outlines",
                 "equal_length": "each ranking cut, town by town, to the street length the official zones (any "
                                 "zone) flag; terrain: median HAND lowest first; SIMULATED: median maximum depth "
                                 "deepest first",
                 "hit_rate_pct": "share of the flooded street length flagged",
                 "precision_pct": "share of the flagged street length that flooded",
                 "chance": "a random choice of the same length: hit rate = flagged_pct_of_streets, precision = "
                           "chance_precision_pct"},
        "main": results["main"],
        "with_tracks": results["with_tracks"],
        "checks": {"equal_area_cuts_rebuilt": lay_all["checks_equal_area"], "upv_at_marks": upv_check},
        "inputs": {
            "osm": {k: v for k, v in manifest.items() if k.startswith("osm_highways_")},
            "upv": {k: v for k, v in manifest.items() if k.startswith("upv_")},
            "pixel_layers": "PR #39 rasters in data/interim/streets/terrain and simulation, pipeline.zones downloads",
        },
        "seconds": round(time.time() - t0, 1),
    }
    path = STREETS_DIR / "results.json"
    res = json.loads(path.read_text(encoding="utf-8"))
    if block != "streets":
        avail = lay_all["available"]
        out["title"] = ("Street by street, two more SIMULATED runs (forecast rain, buildings) next to the official "
                        "zones, DANA of 29 Oct 2024, 10 towns of L'Horta Sud and Chiva")
        out["rules"] = ("docs/STREETS.md, section 'Two more simulations' (committed before either run was simulated "
                        "or scored: commit 37c33ef); scoring as in 'Street by street'")
        out["rebuilt_layers"] = avail
        for label in ("main", "with_tracks"):
            out[label] = _filtered(out[label], avail)
        out["same_as_pr43"] = _same_as_pr43(out, res.get("streets", {}))
        out["inputs"]["osm"] = {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                for p in sorted(OSM_DIR.glob("highways_*.json"))}
        out["inputs"]["pixel_layers"] = ("rebuilt 15 Nov 2026 from the PR #39 sources: data/interim/streets/terrain, "
                                         "the simulation folders of pipeline.streets.SIM_RUNS, pipeline.zones downloads")
    res[block] = out
    path.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path} → {block} ({time.time() - t0:.0f} s)")
    return out


# ---------------------------------------------------------------- report


def _p(v) -> str:
    return "n/a" if v is None else f"{v:.1f} %"


def report() -> str:
    s = json.loads((STREETS_DIR / "results.json").read_text(encoding="utf-8"))["streets"]
    m = s["main"]
    lines = []
    for key, title in (("A", "Key A (EMSR773 observed flood or a water mark within 10 m)"),
                       ("B", "Key B (UPV depth above 0.1 m, inside the UPV outlines)")):
        lines += [f"Equal street length, {title}:", "",
                  "| Town | Streets (km) | Flooded (km) | Official length (km) | Hit rate: zones | Hit rate: terrain | "
                  "Hit rate: simulated | Precision: zones | Precision: terrain | Precision: simulated | Chance precision |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for t in [*TOWNS, "total"]:
            row = [m["equal_length"][r][key]["total" if t == "total" else "towns"] for r in
                   ("official_union", "terrain_hand", "simulated_depth")]
            row = [r if t == "total" else r[t] for r in row]
            o, te, si = row
            lines.append(f"| {'**Total**' if t == 'total' else t} | {o['street_km']:.1f} | {o['flooded_km']:.1f} | "
                         f"{o['flagged_km']:.1f} | {_p(o['hit_rate_pct'])} | {_p(te['hit_rate_pct'])} | "
                         f"{_p(si['hit_rate_pct'])} | {_p(o['precision_pct'])} | {_p(te['precision_pct'])} | "
                         f"{_p(si['precision_pct'])} | {_p(o['chance_precision_pct'])} |")
        lines.append("")
    lines += ["Every method at its own length, the 10 towns together:", "",
              "| Method | Flagged (km) | Share of streets | Key A hit rate | Key A precision | Key B flagged (km) | "
              "Key B hit rate | Key B precision |", "|---|---|---|---|---|---|---|---|"]
    for name, blk in m["methods"].items():
        a, b = blk["A"]["total"], blk["B"]["total"]
        lines.append(f"| `{name}` | {a['flagged_km']:.1f} | {_p(a['flagged_pct_of_streets'])} | {_p(a['hit_rate_pct'])} | "
                     f"{_p(a['precision_pct'])} | {b['flagged_km']:.1f} | {_p(b['hit_rate_pct'])} | "
                     f"{_p(b['precision_pct'])} |")
    lines += ["", "Reach: the official zones and the SIMULATED extent at their own length, key A:", "",
              "| Town | Zones: km | Zones: hit rate | Zones: precision | Simulated: km | Simulated: hit rate | "
              "Simulated: precision |", "|---|---|---|---|---|---|---|"]
    for t in [*TOWNS, "total"]:
        o = m["methods"]["official_union"]["A"]
        si = m["methods"]["simulated_depth_above_0p3m"]["A"]
        o, si = (o["total"], si["total"]) if t == "total" else (o["towns"][t], si["towns"][t])
        lines.append(f"| {'**Total**' if t == 'total' else t} | {o['flagged_km']:.1f} | {_p(o['hit_rate_pct'])} | "
                     f"{_p(o['precision_pct'])} | {si['flagged_km']:.1f} | {_p(si['hit_rate_pct'])} | "
                     f"{_p(si['precision_pct'])} |")
    lines += ["", "Sensitivity, equal street length, 10 towns (hit rate zones / terrain / simulated):"]
    sens = {"key A from EMSR773 alone": m["key_sensitivity"]["key_a_emsr773_only"],
            "key A from the marks alone": m["key_sensitivity"]["key_a_marks_only"],
            "tracks included, key A": {r: v["A"] for r, v in s["with_tracks"]["equal_length"].items()},
            "tracks included, key B": {r: v["B"] for r, v in s["with_tracks"]["equal_length"].items()}}
    ph = m.get("key_b_surveyed_area_only_post_hoc")
    if ph:
        sens["key B, surveyed area only (POST-HOC)"] = ph["equal_length"]
    for label, blk in sens.items():
        vals = " / ".join(_p(blk[r]["total"]["hit_rate_pct"]) for r in ("official_union", "terrain_hand", "simulated_depth"))
        lines.append(f"- {label}: {vals} (flooded {blk['official_union']['total']['flooded_km']:.1f} km)")
    text = "\n".join(lines)
    print(text)
    return text


RUN_LABELS = {"ifs_20241028T12": "Run A, forecast of 28 Oct 12 UTC", "ifs_20241029T00": "Run A, forecast of 29 Oct 00 UTC",
              "buildings": "Run B, gauged rain and buildings", "ifs_20241029T06": "Run A3, forecast of 29 Oct 06 UTC"}


def report_runs() -> str:
    """The tables of docs/STREETS.md, 'Two more simulations', printed from results.json (PR #43 run beside them)."""
    res = json.loads((STREETS_DIR / "results.json").read_text(encoding="utf-8"))
    old, new = res["streets"]["main"], res["streets_more_runs"]["main"]
    runs = [r for r in EXTRA_SIM_RUNS if f"simulated_{r}_depth_above_0p3m" in new["methods"]]
    own = [("Official, any zone", new["methods"]["official_union"]),
           ("SIMULATED, gauged rain (PR #39, PR #43 numbers)", old["methods"]["simulated_depth_above_0p3m"])]
    own += [(RUN_LABELS[r], new["methods"][f"simulated_{r}_depth_above_0p3m"]) for r in runs]
    lines = ["Own extent (depth above 0.3 m), 10 towns:", "",
             "| Method | Flagged (km) | Key A: hit rate | Key A: precision | Key B: flagged inside (km) | "
             "Key B: hit rate | Key B: precision |", "|---|---|---|---|---|---|---|"]
    for name, m in own:
        a, b = m["A"]["total"], m["B"]["total"]
        lines.append(f"| {name} | {a['flagged_km']:,.1f} | {_p(a['hit_rate_pct'])} | {_p(a['precision_pct'])} | "
                     f"{b['flagged_km']:,.1f} | {_p(b['hit_rate_pct'])} | {_p(b['precision_pct'])} |")
    eq = [("Official, any zone", new["equal_length"]["official_union"]),
          ("SIMULATED, gauged rain (PR #39, PR #43 numbers)", old["equal_length"]["simulated_depth"])]
    eq += [(RUN_LABELS[r], new["equal_length"][f"simulated_{r}_depth"]) for r in runs]
    lines += ["", "Equal street length (each ranking cut to the zones' length, town by town), 10 towns:", "",
              "| Method | Key A: hit rate | Key A: precision | Key B: hit rate | Key B: precision |",
              "|---|---|---|---|---|"]
    for name, m in eq:
        a, b = m["A"]["total"], m["B"]["total"]
        lines.append(f"| {name} | {_p(a['hit_rate_pct'])} | {_p(a['precision_pct'])} | {_p(b['hit_rate_pct'])} | "
                     f"{_p(b['precision_pct'])} |")
    lines += ["", "Own extent, key A, by town (hit rate / precision):", "",
              "| Town | " + " | ".join(n for n, _ in own) + " |", "|---|" + "---|" * len(own)]
    for t in TOWNS:
        cells = [f"{_p(m['A']['towns'][t]['hit_rate_pct'])} / {_p(m['A']['towns'][t]['precision_pct'])}" for _, m in own]
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines += ["", "Outside every official zone (descriptive), key A:"]
    d_old = res["streets"]["main"]["descriptive"]
    lines.append(f"- PR #43 run: {d_old['simulated_outside_zones']['A']['total']['flagged_km']:.1f} km, "
                 f"{_p(d_old['simulated_outside_zones']['A']['total']['precision_pct'])} flooded")
    for r in runs:
        blk = new["descriptive"][f"simulated_{r}_outside_zones"]["A"]["total"]
        lines.append(f"- {RUN_LABELS[r]}: {blk['flagged_km']:.1f} km, {_p(blk['precision_pct'])} flooded, "
                     f"catching {blk['flagged_and_flooded_km']:.1f} km of flooded street")
    lines.append(f"- chance outside the zones: {_p(new['descriptive']['outside_zones_chance_precision']['A'])}")
    # the ceiling, on the streets inside the UPV outlines
    ka, ce = new["key_a_inside_upv_outlines"], new["ceiling"]
    inside = ce["key_b_against_key_a"]["total"]["street_km"]
    lines += ["", f"Inside the UPV outlines ({inside:,.1f} km of street), own extent:", "",
              "| Method | Flagged (km) | Key A: found | Key A: really flooded |", "|---|---|---|---|"]
    t = ce["key_b_against_key_a"]["total"]
    lines.append(f"| Ceiling (two records of the same flood): the UPV map against key A | {t['flagged_km']:,.1f} | "
                 f"{_p(t['hit_rate_pct'])} | {_p(t['precision_pct'])} |")
    rows_in = [("Official, any zone", "official_union")]
    if "simulated_depth_above_0p3m" in ka["own_length"]:
        rows_in.append(("SIMULATED, gauged rain (rebuilt)", "simulated_depth_above_0p3m"))
    rows_in += [(RUN_LABELS[r], f"simulated_{r}_depth_above_0p3m") for r in runs]
    for name, key in rows_in:
        t = ka["own_length"][key]["total"]
        lines.append(f"| {name} | {t['flagged_km']:,.1f} | {_p(t['hit_rate_pct'])} | {_p(t['precision_pct'])} |")
    t = ce["key_a_against_key_b"]["total"]
    lines += ["", f"Ceiling the other way: key A against the UPV map (key B): flagged {t['flagged_km']:,.1f} km, "
                  f"found {_p(t['hit_rate_pct'])}, really flooded {_p(t['precision_pct'])}"]
    text = "\n".join(lines)
    print(text)
    return text


STEPS = ("fetch", "fetch-osm", "fetch-upv", "score", "report", "score-runs", "report-runs")


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
    elif args.step == "score":
        score(args.zones_interim)
    elif args.step == "report":
        report()
    elif args.step == "score-runs":
        score(args.zones_interim, block="streets_more_runs")
    elif args.step == "report-runs":
        report_runs()


if __name__ == "__main__":
    main()
