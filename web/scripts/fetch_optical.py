"""Fetch real Sentinel-2 true colour pictures of a site for chosen days, on the same grid family as the water frames.

    python scripts/fetch_optical.py --site pego_oliva --days 2026-10-08 2026-10-18 2026-10-21 2026-10-28

Searches the Element 84 Earth Search STAC (public, no login) for Sentinel-2 L2A scenes of each day, reads only the
site window of the true colour image (the "visual" asset, a Cloud-Optimized GeoTIFF on AWS) and writes
public/layers/<site>/optical/<day>.webp, read on the Web Mercator zoom 14 lattice (about 7.5 m on the ground, twice
the water grid) and stored at most --max-px pixels a side (2560: about 10 m, the resolution of Sentinel-2 itself,
and what the map pages draw), plus optical.json with each scene id, its time, its cloud cover and the box to place
it on the map. width and height in optical.json are those of the lattice it was read on.

Nothing is retouched: no cloud removal, no colour change. A cloudy day stays cloudy, which is the point.
Contains modified Copernicus Sentinel data, processed by ESA; credit it wherever a picture is shown.

Needs rasterio, numpy, pillow, pyproj and requests (the pipeline environment has them all).
Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

WEB = Path(__file__).resolve().parents[1]
STAC = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
ZOOM = 14
WORLD = 2 * math.pi * 6378137.0
RES = WORLD / (256 * 2**ZOOM)
ORIGIN = WORLD / 2

SITES = {
    "albufera": (-0.45, 39.15, -0.22, 39.45),
    "pego_oliva": (-0.25, 38.78, 0.06, 39.02),
    "espada": (-0.50, 39.78, -0.10, 40.02),
    "lorca": (-1.80, 37.55, -1.45, 37.85),
}


def web_grid(bbox):
    to_m = Transformer.from_crs(4326, 3857, always_xy=True)
    x0, y0 = to_m.transform(bbox[0], bbox[1])
    x1, y1 = to_m.transform(bbox[2], bbox[3])
    c0, c1 = math.floor((x0 + ORIGIN) / RES), math.ceil((x1 + ORIGIN) / RES)
    r0, r1 = math.floor((ORIGIN - y1) / RES), math.ceil((ORIGIN - y0) / RES)
    return Affine(RES, 0, c0 * RES - ORIGIN, 0, -RES, ORIGIN - r0 * RES), c1 - c0, r1 - r0


def scenes(bbox, day):
    body = {"collections": [COLLECTION], "bbox": list(bbox), "datetime": f"{day}T00:00:00Z/{day}T23:59:59Z", "limit": 50}
    r = requests.post(STAC, json=body, timeout=120)
    r.raise_for_status()
    out = []
    for f in r.json()["features"]:
        p = f["properties"]
        out.append({"id": f["id"], "time_utc": p["datetime"][:19] + "Z", "platform": p.get("platform", ""),
                    "cloud_pct": round(float(p.get("eo:cloud_cover", -1)), 1), "tile": p.get("grid:code", ""),
                    "href": f["assets"]["visual"]["href"]})
    return sorted(out, key=lambda s: s["id"])


def read_day(items, transform, width, height):
    """Mosaic the true colour windows of one day onto the grid; the first scene with data wins."""
    out = np.zeros((3, height, width), "uint8")
    used = []
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4"):
        for it in items:
            empty = out.max(axis=0) == 0
            if not empty.any():
                break
            tile = np.zeros((3, height, width), "uint8")
            with rasterio.open(it["href"]) as src:
                for b in range(3):
                    reproject(rasterio.band(src, b + 1), tile[b], src_nodata=0, dst_transform=transform,
                              dst_crs="EPSG:3857", dst_nodata=0, resampling=Resampling.bilinear)
            take = empty & (tile.max(axis=0) > 0)
            if take.any():
                out[:, take] = tile[:, take]
                used.append({**it, "share": round(float(take.mean()), 3)})
    return out, used


def store(picture, max_px):
    """The picture as it is stored: at most max_px a side. The lattice is finer than Sentinel-2 (7.5 m against 10 m),
    so this keeps every detail of the satellite and about a third of the bytes."""
    w, h = picture.size
    k = max_px / max(w, h) if max_px else 1
    return picture if k >= 1 else picture.resize((round(w * k), round(h * k)), Image.Resampling.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True, choices=sorted(SITES))
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=WEB / "public" / "layers")
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--max-px", type=int, default=2560, help="longest side of a stored picture (0 keeps the lattice)")
    args = ap.parse_args()

    bbox = SITES[args.site]
    transform, width, height = web_grid(bbox)
    folder = args.out / args.site / "optical"
    folder.mkdir(parents=True, exist_ok=True)
    index_path = args.out / args.site / "optical.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"scenes": []}
    to_deg = Transformer.from_crs(3857, 4326, always_xy=True)
    west, south = to_deg.transform(transform.c, transform.f - height * RES)
    east, north = to_deg.transform(transform.c + width * RES, transform.f)
    index.update({"site": args.site, "width": width, "height": height, "zoom": ZOOM,
                  "bounds": [round(west, 7), round(south, 7), round(east, 7), round(north, 7)],
                  "source": "Sentinel-2 L2A true colour, Element 84 Earth Search STAC on AWS",
                  "credit": "Contains modified Copernicus Sentinel data 2026"})
    for day in args.days:
        items = scenes(bbox, day)
        if not items:
            print(f"  {day}: no scene")
            continue
        rgb, used = read_day(items, transform, width, height)
        filled = float((rgb.max(axis=0) > 0).mean())
        name = f"{day}.webp"
        store(Image.fromarray(np.moveaxis(rgb, 0, -1)), args.max_px).save(folder / name, "WEBP", quality=args.quality, method=6)
        # the cloud share quoted for the picture is the one of the scene that fills most of it
        main = max(used, key=lambda u: u["share"]) if used else None
        rec = {"day": day, "file": f"optical/{name}", "time_utc": main["time_utc"] if main else None,
               "platform": main["platform"] if main else None, "covered": round(filled, 3),
               "cloud_pct": main["cloud_pct"] if main else None, "main_scene": main["id"] if main else None,
               "scenes": [{"id": u["id"], "tile": u["tile"], "cloud_pct": u["cloud_pct"], "share": u["share"]} for u in used]}
        index["scenes"] = sorted([s for s in index["scenes"] if s["day"] != day] + [rec], key=lambda s: s["day"])
        size = (folder / name).stat().st_size / 1e6
        print(f"  {day}: {[(u['id'], u['cloud_pct'], u['share']) for u in used]} covered {filled:.0%}, {size:.1f} MB", flush=True)
    index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"index -> {index_path}")


if __name__ == "__main__":
    sys.exit(main())
