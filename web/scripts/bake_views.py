"""Bake the four NISAR views as light web assets, with every number they show and the file it comes from.

    python web/scripts/bake_views.py                                    # every view of every site
    python web/scripts/bake_views.py --views swipe timeline --sites pego_oliva

Run it with the pipeline environment; it moves to the repo root itself. The views answer "where is NISAR?" with
what only NISAR gives:

    swipe      Water the same evening: the Sentinel-1 map (OPERA DSWx-S1, open water and flooded vegetation)
               against NISAR's (the team CV model v1 at its pre-registered threshold 0.3: water where the
               probability of open water or flooded vegetation is at least 0.3, the exported CV layer), on 18 Jun
               (rice), 16 Oct and 28 Oct (before and after the DANA), at Albufera and Pego-Oliva.
    coherence  NISAR dark pixels (5x5 filtered HH below -15 dB) against dark pixels whose 12-day coherence is
               below 0.25 (methods 2 and 4 of docs/CV_BENCHMARK.md). At L-band smooth dry ground is as dark as
               water, but it keeps its radar phase over 12 days and water does not. Donana on 7 Sep (a window over
               the dry marsh) and Albufera on the clear date with the most dark ground among those with a pair.
    soil       NISAR soil moisture (L3 SME2, 200 m, provisional) of the last dates before the DANA (18 to 19 Oct),
               from the maps pipeline/soil_moisture.py stores for the spatial model, against every earlier date.
    timeline   NISAR water on every pass of track 066 D (every 12 days), with its hectares, the share of the land
               the radar saw and the share an optical satellite saw clear within a day of the pass.

Writes under web/public/layers/<site>/ (every image covers the bounds in views.json, so they stack):

    views/ground.webp                   cloud-free ground: EOX Sentinel-2 cloudless 2017 from the local zoom 12 tiles
    views/swipe/<date>_s1.webp          RGBA: water blue, ground the map did not cover grey, the rest transparent
    views/swipe/<date>_nisar.webp
    views/coherence/<date>_photo.webp   Sentinel-2 true colour of that day (Element 84 Earth Search), not retouched
    views/coherence/<date>_dark.webp    every dark pixel (blue)
    views/coherence/<date>_coh.webp     only the dark pixels with low coherence (blue)
    views/coherence/<date>_removed.webp the dark but coherent ground the rule takes out (amber), to lay over the photo
    views/soil/<date>.webp              soil moisture of each 200 m cell on a dry to wet ramp
    views/timeline/<nn>.webp            NISAR water of each pass
    views.json                          dates, files and bytes, captions, and every number with its source files

Masks and numbers come from the 20 m analysis grid of the stacks (0.04 ha a pixel), as in docs/CV_BENCHMARK.md;
the pictures are those masks put on the Web Mercator zoom 13 lattice of meta.json (nearest neighbour), which is
the existing pixel size of the map pages. Soil moisture is counted on its own 200 m cells. Hectares leave out the
sea. Pictures are lossless WebP (lossy for the two photographs) and the page asks for them with ?v=<baked_utc>.

Needs the data folders of the main checkout (data/stack, data/coherence, data/optical, data/interim, data/raw), the
soil moisture maps in data/context (python -m pipeline.soil_moisture), and the network for Earth Search.
Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web"
os.chdir(REPO)  # pipeline.cv.coherence reads data/coherence relative to the repo root
sys.path[:0] = [str(REPO), str(WEB / "scripts")]

import rasterio  # noqa: E402
from PIL import Image  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.transform import Affine  # noqa: E402
from rasterio.warp import Resampling, reproject  # noqa: E402

import bake_water as bw  # noqa: E402  (the zoom 13 lattice of the map pages)
import fetch_optical as fo  # noqa: E402  (Sentinel-2 true colour from Earth Search)
from pipeline import soil_moisture as smx  # noqa: E402
from pipeline.config import STACK_DIR  # noqa: E402
from pipeline.cv.baseline import area_ha  # noqa: E402
from pipeline.cv.benchmark_optical import (  # noqa: E402
    COUNTS_PATH, DARK_DB, MIN_CLEAR_SHARE, TRAINING_SITES, V1_THRESHOLD, cache_path, load_cached, regions_of,
)
from pipeline.cv.coherence import coherence_for, coherence_path  # noqa: E402
from pipeline.cv.data import dswx_on_grid, open_stack  # noqa: E402
from pipeline.cv.dataset import OPTICAL_DIR, optical_classes  # noqa: E402
from pipeline.cv.evaluate import (  # noqa: E402
    CONTEXT_DIR, DSWX_INUNDATED_VEG, DSWX_INVALID, DSWX_OPEN_WATER, DSWX_RAW, MAX_GAP_H, date_index, dswx_files,
    permanent_water, scene_db,
)

OUT_ROOT = WEB / "public" / "layers"
BENCHMARK = REPO / "data" / "metrics" / "cv_optical_benchmark.json"
MANIFEST = REPO / "data" / "manifest.json"
THIS = "web/scripts/bake_views.py"

SITES = {
    "albufera": {"title": "Albufera lagoon and rice fields", "bbox": bw.SITES["albufera"]["bbox"], "stack": "066_D_069"},
    "pego_oliva": {"title": "Pego-Oliva marsh", "bbox": bw.SITES["pego_oliva"]["bbox"], "stack": "066_D_069"},
    # Not a map page: its own window over the dry marsh (the marismas), which holds most of the dark dry ground of
    # the site box (-6.42, 36.88, -6.08, 37.20); the share is in views.json.
    "donana": {"title": "Doñana marsh", "bbox": (-6.42, 36.88, -6.22, 37.15), "stack": "023_D_070"},
}
VIEWS = ("swipe", "coherence", "soil", "timeline")
WINDOWED = ("donana",)  # sites whose pictures show a window of the site box, not all of it
SITE_VIEWS = {"albufera": VIEWS, "pego_oliva": ("swipe", "soil", "timeline"), "donana": ("coherence",)}

SWIPE_DAYS = ("2026-06-18", "2026-10-16", "2026-10-28")
# Where a page may zoom first: the Copernicus EMS flood map of the DANA (EMSR935, drawn by people), its flooded
# areas of at least 1 ha (782 of its 889 ha; a few small ones lie far north), with half its size again on each side.
FOCUS = {"pego_oliva": (REPO / "data" / "labels" / "pego_oliva_emsr935_flood.geojson", 1.0, 0.5)}
COH_CUT = 0.25                       # chosen on the training sites (data/metrics/cv_optical_select.json)
COH_DAY = {"donana": "2026-09-07"}   # the dry-marsh case of docs/CV_BENCHMARK.md section 2
COH_PICK_CLEAR = 0.9                 # elsewhere: the date with a pair, an answer key this clear, and the most dark ground
SOIL_BEFORE = "2026-10-18"           # the DANA reached the coast on 18 Oct (AEMET: the episode ran 18 to 19 Oct)
SOIL_LAYERS = 3                      # the last dates before it get a picture
FLOODED = {"pego_oliva": REPO / "data" / "labels" / "pego_oliva_emsr935_flood.geojson"}  # what the storm flooded

# Classes of a picture, and how they are drawn. The blue and the amber are those of the story pages (story.css).
DRY, WATER, UNSEEN, REMOVED, OUT = 0, 1, 2, 3, 255
LUT = np.zeros((256, 4), "uint8")
LUT[WATER] = (42, 143, 255, 235)
LUT[UNSEEN] = (10, 16, 24, 125)
LUT[REMOVED] = (255, 171, 74, 170)
LEGEND = {
    "water": "#2a8fff", "not_covered": "rgba(10,16,24,0.49)", "dry_ground_removed": "#ffab4a",
}
# Soil moisture ramp, dry to wet, lightness falling all the way (m3/m3)
SOIL_STOPS = [(0.05, (243, 231, 200)), (0.15, (214, 196, 150)), (0.25, (150, 190, 190)),
              (0.35, (70, 150, 210)), (0.45, (30, 90, 190)), (0.55, (15, 45, 120))]
SOIL_ALPHA = 215

EOX_CREDIT = ("EOxCloudless 2017, https://cloudless.eox.at, by EOX IT Services GmbH (contains modified Copernicus "
              "Sentinel data 2017), CC BY 4.0")
S2_CREDIT = "Contains modified Copernicus Sentinel data 2026, Element 84 Earth Search"


# ---------------------------------------------------------------- small helpers

def rel(path) -> str:
    """A path as the repo writes it (forward slashes, from the repo root)."""
    p = Path(path)
    if p.is_absolute():
        try:
            return p.relative_to(REPO).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def num(value, unit: str, what: str, *sources) -> dict:
    return {"value": value, "unit": unit, "what": what,
            "source": [s if isinstance(s, dict) else rel(s) for s in sources] + [THIS]}


def cited(value, unit: str, what: str, file: Path, pointer: str) -> dict:
    """A number taken as it is from a result file of the repo."""
    return {"value": value, "unit": unit, "what": what, "source": [{"file": rel(file), "path": pointer}]}


def ha_txt(v: float) -> str:
    return f"{round(v):,} ha"


def pct_txt(share: float) -> str:
    v = share * 100
    return f"{v:.1f} %" if 0 < v < 1 or 99 < v < 100 else f"{v:.0f} %"


def two(v: float) -> str:
    """Two decimals, half up (0.205 is 0.21)."""
    from decimal import ROUND_HALF_UP, Decimal

    return str(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def day_txt(day: str) -> str:
    d = datetime.strptime(day[:10], "%Y-%m-%d")
    return f"{d.day} {d.strftime('%b')}"


def share(a: np.ndarray, b: np.ndarray) -> float:
    n = int(np.count_nonzero(b))
    return float(np.count_nonzero(a & b) / n) if n else 0.0


def r1(v: float) -> float:
    return round(float(v), 1)


def r3(v: float) -> float:
    return round(float(v), 3)


class Grid:
    """The zoom 13 Web Mercator lattice of one view."""

    def __init__(self, bbox):
        self.transform, self.width, self.height = bw.web_grid(bbox)
        x0, y1 = self.transform.c, self.transform.f
        x1, y0 = x0 + self.width * bw.RES, y1 - self.height * bw.RES
        to_deg = Transformer.from_crs(3857, 4326, always_xy=True)
        (west, east), (south, north) = to_deg.transform([x0, x1], [y0, y1])
        self.extent = (x0, y0, x1, y1)
        self.bounds = [round(west, 7), round(south, 7), round(east, 7), round(north, 7)]

    def coarse(self, k: int = 2) -> tuple[Affine, int, int]:
        """The same box at 1/k of the pixels (for the photographs), exactly covering the bounds."""
        w, h = math.ceil(self.width / k), math.ceil(self.height / k)
        x0, y0, x1, y1 = self.extent
        return Affine((x1 - x0) / w, 0, x0, 0, -(y1 - y0) / h, y1), w, h


def save_rgba(classes: np.ndarray, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(LUT[classes], "RGBA").save(path, "WEBP", lossless=True, quality=100, method=6)
    return path.stat().st_size


def on_web(classes: np.ndarray, ds, grid: Grid) -> np.ndarray:
    """uint8 classes of the stack grid on the web grid (nearest); OUT where the stack has nothing."""
    out = np.full((grid.height, grid.width), OUT, "uint8")
    reproject(classes, out, src_transform=ds["HH"].rio.transform(), src_crs=ds["HH"].rio.crs, src_nodata=OUT,
              dst_transform=grid.transform, dst_crs="EPSG:3857", dst_nodata=OUT, resampling=Resampling.nearest)
    return out


def picture(water: np.ndarray, seen: np.ndarray, sea: np.ndarray, removed: np.ndarray | None = None) -> np.ndarray:
    cls = np.where(seen, np.where(water, WATER, DRY), UNSEEN).astype("uint8")
    if removed is not None:
        cls[seen & removed & ~water] = REMOVED
    cls[sea] = OUT
    return cls


def in_view(ds, grid: Grid) -> np.ndarray:
    """Stack pixels whose centre lies inside the view box (for Albufera and Pego-Oliva almost all of them)."""
    tr = ds["HH"].rio.transform()
    h, w = ds.sizes["y"], ds.sizes["x"]
    cols, rows = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    xs, ys = tr.c + cols * tr.a + rows * tr.b, tr.f + cols * tr.d + rows * tr.e
    mx, my = Transformer.from_crs(ds["HH"].rio.crs, 3857, always_xy=True).transform(xs, ys)
    x0, y0, x1, y1 = grid.extent
    return (mx >= x0) & (mx < x1) & (my > y0) & (my <= y1)


def sea_of(site: str, shape: tuple[int, int]) -> np.ndarray:
    with rasterio.open(CONTEXT_DIR / f"{site}_sea_20m.tif") as src:
        sea = src.read(1) == 1
    if sea.shape != shape:
        raise ValueError(f"{site}: the sea mask is not on the stack grid")
    return sea


def optical_record(site: str, stack: str, day: str) -> dict | None:
    """The answer key entry of data/optical/index.json: which optical days and granules made the map."""
    for e in json.loads((OPTICAL_DIR / "index.json").read_text(encoding="utf-8")):
        if e.get("site") == site and e.get("stack") == stack and e.get("date") == day:
            return e
    return None


def stack_file(site: str, stack: str) -> Path:
    return STACK_DIR / f"{site}_{stack}.nc"


def granule_at(ds, t: int) -> str:
    return str(ds["granule_ur"].values[t]) if "granule_ur" in ds else ""


def nisar_time(granule: str, day: str) -> str:
    m = re.search(r"_(\d{8})T(\d{6})_", granule)
    if not m:
        return f"{day}T00:00:00Z"
    d, t = m.groups()
    return f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}Z"


def clock(time_utc: str) -> str:
    return time_utc[11:16]


# ---------------------------------------------------------------- the ground to draw on

def bake_ground(grid: Grid, out_dir: Path) -> dict | None:
    """EOX Sentinel-2 cloudless 2017 at zoom 12 from the tiles the pages already ship, cut to the view box."""
    tiles = WEB / "public" / "tiles" / "base" / "12"
    res12 = bw.RES * 2
    x0, y0, x1, y1 = grid.extent
    c0, c1 = math.floor((x0 + bw.ORIGIN) / res12), math.ceil((x1 + bw.ORIGIN) / res12)
    r0, r1 = math.floor((bw.ORIGIN - y1) / res12), math.ceil((bw.ORIGIN - y0) / res12)
    tx0, tx1, ty0, ty1 = c0 // 256, (c1 - 1) // 256, r0 // 256, (r1 - 1) // 256
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), "uint8")
    missing = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            path = tiles / str(tx) / f"{ty}.jpg"
            if not path.exists():
                missing += 1
                continue
            tile = np.asarray(Image.open(path).convert("RGB"))
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = tile
    if missing == (tx1 - tx0 + 1) * (ty1 - ty0 + 1):
        print("  ground: no local tiles cover this box")
        return None
    src_t = Affine(res12, 0, tx0 * 256 * res12 - bw.ORIGIN, 0, -res12, bw.ORIGIN - ty0 * 256 * res12)
    dst_t, w, h = grid.coarse(2)
    rgb = np.zeros((3, h, w), "uint8")
    for b in range(3):
        reproject(mosaic[..., b], rgb[b], src_transform=src_t, src_crs="EPSG:3857", dst_transform=dst_t,
                  dst_crs="EPSG:3857", resampling=Resampling.bilinear)
    path = out_dir / "views" / "ground.webp"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.moveaxis(rgb, 0, -1)).save(path, "WEBP", quality=72, method=6)
    print(f"  ground: {w} x {h} px, {missing} tiles missing, {path.stat().st_size / 1e3:.0f} kB", flush=True)
    return {"file": "views/ground.webp", "bytes": path.stat().st_size, "width": w, "height": h,
            "source": "EOX Sentinel-2 cloudless 2017 (web/public/tiles/base/12)", "credit": EOX_CREDIT}


def bake_photo(site: str, day: str, grid: Grid, out_dir: Path) -> dict | None:
    """The Sentinel-2 true colour picture of the day (or of the nearest day within one), at half the pixels."""
    bbox = SITES[site]["bbox"]
    for offset in (0, -1, 1):
        d = (np.datetime64(day) + np.timedelta64(offset, "D")).astype(str)
        items = fo.scenes(bbox, d)
        if not items:
            continue
        transform, w, h = grid.coarse(2)
        rgb, used = fo.read_day(items, transform, w, h)
        filled = float((rgb.max(axis=0) > 0).mean())
        if filled < 0.5:
            continue
        path = out_dir / "views" / "coherence" / f"{day}_photo.webp"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.moveaxis(rgb, 0, -1)).save(path, "WEBP", quality=72, method=6)
        main = max(used, key=lambda u: u["share"])
        print(f"  photo {d}: {[(u['id'], u['cloud_pct'], u['share']) for u in used]}, "
              f"{path.stat().st_size / 1e3:.0f} kB", flush=True)
        return {"file": rel(path.relative_to(out_dir)), "bytes": path.stat().st_size, "day": d,
                "time_utc": main["time_utc"], "scenes": [u["id"] for u in used], "cloud_pct": main["cloud_pct"],
                "covered": round(filled, 3), "source": "Sentinel-2 L2A true colour (visual), Element 84 Earth Search",
                "credit": S2_CREDIT}
    print(f"  photo: no Sentinel-2 picture within a day of {day}")
    return None


# ---------------------------------------------------------------- view 1: Sentinel-1 against NISAR, the same evening

def dswx_entry(site: str, stack: str, day: str) -> dict | None:
    for e in json.loads((DSWX_RAW / site / "index.json").read_text(encoding="utf-8")):
        if e["stack_id"] == stack and e["date"] == day:
            return e
    return None


def s1_time(entry: dict) -> str:
    stamps = sorted(re.search(r"_(\d{8})T(\d{6})Z_", Path(f.replace("\\", "/")).name).groups()
                    for f in entry["files"])
    d, t = stamps[0]
    return f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}Z"


def training_note(site: str, what: str) -> list[dict]:
    """On a site the model learned from, its numbers are not a test (docs/CV_BENCHMARK.md section 5)."""
    if site not in TRAINING_SITES:
        return []
    return [{"text": f"{SITES[site]['title'].split(' ')[0]} is one of the three sites {what}, so these numbers are not a "
                     f"test. Pego-Oliva and Doñana are test sites.",
             "numbers": {}, "source": [{"file": "docs/CV_BENCHMARK.md", "path": "sections 5 and 7"}]}]


def benchmark_context(site: str) -> list[dict]:
    """Benchmark lines that put one evening in its place (docs/CV_BENCHMARK.md section 10)."""
    b = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    out = []
    table = next((x for x in b["tables"] if x["group"] == site and x["set"] == "with_sentinel1" and x["land"] == "all"),
                 None)
    if table:
        i = next(k for k, x in enumerate(b["tables"]) if x is table)
        v1, s1 = table["methods"]["v1_preregistered_0.3"]["iou"], table["methods"]["sentinel1_dswx"]["iou"]
        out.append({
            "text": (f"Across the {table['dates']} same-evening dates of the benchmark here, scored on open water "
                     f"against optical maps, the two are level: IoU {v1:.3f} for NISAR and {s1:.3f} for Sentinel-1."),
            "numbers": {
                "nisar_iou": cited(v1, "IoU", "v1 at 0.3, changing open water, same-evening dates", BENCHMARK,
                                   f"tables[{i}].methods.v1_preregistered_0.3.iou"),
                "s1_iou": cited(s1, "IoU", "Sentinel-1 map, same pixels", BENCHMARK,
                                f"tables[{i}].methods.sentinel1_dswx.iou"),
            }})
    flood = b["dana_flood_emsr935"]
    if flood["site"] == site:
        v1 = flood["methods"]["v1_preregistered_0.3"]["water_gain"]
        s1 = flood["methods"]["sentinel1_dswx"]["water_gain"]
        out.append({
            "text": (f"On the new flood water ({day_txt(flood['before'])} to {day_txt(flood['after'])}, against the "
                     f"Copernicus EMS map drawn by people) NISAR scores IoU {v1['iou']:.3f}, Sentinel-1 {s1['iou']:.3f}."),
            "numbers": {
                "nisar_gain_iou": cited(v1["iou"], "IoU", "water gain, v1 at 0.3, against EMSR935", BENCHMARK,
                                        "dana_flood_emsr935.methods.v1_preregistered_0.3.water_gain.iou"),
                "s1_gain_iou": cited(s1["iou"], "IoU", "water gain, Sentinel-1 map, same pixels", BENCHMARK,
                                     "dana_flood_emsr935.methods.sentinel1_dswx.water_gain.iou"),
                "nisar_gain_precision": cited(v1["precision"], "share", "of the new water NISAR maps, inside the EMS map",
                                              BENCHMARK, "dana_flood_emsr935.methods.v1_preregistered_0.3.water_gain.precision"),
                "s1_gain_precision": cited(s1["precision"], "share", "of the new water Sentinel-1 maps, inside the EMS map",
                                           BENCHMARK, "dana_flood_emsr935.methods.sentinel1_dswx.water_gain.precision"),
            }})
    return out


def bake_swipe(site: str, ds, grid: Grid, out_dir: Path, sea: np.ndarray, perm: np.ndarray, view: np.ndarray) -> dict:
    stack = SITES[site]["stack"]
    land = ~sea & view
    days = date_index(ds)
    items = []
    for day in SWIPE_DAYS:
        entry = dswx_entry(site, stack, day)
        if day not in days or not entry or entry["hours_from_nisar"] is None or entry["hours_from_nisar"] > MAX_GAP_H:
            print(f"  swipe {day}: no same-evening Sentinel-1 map")
            continue
        t = days[day]
        tiles = dswx_files(entry)
        dswx = dswx_on_grid(ds, tiles)
        cached = load_cached("v1", site, stack, day)
        if cached is None:
            print(f"  swipe {day}: no cached NISAR probabilities")
            continue
        p_any = cached[1]
        n_ok = np.isfinite(p_any)
        n_water = n_ok & (np.nan_to_num(p_any, nan=0.0) >= V1_THRESHOLD)
        s_ok = ~np.isin(dswx, DSWX_INVALID)
        s_water = s_ok & np.isin(dswx, (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG))
        both = land & n_ok & s_ok

        files = {}
        for name, water, ok in (("s1", s_water, s_ok), ("nisar", n_water, n_ok)):
            path = out_dir / "views" / "swipe" / f"{day}_{name}.webp"
            size = save_rgba(on_web(picture(water, ok, sea), ds, grid), path)
            files[name] = {"file": f"views/swipe/{day}_{name}.webp", "bytes": size}

        granule = granule_at(ds, t)
        t_nisar, t_s1 = nisar_time(granule, day), s1_time(entry)
        minutes = round(abs((datetime.fromisoformat(t_nisar[:-1]) - datetime.fromisoformat(t_s1[:-1])).total_seconds()) / 60)
        cache_file = cache_path("v1", site, stack, day)
        src_n = (stack_file(site, stack), cache_file)
        src_s = tuple(tiles)
        a = lambda m: r1(area_ha(m))  # noqa: E731
        numbers = {
            "minutes_apart": num(minutes, "min", "between the NISAR and the Sentinel-1 pass", stack_file(site, stack),
                                 DSWX_RAW / site / "index.json"),
            "land_both_cover": num(r3(share(both, land)), "share", "of the land (sea left out) both maps cover",
                                   *src_n, *src_s),
            "nisar_water_ha": num(a(n_water & both), "ha", "water NISAR maps (v1 at 0.3) on the land both maps cover",
                                  *src_n),
            "s1_water_ha": num(a(s_water & both), "ha", "water Sentinel-1 maps (open water and flooded vegetation) there",
                               *src_s),
            "s1_flooded_vegetation_ha": num(a(both & (dswx == DSWX_INUNDATED_VEG)), "ha",
                                            "of it marked flooded vegetation by Sentinel-1", *src_s),
            "nisar_only_ha": num(a(both & n_water & ~s_water), "ha", "water only NISAR maps", *src_n, *src_s),
            "s1_only_ha": num(a(both & s_water & ~n_water), "ha", "water only Sentinel-1 maps", *src_n, *src_s),
            "both_ha": num(a(both & n_water & s_water), "ha", "water both map", *src_n, *src_s),
        }
        # The referee: an optical water map within a day (OPERA DSWx-HLS), on changing water (outside the sea and
        # permanent water), only where it is clear. Optical cannot see water under plants, so it judges two things it
        # can: how much of the open water it sees each radar maps, and what it sees where only one radar maps water.
        optical = optical_classes(site, stack, day)
        record = optical_record(site, stack, day)
        caption = [f"{day_txt(day)}, the same evening: NISAR {clock(t_nisar)}, Sentinel-1 {clock(t_s1)} UTC "
                   f"({minutes} min apart).",
                   f"NISAR maps {ha_txt(numbers['nisar_water_ha']['value'])} of water, Sentinel-1 "
                   f"{ha_txt(numbers['s1_water_ha']['value'])}; {ha_txt(numbers['nisar_only_ha']['value'])} only on "
                   f"NISAR's map, {ha_txt(numbers['s1_only_ha']['value'])} only on Sentinel-1's."]
        referee = None
        changing = both & ~perm
        if optical is not None:
            src_o = (OPTICAL_DIR / f"{site}_{stack}" / f"{day}.tif",)
            clear = changing & np.isin(optical, (0, 1, 2))
            clear_share = share(clear, changing)
            numbers["optical_clear"] = num(r3(clear_share), "share", "of the changing land the optical map saw clear",
                                           *src_o)
            if clear_share >= MIN_CLEAR_SHARE:
                wet = changing & (optical == 1)
                n_only, s_only = clear & n_water & ~s_water, clear & s_water & ~n_water
                water_o = np.isin(optical, (1, 2))
                numbers.update({
                    "optical_open_water_ha": num(a(wet), "ha", "open water the optical map sees, outside permanent water",
                                                 *src_o),
                    "nisar_finds": num(r3(share(n_water, wet)), "share", "of that open water on NISAR's map", *src_n, *src_o),
                    "s1_finds": num(r3(share(s_water, wet)), "share", "of that open water on Sentinel-1's map", *src_s, *src_o),
                    "nisar_only_clear_ha": num(a(n_only), "ha", "water only NISAR maps, where the optical map is clear",
                                               *src_n, *src_s, *src_o),
                    "nisar_only_optical_water": num(r3(share(water_o, n_only)), "share",
                                                    "of it the optical map calls water (open or partial)", *src_o),
                    "s1_only_clear_ha": num(a(s_only), "ha", "water only Sentinel-1 maps, where the optical map is clear",
                                            *src_n, *src_s, *src_o),
                    "s1_only_optical_water": num(r3(share(water_o, s_only)), "share",
                                                 "of it the optical map calls water (open or partial)", *src_o),
                })
                referee = {"optical_days": record.get("optical_dates_used") if record else None,
                           "granules": record.get("granules_used") if record else None}
                caption.append(
                    f"An optical map within a day (clear on {pct_txt(clear_share)} of it) sees "
                    f"{ha_txt(numbers['optical_open_water_ha']['value'])} of open water outside permanent water: NISAR "
                    f"finds {pct_txt(numbers['nisar_finds']['value'])} of it, Sentinel-1 "
                    f"{pct_txt(numbers['s1_finds']['value'])}.")
                caption.append(
                    f"Where only NISAR maps water, optical sees water on "
                    f"{pct_txt(numbers['nisar_only_optical_water']['value'])}; where only Sentinel-1 does, on "
                    f"{pct_txt(numbers['s1_only_optical_water']['value'])}.")
        if referee is None:
            caption.append("Too cloudy for an optical check within a day of the pass.")
        items.append({
            "date": day,
            "nisar": {**files["nisar"], "time_utc": t_nisar, "granule": granule,
                      "product": "NISAR GCOV, team CV model v1 (5 U-Nets) at 0.3", "model_cache": rel(cache_file)},
            "s1": {**files["s1"], "time_utc": t_s1, "granules": [Path(f).name for f in tiles],
                   "product": "OPERA DSWx-S1 B01_WTR (open water 1, flooded vegetation 3)"},
            "referee": referee, "caption": caption, "numbers": numbers,
        })
        print(f"  swipe {day}: NISAR {numbers['nisar_water_ha']['value']} ha, Sentinel-1 "
              f"{numbers['s1_water_ha']['value']} ha, {files['nisar']['bytes'] / 1e3:.0f} + "
              f"{files['s1']['bytes'] / 1e3:.0f} kB", flush=True)
    return {
        "title": "Sentinel-1 against NISAR, the same evening",
        "what": ("Left of the handle the Sentinel-1 water map (C band, OPERA DSWx-S1: open water and flooded "
                 "vegetation), right of it NISAR's (L band, the team CV model v1 at 0.3), from passes about an hour "
                 "apart. Grey: ground the map does not cover."),
        "legend": {"water": LEGEND["water"], "not_covered": LEGEND["not_covered"]},
        "items": items,
        "context": training_note(site, "the CV model learned from (with Sentinel-1 maps as labels)") + benchmark_context(site),
    }


# ---------------------------------------------------------------- view 2: coherence takes out the dry ground

def coherence_masks(site: str, stack: str, ds, t: int, day: str):
    hh_db, ok = scene_db(ds["HH"].values[t], ds["valid"].values[t])
    dark = ok & (hh_db < DARK_DB)
    coh = coherence_for(site, stack, day, dark.shape)
    removed = dark & (coh >= COH_CUT)
    return ok, dark, dark & ~removed, removed


def pick_coherence_day(site: str, stack: str, ds, perm: np.ndarray, region: np.ndarray) -> tuple[str, list[dict]]:
    """The date with a coherence pair and a clear answer key (COH_PICK_CLEAR) that has the most dark ground."""
    tried = []
    for day, t in date_index(ds).items():
        if coherence_path(site, stack, day) is None or not np.isfinite(ds["HV"].values[t]).any():
            continue
        optical = optical_classes(site, stack, day)
        if optical is None:
            continue
        ok, dark, _, _ = coherence_masks(site, stack, ds, t, day)
        base = ok & ~perm & region
        clear = share(np.isin(optical, (0, 1)), base)
        tried.append({"date": day, "answer_key_clear": r3(clear), "dark_ha": r1(area_ha(dark & region))})
    good = [x for x in tried if x["answer_key_clear"] >= COH_PICK_CLEAR]
    return max(good, key=lambda x: x["dark_ha"])["date"], tried


def benchmark_check(site: str, stack: str, day: str, shares: dict[str, float]) -> dict | None:
    """The false-water shares of this bake against the benchmark's own counts of the same date (the regenerable
    data/interim/cv_optical_counts.json); a difference stops the bake, so the captions cannot drift from it."""
    if not COUNTS_PATH.exists():
        return None
    rows = [r for r in json.loads(COUNTS_PATH.read_text(encoding="utf-8"))["rows"]
            if r.get("site") == site and r.get("stack") == stack and r.get("date") == day and r.get("set") == "all_dates"]
    out = {"file": rel(COUNTS_PATH), "set": "all_dates", "methods": {}}
    for method, mine in shares.items():
        row = next((r for r in rows if r["method"] == method), None)
        if row is None:
            return None
        tn, fn, fp, tp = (sum(c[k] for c in row["counts"].values()) for k in range(4))
        theirs = fp / (fp + tn)
        if abs(theirs - mine) > 1e-6:
            raise SystemExit(f"{site} {day} {method}: false water {mine:.5f} here, {theirs:.5f} in the benchmark counts")
        out["methods"][method] = {"false_water_share_of_dry": round(theirs, 5), "equal": True}
    return out


def coherence_context(site: str) -> list[dict]:
    b = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    out = []
    for group, kind in (("donana", "false"), ("pego_oliva", "iou")):
        i, table = next((k, x) for k, x in enumerate(b["tables"])
                        if x["group"] == group and x["set"] == "all_dates" and x["land"] == "all")
        th, lc = table["methods"]["nisar_threshold_15db"], table["methods"]["nisar_dark_lowcoh"]
        p = f"tables[{i}].methods"
        if kind == "false":
            out.append({
                "text": (f"Across {table['dates']} dates at Doñana, scored the same way, coherence cuts the false "
                         f"water from {pct_txt(th['false_water_share_of_dry'])} to "
                         f"{pct_txt(lc['false_water_share_of_dry'])} of the dry ground."),
                "numbers": {
                    "dark_false_water": cited(th["false_water_share_of_dry"], "share", "of the optical dry ground "
                                              "darkness alone calls water", BENCHMARK,
                                              f"{p}.nisar_threshold_15db.false_water_share_of_dry"),
                    "coh_false_water": cited(lc["false_water_share_of_dry"], "share", "with coherence", BENCHMARK,
                                             f"{p}.nisar_dark_lowcoh.false_water_share_of_dry")}})
        else:
            out.append({
                "text": (f"In the Pego-Oliva marsh, where water keeps some coherence, it does not help: across "
                         f"{table['dates']} dates scored the same way, IoU {lc['iou']:.3f} with coherence against "
                         f"{th['iou']:.3f} for darkness alone."),
                "numbers": {
                    "dark_iou": cited(th["iou"], "IoU", "darkness alone, changing open water", BENCHMARK,
                                      f"{p}.nisar_threshold_15db.iou"),
                    "coh_iou": cited(lc["iou"], "IoU", "dark and low coherence", BENCHMARK, f"{p}.nisar_dark_lowcoh.iou")}})
    return out


def bake_coherence(site: str, ds, grid: Grid, out_dir: Path, sea: np.ndarray, perm: np.ndarray,
                   view: np.ndarray) -> dict:
    stack = SITES[site]["stack"]
    land = ~sea
    region = land & view
    days = date_index(ds)
    tried = None
    if site in COH_DAY:
        day, rule = COH_DAY[site], "the dry-marsh case of docs/CV_BENCHMARK.md section 2"
    else:
        day, tried = pick_coherence_day(site, stack, ds, perm, region)
        rule = (f"the date with a coherence pair and an optical answer key at least {pct_txt(COH_PICK_CLEAR)} clear "
                f"that has the most dark ground")
    t = days[day]
    ok, dark, kept, removed = coherence_masks(site, stack, ds, t, day)
    pair = coherence_path(site, stack, day)
    index = json.loads((REPO / "data" / "coherence" / "index.json").read_text(encoding="utf-8"))
    ref, sec = pair.stem.split("_")
    pair_rec = next((e for e in index if e["site"] == site and e["stack"] == stack and e["reference_date"] == ref
                     and e["secondary_date"] == sec), {})
    files = {}
    removed_only = np.where(removed, REMOVED, OUT).astype("uint8")
    removed_only[sea] = OUT
    for name, cls in (("dark", picture(dark, ok, sea)), ("coh", picture(kept, ok, sea)), ("removed", removed_only)):
        path = out_dir / "views" / "coherence" / f"{day}_{name}.webp"
        files[name] = {"file": f"views/coherence/{day}_{name}.webp", "bytes": save_rgba(on_web(cls, ds, grid), path)}
    photo = bake_photo(site, day, grid, out_dir)

    src = (stack_file(site, stack), pair, CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif",
           CONTEXT_DIR / f"{site}_jrc_occurrence_20m.tif")
    a = lambda m: r1(area_ha(m))  # noqa: E731
    changing = region & ~perm  # the sea and permanent water (a lagoon, a river) are water, not dark ground
    numbers = {
        "dark_ha": num(a(dark & changing), "ha", "dark (HH below -15 dB) in the window, outside the sea and "
                       "permanent water", *src),
        "kept_ha": num(a(kept & changing), "ha", "of it with low coherence (below 0.25): kept as water", *src),
        "removed_ha": num(a(removed & changing), "ha", "of it coherent: called dry ground by the rule", *src),
    }
    if site in COH_DAY:
        numbers["window_holds"] = num(r3(share(view, removed & land)), "share",
                                      "of the dark coherent ground of the whole site box inside this window", *src)
    where_shown = ", in this window" if site in WINDOWED else ""
    caption = [f"{day_txt(day)}{where_shown}: {ha_txt(numbers['dark_ha']['value'])} outside permanent water look as dark "
               f"as water to the radar.",
               f"Coherence over the 12 days before ({day_txt(ref)} to {day_txt(sec)}) keeps "
               f"{ha_txt(numbers['kept_ha']['value'])} of them as water and takes out the "
               f"{ha_txt(numbers['removed_ha']['value'])} that kept their coherence, as dry ground."]
    optical = optical_classes(site, stack, day)
    if optical is not None:
        # Scored exactly as the benchmark (docs/CV_BENCHMARK.md section 5, count_site in pipeline.cv.benchmark_optical):
        # NISAR usable, neither sea nor permanent water, the optical map clear (0 or 1); the whole site box on a test
        # site, only the held-out validation blocks on a training site. Not the window of the picture.
        src_o = OPTICAL_DIR / f"{site}_{stack}" / f"{day}.tif"
        blocks = regions_of(site)
        usable = ds["valid"].values[t].astype(bool) & np.isfinite(ds["HH"].values[t]) & np.isfinite(ds["HV"].values[t]) & ok
        base = usable & ~perm & (blocks if blocks is not None else True)
        scoring = base & np.isin(optical, (0, 1))
        dry, wet = scoring & (optical == 0), scoring & (optical == 1)
        name = SITES[site]["title"].split(" ")[0]
        pixels = (f"the whole {name} box" + (", not only this window" if site in WINDOWED else "") if blocks is None
                  else f"{name}'s held-out validation blocks")

        def iou(m):
            tp, fp, fn = np.count_nonzero(m & wet), np.count_nonzero(m & dry), np.count_nonzero(~m & wet)
            return tp / (tp + fp + fn) if tp + fp + fn else 0.0

        what = f"on the benchmark's pixels: {pixels}, outside the sea and permanent water, optical map clear"
        numbers.update({
            "scored_ha": num(a(scoring), "ha", f"pixels scored, {what}", *src, src_o),
            "scored_open_water_ha": num(a(wet), "ha", "open water the optical map sees there", *src, src_o),
            "answer_key_clear": num(r3(share(scoring, base)), "share", "of the usable changing pixels the optical map "
                                    "saw clear (the benchmark's clear share)", src_o),
            "dark_false_water": num(round(share(dark, dry), 4), "share",
                                    f"of the optical dry ground darkness alone calls water, {what}", *src, src_o),
            "coh_false_water": num(round(share(kept, dry), 4), "share",
                                   f"of the optical dry ground the coherence rule calls water, {what}", *src, src_o),
            "dark_finds": num(r3(share(dark, wet)), "share", f"of the optical open water darkness alone finds, {what}",
                              *src, src_o),
            "coh_finds": num(r3(share(kept, wet)), "share", f"of the optical open water the coherence rule finds, {what}",
                             *src, src_o),
            "dark_iou": num(r3(iou(dark)), "IoU", f"darkness alone against the optical map, {what}", *src, src_o),
            "coh_iou": num(r3(iou(kept)), "IoU", f"the coherence rule against the optical map, {what}", *src, src_o),
        })
        check = benchmark_check(site, stack, day, {"nisar_threshold_15db": share(dark, dry),
                                                   f"nisar_dark_lowcoh@{COH_CUT}": share(kept, dry)})
        caption.append(f"Scored as in the benchmark: {pixels}, outside the sea and permanent water, where the optical "
                       f"map of the day is clear ({ha_txt(numbers['scored_ha']['value'])}).")
        caption.append(f"There darkness alone calls {pct_txt(numbers['dark_false_water']['value'])} of the dry ground "
                       f"water, coherence {pct_txt(numbers['coh_false_water']['value'])}.")
        if numbers["scored_open_water_ha"]["value"] >= 50:
            caption.append(f"The price: of the {ha_txt(numbers['scored_open_water_ha']['value'])} of open water there, "
                           f"coherence finds {pct_txt(numbers['coh_finds']['value'])}, darkness alone "
                           f"{pct_txt(numbers['dark_finds']['value'])}.")
        else:
            caption.append(f"Those pixels hold only {ha_txt(numbers['scored_open_water_ha']['value'])} of open water, "
                           f"too little to say what coherence costs there.")
        record = optical_record(site, stack, day)
    else:
        record, check = None, None
    print(f"  coherence {day}: dark {numbers['dark_ha']['value']} ha, kept {numbers['kept_ha']['value']} ha, "
          f"{files['dark']['bytes'] / 1e3:.0f} + {files['coh']['bytes'] / 1e3:.0f} kB", flush=True)
    return {
        "title": "Coherence takes out the dry ground",
        "what": ("At L-band smooth dry ground is as dark as water. Over 12 days water loses its radar phase and dry "
                 "ground keeps it, so NISAR's coherence tells them apart. Off: every dark pixel (HH below -15 dB). "
                 "On: only dark pixels with low coherence (below 0.25) stay water. The amber layer, to lay on top if "
                 "wanted, is the dark ground coherence takes out."),
        "legend": {"water": LEGEND["water"], "dry_ground_removed": LEGEND["dry_ground_removed"],
                   "not_covered": LEGEND["not_covered"]},
        "items": [{
            "date": day, "rule": rule, "tried": tried, **files, "photo": photo,
            "pair": {"file": rel(pair), "granule": pair_rec.get("granule_ur"), "maturity": pair_rec.get("maturity")},
            "nisar": {"granule": granule_at(ds, t), "time_utc": nisar_time(granule_at(ds, t), day)},
            "answer_key": {"optical_days": record.get("optical_dates_used"), "granules": record.get("granules_used")}
            if record else None,
            "caption": caption, "numbers": numbers, "benchmark_check": check,
        }],
        "context": training_note(site, "the coherence cut of 0.25 was chosen on") + coherence_context(site),
    }


# ---------------------------------------------------------------- view 3: soil wetness before the storm

def soil_colours(sm: np.ndarray) -> np.ndarray:
    v = np.clip(sm, SOIL_STOPS[0][0], SOIL_STOPS[-1][0])
    xs = [s[0] for s in SOIL_STOPS]
    rgb = np.stack([np.interp(v, xs, [s[1][k] for s in SOIL_STOPS]) for k in range(3)], axis=-1)
    return np.rint(rgb).astype("uint8")


def soil_maps(site: str) -> tuple[list[dict], dict]:
    """The shared SME2 maps of a site before the storm (pipeline/soil_moisture.py), oldest first: every pass over
    the site, the passes of one day averaged, on 200 m cells aligned with the 20 m site grid."""
    index = json.loads(smx.index_path(site).read_text(encoding="utf-8"))
    out = []
    for d in index["dates"]:
        if d["date"] >= SOIL_BEFORE:
            continue
        path = smx.tif_path(site, d["date"])
        with rasterio.open(path) as src:
            out.append({**d, "sm": smx.from_uint16(src.read(1)), "transform": src.transform, "crs": src.crs,
                        "path": path})
    return out, index


def tracks_of(granules: list[str]) -> list[str]:
    return sorted({m.group(1) for g in granules if (m := re.search(r"SME2_\d{3}_(\d{3}_[AD])_", g))})


def bake_soil(site: str, grid: Grid, out_dir: Path) -> dict:
    """Soil moisture of the last dates before the storm, against every earlier date compared on the same cells."""
    maps, index = soil_maps(site)
    last, before = maps[-1], maps[:-1]
    folder = out_dir / "views" / "soil"
    for old in (folder.glob("*.webp") if folder.exists() else []):
        old.unlink()
    items = []
    for m in maps[-SOIL_LAYERS:]:
        on = np.full((grid.height, grid.width), np.nan, "float32")
        reproject(m["sm"], on, src_transform=m["transform"], src_crs=m["crs"], src_nodata=np.nan,
                  dst_transform=grid.transform, dst_crs="EPSG:3857", dst_nodata=np.nan, resampling=Resampling.nearest)
        rgba = np.zeros((grid.height, grid.width, 4), "uint8")
        have = np.isfinite(on)
        rgba[have, :3] = soil_colours(on[have])
        rgba[have, 3] = SOIL_ALPHA
        path = folder / f"{m['date']}.webp"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba, "RGBA").save(path, "WEBP", lossless=True, quality=100, method=6)
        items.append({"date": m["date"], "file": f"views/soil/{m['date']}.webp", "bytes": path.stat().st_size,
                      "granules": m["granules"], "tracks": tracks_of(m["granules"]), "source": rel(m["path"])})
        print(f"  soil picture {m['date']}: {path.stat().st_size / 1e3:.0f} kB", flush=True)

    lv = last["sm"]
    series = []
    for m in maps:
        own = m["sm"][np.isfinite(m["sm"])]
        shared = np.isfinite(lv) & np.isfinite(m["sm"])
        series.append({"date": m["date"], "granules": m["granules"], "tracks": tracks_of(m["granules"]),
                       "cells": int(own.size), "median": round(float(np.median(own)), 3),
                       "p90": round(float(np.percentile(own, 90)), 3), "shared_cells": int(shared.sum()),
                       "median_shared": round(float(np.median(m["sm"][shared])), 3),
                       "last_median_shared": round(float(np.median(lv[shared])), 3)})
        print(f"  soil {m['date']} {'+'.join(series[-1]['tracks'])}: {own.size} cells, median {series[-1]['median']}; "
              f"on the {shared.sum()} cells it shares with the last date {series[-1]['median_shared']} against "
              f"{series[-1]['last_median_shared']}", flush=True)
    earlier = series[:-1]
    drier = [s for s in earlier if s["median_shared"] < s["last_median_shared"]]
    src_last = (last["path"], smx.index_path(site))
    src_all = [m["path"] for m in maps] + [smx.index_path(site)]
    s_last = series[-1]
    numbers = {
        "last_median": num(s_last["median"], "m3/m3", f"median soil moisture of the land on {day_txt(last['date'])}",
                           *src_last),
        "last_p90": num(s_last["p90"], "m3/m3", "nine in ten cells read below this", *src_last),
        "last_cells": num(s_last["cells"], "cells", "200 m cells with a value", *src_last),
        "earlier_dates": num(len(earlier), "dates", f"earlier SME2 dates from {day_txt(earlier[0]['date'])}", *src_all),
        "earlier_drier": num(len(drier), "dates", "earlier dates that read drier than the last on the cells both have",
                             *src_all),
        "earlier_median_low": num(min(s["median"] for s in earlier), "m3/m3", "lowest median of the earlier dates",
                                  *src_all),
        "earlier_median_high": num(max(s["median"] for s in earlier), "m3/m3", "highest median of the earlier dates",
                                   *src_all),
    }
    if not drier:
        rank = f"None of the {len(earlier)} earlier dates, from {day_txt(earlier[0]['date'])} on, read drier on the same cells."
    elif len(drier) == 1:
        rank = (f"Of the {len(earlier)} earlier dates, from {day_txt(earlier[0]['date'])} on, only "
                f"{day_txt(drier[0]['date'])} read drier on the same cells.")
    else:
        rank = (f"Of the {len(earlier)} earlier dates, from {day_txt(earlier[0]['date'])} on, {len(drier)} read drier "
                f"on the same cells.")
    caption = [f"{day_txt(last['date'])}, two days before the storm: half of the land read below "
               f"{two(s_last['median'])} m³/m³ of soil moisture, nine in ten cells below {two(s_last['p90'])}.", rank]
    if site in FLOODED:
        import geopandas as gpd
        from rasterio.features import rasterize

        shapes = gpd.read_file(FLOODED[site])
        shapes = shapes[shapes["class"] == "flooded_area"].to_crs(last["crs"])
        touch = rasterize(((g, 1) for g in shapes.geometry), out_shape=lv.shape, transform=last["transform"], fill=0,
                          all_touched=True).astype(bool)
        inside, rest = lv[touch & np.isfinite(lv)], lv[~touch & np.isfinite(lv)]
        numbers.update({
            "flooded_ground_median": num(round(float(np.median(inside)), 3), "m3/m3",
                                         "median of the 200 m cells touching the Copernicus EMS flood outline (EMSR935)",
                                         *src_last, FLOODED[site]),
            "flooded_ground_cells": num(int(inside.size), "cells", "cells touching the outline with a value", *src_last,
                                        FLOODED[site]),
            "other_land_median": num(round(float(np.median(rest)), 3), "m3/m3", "median of the other cells", *src_last,
                                     FLOODED[site]),
        })
        caption.append(f"Over the ground that then flooded (the {inside.size} cells touching the Copernicus EMS outline) "
                       f"it read {two(np.median(inside))}, the rest of the land {two(np.median(rest))}.")
    if len(drier) <= len(earlier) // 3:
        verdict = "The ground was not soaked when the storm came: it was among the driest readings of the season."
    elif len(drier) < len(earlier):
        wettest = max(earlier, key=lambda s: s["median_shared"] - s["last_median_shared"])
        verdict = (f"The ground was not soaked when the storm came: it read within the range of the summer, below its "
                   f"wettest date ({day_txt(wettest['date'])}, {two(wettest['median_shared'])} on the same cells).")
    else:
        verdict = "The ground was wetter than on any earlier date of the season."
    caption.append(verdict)
    return {
        "title": "Soil wetness before the storm",
        "what": ("NISAR soil moisture of the top soil (L3 SME2, a provisional product, not yet validated), as stored for "
                 "the spatial model by pipeline/soil_moisture.py: every pass over the site, the passes of one day "
                 "averaged, on 200 m cells. The last dates before the DANA of 18 to 19 Oct; dates are compared on the "
                 "cells both have."),
        "product": index.get("product"), "maturity": index.get("maturity"), "units": index.get("units"),
        "legend": {"stops": [{"value": v, "color": "#%02x%02x%02x" % c} for v, c in SOIL_STOPS], "alpha": SOIL_ALPHA / 255},
        "items": items, "series": series, "caption": caption, "numbers": numbers,
    }


# ---------------------------------------------------------------- view 4: water every 12 days, through cloud

def manifest_ha(site: str, stack: str) -> dict[str, float]:
    out = {}
    for e in json.loads(MANIFEST.read_text(encoding="utf-8")):
        if e.get("model") == "cv" and e.get("site") == site and e.get("stack") == stack and e.get("layer") == "water":
            out[e["date"]] = e.get("open_water_ha")
    return out


def bake_timeline(site: str, ds, grid: Grid, out_dir: Path, sea: np.ndarray, view: np.ndarray) -> dict:
    stack = SITES[site]["stack"]
    land = ~sea & view
    exported = manifest_ha(site, stack)
    frames = []
    folder = out_dir / "views" / "timeline"
    for old in (folder.glob("*.webp") if folder.exists() else []):
        old.unlink()
    for day, t in date_index(ds).items():
        cached = load_cached("v1", site, stack, day)
        if cached is None:
            continue
        p_any = cached[1]
        ok = np.isfinite(p_any)
        water = ok & (np.nan_to_num(p_any, nan=0.0) >= V1_THRESHOLD)
        n = len(frames)
        path = folder / f"{n:02d}.webp"
        size = save_rgba(on_web(picture(water, ok, sea), ds, grid), path)
        optical = optical_classes(site, stack, day)
        clear = share(np.isin(optical, (0, 1, 2)), land) if optical is not None else 0.0
        granule = granule_at(ds, t)
        src = (stack_file(site, stack), cache_path("v1", site, stack, day))
        src_o = (OPTICAL_DIR / f"{site}_{stack}" / f"{day}.tif",) if optical is not None else (OPTICAL_DIR / "index.json",)
        water_ha = r1(area_ha(water & land))
        frames.append({
            "date": day, "time_utc": nisar_time(granule, day), "granule": granule,
            "file": f"views/timeline/{n:02d}.webp", "bytes": size,
            "numbers": {
                "water_ha": num(water_ha, "ha", "water on NISAR's map (v1 at 0.3), sea left out", *src),
                "exported_water_ha": cited(exported.get(day), "ha", "the same layer as exported (data/cv), a check",
                                           MANIFEST, f"[model=cv, site={site}, stack={stack}, layer=water, "
                                                     f"date={day}].open_water_ha"),
                "radar_saw": num(r3(share(ok, land)), "share", "of the land the radar saw", *src),
                "optical_clear": num(r3(clear), "share", "of the land an optical map saw clear within a day "
                                     "(OPERA DSWx-HLS; 0 when there is no image)", *src_o),
            },
        })
        print(f"  timeline {day}: {water_ha} ha (exported {exported.get(day)}), radar saw {share(ok, land):.0%}, "
              f"optical clear {clear:.0%}, {size / 1e3:.0f} kB", flush=True)
    cloudy = [f for f in frames if f["numbers"]["optical_clear"]["value"] < 0.5]
    peak = max(frames, key=lambda f: f["numbers"]["water_ha"]["value"])
    low = min(frames, key=lambda f: f["numbers"]["water_ha"]["value"])
    span = (np.datetime64(frames[-1]["date"]) - np.datetime64(frames[0]["date"])).astype(int)
    missed = span // 12 + 1 - len(frames)
    caption = [
        f"{len(frames)} NISAR passes from {day_txt(frames[0]['date'])} to {day_txt(frames[-1]['date'])} on a 12-day "
        f"repeat" + (f" ({missed} pass{'es' if missed > 1 else ''} missed)" if missed > 0 else "") +
        f", each at {clock(frames[0]['time_utc'])} UTC. The radar needs no daylight and sees through cloud.",
        f"Water goes from {ha_txt(low['numbers']['water_ha']['value'])} on {day_txt(low['date'])} to "
        f"{ha_txt(peak['numbers']['water_ha']['value'])} on {day_txt(peak['date'])}.",
        f"On {len(cloudy)} of the {len(frames)} passes an optical satellite saw less than half of the land clear "
        f"within a day.",
    ]
    return {
        "title": "Water every 12 days, through cloud",
        "what": ("NISAR water (the team CV model v1 at 0.3) on every pass of track 066 D. A frame is one pass; "
                 "nothing is drawn between passes. Grey: ground the radar did not see."),
        "legend": {"water": LEGEND["water"], "not_covered": LEGEND["not_covered"]},
        "stack": stack, "frames": frames, "caption": caption,
        "context": training_note(site, "the CV model learned from (with Sentinel-1 maps as labels)"),
        "numbers": {"passes": num(len(frames), "passes", "NISAR passes of track 066 D with HH and HV",
                                  stack_file(site, stack)),
                    "cloudy_passes": num(len(cloudy), "passes", "with less than half of the land clear to optical "
                                         "within a day", OPTICAL_DIR / "index.json")},
    }


# ---------------------------------------------------------------- one site

def focus_box(site: str, grid: Grid) -> dict | None:
    """The FOCUS outline's box with a margin, as fractions of the view box (x0, y0, x1, y1 from the top left)."""
    if site not in FOCUS:
        return None
    import geopandas as gpd

    path, min_ha, margin = FOCUS[site]
    shapes = gpd.read_file(path)
    shapes = shapes[shapes["class"] == "flooded_area"]
    lat = float(shapes.total_bounds[[1, 3]].mean())
    ha = shapes.to_crs(3857).area.values / 1e4 * math.cos(math.radians(lat)) ** 2
    west, south, east, north = shapes[ha >= min_ha].total_bounds
    to_m = Transformer.from_crs(4326, 3857, always_xy=True)
    (mx0, mx1), (my0, my1) = to_m.transform([west, east], [south, north])
    x0, y0, x1, y1 = grid.extent
    fx0, fx1 = (mx0 - x0) / (x1 - x0), (mx1 - x0) / (x1 - x0)
    fy0, fy1 = (y1 - my1) / (y1 - y0), (y1 - my0) / (y1 - y0)
    dx, dy = (fx1 - fx0) * margin, (fy1 - fy0) * margin
    box = [max(0.0, fx0 - dx), max(0.0, fy0 - dy), min(1.0, fx1 + dx), min(1.0, fy1 + dy)]
    return {"box": [round(v, 4) for v in box], "from": rel(path), "rule": f"flooded areas of at least {min_ha:g} ha, "
            f"with {margin:.0%} of the box added on each side"}


def bake_site(site: str, views: tuple[str, ...]) -> Path:
    cfg = SITES[site]
    grid = Grid(cfg["bbox"])
    out_dir = OUT_ROOT / site
    meta_path = out_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if (meta["width"], meta["height"]) != (grid.width, grid.height):
            raise SystemExit(f"{site}: the view grid {grid.width} x {grid.height} is not the map grid of meta.json")
    print(f"{site}: {grid.width} x {grid.height} px at zoom {bw.ZOOM}", flush=True)
    path = out_dir / "views.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"views": {}}
    doc.update({
        "site": site, "title": cfg["title"], "zoom": bw.ZOOM, "width": grid.width, "height": grid.height,
        "bounds": grid.bounds, "pixel_m": round(float(np.sqrt(bw.pixel_ha(grid.transform, grid.height).mean() * 1e4)), 2),
        "note": ("Every image covers bounds (west, south, east, north). Ask for files with ?v=baked_utc. Numbers carry "
                 "the files they come from."),
        "written_with": "Written with SI assistance (Claude Code), reviewed by the team.",
    })
    doc["focus"] = focus_box(site, grid)
    want = [v for v in views if v in SITE_VIEWS[site]]
    if site != "donana" and any(v in want for v in ("swipe", "soil", "timeline")):
        doc["ground"] = bake_ground(grid, out_dir)
    if any(v in want for v in ("swipe", "coherence", "timeline")):
        ds = open_stack(stack_file(site, cfg["stack"]))
        sea = sea_of(site, (ds.sizes["y"], ds.sizes["x"]))
        perm = permanent_water(ds, site)
        view = in_view(ds, grid)
        if "swipe" in want:
            doc["views"]["swipe"] = bake_swipe(site, ds, grid, out_dir, sea, perm, view)
        if "coherence" in want:
            doc["views"]["coherence"] = bake_coherence(site, ds, grid, out_dir, sea, perm, view)
        if "timeline" in want:
            doc["views"]["timeline"] = bake_timeline(site, ds, grid, out_dir, sea, view)
        del ds
    if "soil" in want:
        doc["views"]["soil"] = bake_soil(site, grid, out_dir)
    doc["views"] = {k: doc["views"][k] for k in VIEWS if k in doc["views"]}
    doc["baked_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = sum(p.stat().st_size for p in (out_dir / "views").rglob("*.webp"))
    doc["bytes_total"] = total
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{site}: {total / 1e6:.2f} MB of pictures, views -> {rel(path)}", flush=True)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sites", nargs="*", default=list(SITES), choices=list(SITES))
    ap.add_argument("--views", nargs="*", default=list(VIEWS), choices=list(VIEWS))
    args = ap.parse_args()
    for site in args.sites:  # one stack in memory at a time
        bake_site(site, tuple(args.views))


if __name__ == "__main__":
    sys.exit(main())
