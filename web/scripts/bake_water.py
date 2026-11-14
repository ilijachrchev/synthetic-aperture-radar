"""Bake dated water maps into the frames the map animation plays.

    python scripts/bake_water.py --site pego_oliva --start 2026-10-16 --end 2026-11-10 --data-root ../data
    python scripts/bake_water.py --site albufera --start 2026-06-18 --end 2026-10-28 --clock 18:53 --days 2026-06-18 ...
    python scripts/bake_water.py --site espada --layer burn --no-s1 --start 2026-06-18 --end 2026-10-28 --data-root ../data

For one site it gathers every radar water map in a date range and writes, under public/layers/<site>/:

    <series>/<n>.webp  one RGB frame per pass, lossless, on one Web Mercator grid (zoom 13 lattice, about 15 m on the ground)
                       R  255 where this pass saw the pixel, 0 where it did not
                       G  signed distance to the edge of all water (open water plus flooded vegetation)
                       B  signed distance to the edge of open water
    <series>/always.webp  the same fields for the water that every pass of the series has
    base.png           R  255 on the sea (left to the base map)
    meta.json          the grid, the time, source files and hectares of every frame, and the area between passes

Series:
    s1     OPERA DSWx-S1 (Sentinel-1, C band), layer B01_WTR, searched in NASA CMR and downloaded with the
           Earthdata login in ~/.netrc. Classes: 1 open water, 3 inundated vegetation, 250 masked by the terrain
           model (drawn as land), 251 layover or shadow and 255 fill (drawn as not seen).
    nisar  the CV model water layers (data/cv/<site>_<stack>/<date>_water.tif, listed in data/manifest.json):
           0 not water, 1 open water, 2 flooded vegetation, 255 no data or sea.

The distance fields are what lets the shoreline move between two passes instead of fading: the app mixes the
fields of the passes before and after the playhead and draws water where the mix is below zero. At a pass the
picture is the map of that pass. Between passes it is an interpolation, and the app says so.

Between two passes the app does not let a distance outside the water count for more than REACH_PX pixels. So new
water far from any old water does not wait until the last moment to appear: it starts in its deepest part about
halfway through the gap and grows out to its edge, and water that goes shrinks towards its middle the same way.

Distances are in grid pixels, negative inside water, packed into one byte: steps of 1/8 pixel up to 4 pixels from
an edge, then a square-root ramp out to 300 pixels (see ENC_* below; the shader in src/lib/water-layer.ts decodes
it the same way).

Needs rasterio, numpy, scipy, pillow, pyproj, requests and earthaccess (the pipeline environment has them all).
Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject
from scipy.ndimage import distance_transform_edt

WEB = Path(__file__).resolve().parents[1]
CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
DSWX = "OPERA_L3_DSWX-S1_V1"
ZOOM = 13
WORLD = 2 * math.pi * 6378137.0
RES = WORLD / (256 * 2**ZOOM)  # metres per pixel in Web Mercator at this zoom
ORIGIN = WORLD / 2
ENC_LINEAR_PX = 4.0   # 1/8 pixel steps out to here
ENC_RANGE_PX = 300.0  # the ramp ends here
SAMPLES = 17          # area between two passes is measured at this many steps
REACH_PX = 12.0       # between passes, ground farther than this from water counts as this far (see below)

# west, south, east, north in degrees: the pipeline site boxes (pipeline/config.py)
SITES = {
    "albufera": {"title": "Albufera lagoon and rice fields", "bbox": (-0.45, 39.15, -0.22, 39.45)},
    "pego_oliva": {"title": "Pego-Oliva marsh", "bbox": (-0.25, 38.78, 0.06, 39.02)},
    "espada": {"title": "Serra d'Espada burn scar", "bbox": (-0.50, 39.78, -0.10, 40.02)},
}
S1_UNSEEN = (251, 255)


def web_grid(bbox):
    """The zoom 13 pixel lattice that covers a box: affine transform, width, height."""
    to_m = Transformer.from_crs(4326, 3857, always_xy=True)
    x0, y0 = to_m.transform(bbox[0], bbox[1])
    x1, y1 = to_m.transform(bbox[2], bbox[3])
    c0 = math.floor((x0 + ORIGIN) / RES)
    c1 = math.ceil((x1 + ORIGIN) / RES)
    r0 = math.floor((ORIGIN - y1) / RES)
    r1 = math.ceil((ORIGIN - y0) / RES)
    transform = Affine(RES, 0, c0 * RES - ORIGIN, 0, -RES, ORIGIN - r0 * RES)
    return transform, c1 - c0, r1 - r0


def pixel_ha(transform, height):
    """True ground area of one pixel in each row, in hectares (Mercator stretches with latitude)."""
    to_deg = Transformer.from_crs(3857, 4326, always_xy=True)
    ys = transform.f + (np.arange(height) + 0.5) * transform.e
    _, lat = to_deg.transform(np.zeros(height), ys)
    return ((RES * np.cos(np.radians(lat))) ** 2 / 1e4).astype("float64")


def onto_grid(path, transform, width, height, nodata=255):
    """Band 1 of a raster on the web grid, nearest neighbour, nodata where the file has none."""
    out = np.full((height, width), nodata, "uint8")
    with rasterio.open(path) as src:
        reproject(rasterio.band(src, 1), out, src_nodata=src.nodata if src.nodata is not None else nodata,
                  dst_transform=transform, dst_crs="EPSG:3857", dst_nodata=nodata, resampling=Resampling.nearest)
    return out


def signed_distance(mask):
    """Distance in pixels to the edge of a mask, negative inside. The edge runs between pixel centres."""
    if not mask.any():
        return np.full(mask.shape, ENC_RANGE_PX, "float32")
    if mask.all():
        return np.full(mask.shape, -ENC_RANGE_PX, "float32")
    outside = distance_transform_edt(~mask) - 0.5
    inside = distance_transform_edt(mask) - 0.5
    return np.where(mask, -inside, outside).astype("float32")


def encode(s):
    a = np.abs(s)
    f = np.where(a <= ENC_LINEAR_PX, a * (32 / ENC_LINEAR_PX),
                 32 + 95 * np.sqrt(np.clip((a - ENC_LINEAR_PX) / (ENC_RANGE_PX - ENC_LINEAR_PX), 0, 1)))
    return np.clip(np.rint(128 + np.sign(s) * f), 1, 255).astype("uint8")


def decode(code):
    c = code.astype("float32") - 128
    a = np.abs(c)
    s = np.where(a <= 32, a * (ENC_LINEAR_PX / 32), ENC_LINEAR_PX + (ENC_RANGE_PX - ENC_LINEAR_PX) * ((a - 32) / 95) ** 2)
    return np.sign(c) * s


# ---------------------------------------------------------------- Sentinel-1 water maps (OPERA DSWx-S1)

def s1_passes(bbox, start, end):
    """Every DSWx-S1 pass over the box: start time, platform and the newest WTR file per tile."""
    params = {"short_name": DSWX, "bounding_box": ",".join(str(v) for v in bbox),
              "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z", "page_size": 2000}
    r = requests.get(CMR, params=params, timeout=120)
    r.raise_for_status()
    passes = {}
    for item in r.json()["items"]:
        umm = item["umm"]
        ur = umm["GranuleUR"]  # OPERA_L3_DSWx-S1_<tile>_<acquired>Z_<produced>Z_<platform>_30_v1.0
        parts = ur.split("_")
        tile, produced, platform = parts[3], parts[5], parts[6]
        begin = umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
        url = next((u["URL"] for u in umm.get("RelatedUrls", [])
                    if u.get("URL", "").startswith("https") and u["URL"].endswith("_B01_WTR.tif")), None)
        if not url:
            continue
        tiles = passes.setdefault((begin[:13], platform), {})
        if tile not in tiles or produced > tiles[tile]["produced"]:
            tiles[tile] = {"granule": ur, "begin": begin, "produced": produced, "url": url}
    out = []
    for (_, platform), tiles in sorted(passes.items()):
        begin = min(t["begin"] for t in tiles.values())
        out.append({"time_utc": begin[:19] + "Z", "platform": platform, "tiles": [tiles[k] for k in sorted(tiles)]})
    return out


def s1_download(passes, cache):
    todo = []
    for p in passes:
        folder = cache / p["time_utc"][:13].replace(":", "").replace("-", "")
        for t in p["tiles"]:
            t["path"] = folder / t["url"].rsplit("/", 1)[-1]
            if not t["path"].exists():
                todo.append((t["url"], folder))
    if not todo:
        return
    import earthaccess

    earthaccess.login(strategy="netrc")
    for folder in sorted({f for _, f in todo}):
        folder.mkdir(parents=True, exist_ok=True)
        earthaccess.download([u for u, f in todo if f == folder], local_path=str(folder))


def s1_classes(p, transform, width, height):
    """One pass on the grid as 0 land, 1 open water, 2 flooded vegetation, 255 not seen."""
    wtr = np.full((height, width), 255, "uint8")
    for t in p["tiles"]:
        tile = onto_grid(t["path"], transform, width, height)
        take = (wtr == 255) & (tile != 255)
        wtr[take] = tile[take]
    cls = np.zeros((height, width), "uint8")
    cls[wtr == 1] = 1
    cls[wtr == 3] = 2
    cls[np.isin(wtr, S1_UNSEEN)] = 255
    return cls


# ---------------------------------------------------------------- NISAR water layers from the CV model

def nisar_frames(data_root, site, transform, width, height, stacks=None, layer="water"):
    """The CV layers of one kind for a site from data/manifest.json, grouped by stack, each on the grid.
    Class 1 is the thing mapped (water, or burned ground), 2 flooded vegetation, 255 no data."""
    manifest = data_root / "manifest.json"
    if not manifest.exists():
        return {}
    by_stack = {}
    for e in json.loads(manifest.read_text(encoding="utf-8")):
        if e.get("model") != "cv" or e.get("site") != site or e.get("layer") != layer:
            continue
        if stacks and e.get("stack") not in stacks:
            continue
        path = data_root.parent / e["file"]
        if not path.exists():
            continue
        cls = onto_grid(path, transform, width, height)
        src = e.get("source", {})
        stamp = re.search(r"_(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})_", src.get("granule_ur", ""))
        when = "{}-{}-{}T{}:{}:{}Z".format(*stamp.groups()) if stamp else f"{e['date']}T12:00:00Z"
        by_stack.setdefault(e["stack"], []).append({
            "time_utc": when, "date": e["date"], "cls": cls, "granules": [src.get("granule_ur", "")], "platform": "NISAR",
            "crid": src.get("crid"), "model_file": e.get("model_file"), "threshold": e.get("threshold"),
        })
    return {k: sorted(v, key=lambda f: f["time_utc"]) for k, v in by_stack.items()}


# ---------------------------------------------------------------- frames

def fill_unseen(stack_cls):
    """Where a pass did not see a pixel, keep the last state that was seen (else the next), so the
    shoreline never moves just because a pass missed the pixel. Returns filled classes and the seen masks."""
    seen = [c != 255 for c in stack_cls]
    filled = [c.copy() for c in stack_cls]
    last = np.zeros(stack_cls[0].shape, "uint8")
    have = np.zeros(stack_cls[0].shape, bool)
    for i, c in enumerate(filled):
        c[~seen[i] & have] = last[~seen[i] & have]
        last[seen[i]] = stack_cls[i][seen[i]]
        have |= seen[i]
    nxt = np.zeros(stack_cls[0].shape, "uint8")
    have = np.zeros(stack_cls[0].shape, bool)
    for i in range(len(filled) - 1, -1, -1):
        c = filled[i]
        gap = c == 255
        c[gap & have] = nxt[gap & have]
        c[c == 255] = 0
        nxt[seen[i]] = stack_cls[i][seen[i]]
        have |= seen[i]
    return filled, seen


def bake_series(name, frames, sea, row_ha, out_dir):
    """Write one PNG per frame and return the frame records (with hectares) and the area between passes."""
    folder = out_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    for old in list(folder.glob("*.png")) + list(folder.glob("*.webp")):
        old.unlink()
    filled, seen = fill_unseen([f["cls"] for f in frames])
    land = ~sea
    area = row_ha[:, None]
    records, fields = [], []
    for i, f in enumerate(frames):
        cls = filled[i]
        water = (cls > 0) & land
        open_w = (cls == 1) & land
        g = encode(signed_distance(water))
        b = encode(signed_distance(open_w))
        r = np.where(seen[i], 255, 0).astype("uint8")
        Image.fromarray(np.dstack([r, g, b])).save(folder / f"{i:02d}.webp", "WEBP", lossless=True, quality=100, method=4)
        obs = seen[i] & land
        rec = {k: v for k, v in f.items() if k != "cls"}
        rec.update({
            "file": f"{name}/{i:02d}.webp",
            "open_ha": round(float((area * (open_w & obs)).sum()), 1),
            "veg_ha": round(float((area * ((cls == 2) & obs)).sum()), 1),
            "seen": round(float(obs.sum() / max(1, land.sum())), 3),
        })
        records.append(rec)
        fields.append((decode(g), decode(b)))
        print(f"  {name} {i:02d} {f.get('time_utc', f.get('date'))} {f.get('platform', '')}: open {rec['open_ha']} ha, "
              f"flooded vegetation {rec['veg_ha']} ha, seen {rec['seen']:.0%}", flush=True)
    # Water that every pass of the series has: the page can measure "new" water against it (a lagoon, a river)
    always = np.logical_and.reduce([c > 0 for c in filled]) & land
    always_open = np.logical_and.reduce([c == 1 for c in filled]) & land
    Image.fromarray(np.dstack([np.full(always.shape, 255, "uint8"), encode(signed_distance(always)), encode(signed_distance(always_open))])).save(
        folder / "always.webp", "WEBP", lossless=True, quality=100, method=4)
    always_rec = {"file": f"{name}/always.webp", "water_ha": round(float((area * always).sum()), 1)}

    # Hectares the app shows between two passes, so the counter matches the picture. The app runs two clocks in a
    # gap: one for pixels that get wetter (gain) and one for pixels that dry (loss). Three paths cover every case:
    #   both  the two clocks run together (an ordinary gap)
    #   gain  only the wetting has happened so far (a storm: the water rises first)
    #   loss  the wetting is complete and the drying runs (after the storm)
    def hectares(ga, gb, ba, bb, gain, loss, land_w, area_w):
        any_f = np.where(gb < ga, (1 - gain) * ga + gain * gb, (1 - loss) * ga + loss * gb)
        open_f = np.where(bb < ba, (1 - gain) * ba + gain * bb, (1 - loss) * ba + loss * bb)
        any_w = (any_f < 0) & land_w
        open_w = (open_f < 0) & any_w
        return np.array([(area_w * open_w).sum(), (area_w * (any_w & ~open_w)).sum()])

    between = []
    steps = [k / (SAMPLES - 1) for k in range(SAMPLES)]
    area_full = np.broadcast_to(area, land.shape)
    for i in range(len(fields) - 1):
        (ga, ba), (gb, bb) = [[np.minimum(f, REACH_PX) for f in pair] for pair in (fields[i], fields[i + 1])]
        # a pixel whose two fields share a sign never flips, so only the window that holds a flip is mixed
        flips = ((ga < 0) != (gb < 0)) | ((ba < 0) != (bb < 0))
        fixed = hectares(ga, ga, ba, ba, 0.0, 0.0, land & ~flips, area_full)
        if flips.any():
            rows, cols = np.where(flips.any(axis=1))[0], np.where(flips.any(axis=0))[0]
            win = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
            args = (ga[win], gb[win], ba[win], bb[win])
            mask, weights = (land & flips)[win], area_full[win]
            path = lambda pairs: [[round(float(v), 1) for v in fixed + hectares(*args, g, l, mask, weights)] for g, l in pairs]
        else:
            path = lambda pairs: [[round(float(v), 1) for v in fixed] for _ in pairs]
        between.append({
            "both": path([(t, t) for t in steps]),
            "gain": path([(t, 0.0) for t in steps]),
            "loss": path([(1.0, t) for t in steps]),
        })
        print(f"  {name} gap {i:02d}: open water {between[-1]['both'][0][0]} -> {between[-1]['gain'][-1][0]} (all gains) "
              f"-> {between[-1]['both'][-1][0]} ha", flush=True)
    return records, between, always_rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True, choices=sorted(SITES))
    ap.add_argument("--start", required=True, help="first day of Sentinel-1 passes, YYYY-MM-DD")
    ap.add_argument("--end", required=True)
    ap.add_argument("--data-root", type=Path, default=WEB.parent / "data", help="the data folder of the repo")
    ap.add_argument("--cache", type=Path, default=WEB / ".cache" / "dswx", help="downloaded Sentinel-1 water maps")
    ap.add_argument("--out", type=Path, default=WEB / "public" / "layers")
    ap.add_argument("--no-s1", action="store_true")
    ap.add_argument("--stacks", nargs="*", help="NISAR stacks to bake, for example 066_D_069 (default: all in the manifest)")
    ap.add_argument("--layer", default="water", choices=["water", "burn"], help="which CV layer of the manifest to bake")
    ap.add_argument("--days", nargs="*", help="keep only the Sentinel-1 passes of these days (YYYY-MM-DD)")
    ap.add_argument("--clock", help="with --days: on each day keep the one pass nearest this UTC time (HH:MM)")
    args = ap.parse_args()

    site = SITES[args.site]
    transform, width, height = web_grid(site["bbox"])
    row_ha = pixel_ha(transform, height)
    out_dir = args.out / args.site
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{args.site}: grid {width} x {height} px at zoom {ZOOM}, {row_ha.mean() * 1e4:.1f} m2 per pixel", flush=True)

    sea_path = args.data_root / "context" / f"{args.site}_sea_20m.tif"
    if sea_path.exists():
        sea = onto_grid(sea_path, transform, width, height, nodata=0) == 1
    else:
        sea = np.zeros((height, width), bool)
    Image.fromarray(np.dstack([np.where(sea, 255, 0).astype("uint8")] * 3)).save(out_dir / "base.png", optimize=True)

    series = []
    if not args.no_s1:
        passes = s1_passes(site["bbox"], args.start, args.end)
        if args.days:
            passes = [p for p in passes if p["time_utc"][:10] in set(args.days)]
            if args.clock:
                want = int(args.clock[:2]) * 60 + int(args.clock[3:5])
                off = lambda p: abs(int(p["time_utc"][11:13]) * 60 + int(p["time_utc"][14:16]) - want)
                best = {}
                for p in passes:
                    day = p["time_utc"][:10]
                    if day not in best or off(p) < off(best[day]):
                        best[day] = p
                passes = [best[d] for d in sorted(best)]
        s1_download(passes, args.cache / args.site)
        frames = [{"time_utc": p["time_utc"], "platform": p["platform"], "granules": [t["granule"] for t in p["tiles"]],
                   "cls": s1_classes(p, transform, width, height)} for p in passes]
        records, between, always = bake_series("s1", frames, sea, row_ha, out_dir)
        series.append({"id": "s1", "sensor": "Sentinel-1", "band": "C band", "classes": ["open water", "flooded vegetation"],
                       "product": "OPERA DSWx-S1 B01_WTR (JPL, via PO.DAAC)", "frames": records, "between": between, "always": always})
    for stack, frames in nisar_frames(args.data_root, args.site, transform, width, height, args.stacks, args.layer).items():
        name = f"nisar_{stack}" if args.layer == "water" else f"{args.layer}_{stack}"
        records, between, always = bake_series(name, frames, sea, row_ha, out_dir)
        two = any(r["veg_ha"] > 0 for r in records)
        if args.layer == "burn":
            classes, product = ["burned"], "NISAR GCOV burn: the HV echo at least 1.5 dB below the last pass before the fire, on two passes in a row"
        else:
            classes, product = (["open water", "flooded vegetation"] if two else ["water"]), "NISAR GCOV water, the team CV model"
        series.append({"id": name, "sensor": "NISAR", "band": "L band", "stack": stack, "classes": classes,
                       "product": product, "frames": records, "between": between, "always": always})

    x0, y1 = transform.c, transform.f
    x1, y0 = x0 + width * RES, y1 - height * RES
    to_deg = Transformer.from_crs(3857, 4326, always_xy=True)
    west, south = to_deg.transform(x0, y0)
    east, north = to_deg.transform(x1, y1)
    meta = {
        "site": args.site, "title": site["title"], "width": width, "height": height, "zoom": ZOOM,
        "bounds": [round(west, 7), round(south, 7), round(east, 7), round(north, 7)],
        "pixel_m": round(float(np.sqrt(row_ha.mean() * 1e4)), 2),
        "encoding": {"linear_px": ENC_LINEAR_PX, "range_px": ENC_RANGE_PX, "reach_px": REACH_PX, "samples": SAMPLES},
        "base": "base.png", "series": series,
        "baked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"meta -> {out_dir / 'meta.json'}")


if __name__ == "__main__":
    sys.exit(main())
