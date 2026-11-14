"""Bake the playfield of the flood game: what each cell of ground did in the storm, from the radar frames.

    python scripts/bake_game.py --site pego_oliva --before 9 --after 10 --s1-after 8

The game (src/components/game/) replays the DANA "Adam" storm. The player sees the ground as it was on the last
NISAR pass before the rain, marks the cells they think will be under water on the next pass, and then the next
pass is shown and every cell is scored. This script does the measuring once, so the page only reads one small
file, public/layers/<site>/game.json:

    cells      one record per cell of the playfield (CELL_PX frame pixels square, about CELL_PX x 15 m):
               land       share of the cell that is land (sea left out)
               before     share of the land under water on the pass before the storm
               new        share of the land under water on the pass after and not on the pass before
               gone       share of the land under water before and dry after
               hidden     of the new water, the share that the Sentinel-1 pass of the same day drew as land
                          (water under reeds and trees that the shorter C-band radar does not see through)
               ems        share of the land inside the Copernicus EMS flood outline
               elev       mean height of the land above the sea, metres (Mapterhorn terrain tiles, MDT02 lidar)
               elev_min   the lowest point of the cell
               new_ha     hectares of new water
               flood      true when `new` reaches FLOOD_SHARE: the cell counts as flooded in the game

The frames are the ones the map plays (scripts/bake_water.py): R 255 where the pass saw the pixel, G the signed
distance to the edge of all water, negative inside. The elevation comes from the terrain tiles of the app
(public/tiles/dem, zoom 12, 512 px: one tile pixel is one frame pixel of the zoom 13 lattice).

Needs numpy, pillow, rasterio and pyproj. Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.features import rasterize
from rasterio.warp import transform_geom

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bake_water import ORIGIN, RES, pixel_ha  # noqa: E402

WEB = Path(__file__).resolve().parents[1]
CELL_PX = 32          # a cell is this many frame pixels square: about 475 m
PAD_CELLS = 6         # the playfield reaches this many cells beyond the flooded ones: about 2.9 km of other ground to choose from
MIN_LAND = 0.3        # a cell with less land than this (sea) is not in the game
FLOOD_SHARE = 0.2     # a cell counts as flooded when this share of its land is new water
DEM_TILE = 512
DEM_ZOOM = 12


def frame(path: Path):
    """A baked frame: seen (bool), any water (bool), open water (bool)."""
    a = np.asarray(Image.open(path).convert("RGB"))
    return a[..., 0] == 255, a[..., 1] < 128, a[..., 2] < 128


def elevation(meta: dict) -> np.ndarray:
    """Height in metres on the frame grid, from the terrarium tiles of the app. NaN where no tile is here."""
    w, h = meta["width"], meta["height"]
    west, south, east, north = meta["bounds"]
    # the frame grid is a window of the zoom 13 lattice (bake_water.web_grid): its first global pixel
    x0 = ORIGIN + 6378137.0 * math.radians(west)
    y1 = ORIGIN - 6378137.0 * math.log(math.tan(math.pi / 4 + math.radians(north) / 2))
    c0 = int(round(x0 / RES))
    r0 = int(round(y1 / RES))
    out = np.full((h, w), np.nan, dtype="float32")
    for ty in range(r0 // DEM_TILE, (r0 + h - 1) // DEM_TILE + 1):
        for tx in range(c0 // DEM_TILE, (c0 + w - 1) // DEM_TILE + 1):
            path = WEB / "public" / "tiles" / "dem" / str(DEM_ZOOM) / str(tx) / f"{ty}.webp"
            if not path.exists():
                continue
            t = np.asarray(Image.open(path).convert("RGB")).astype("float32")
            z = t[..., 0] * 256 + t[..., 1] + t[..., 2] / 256 - 32768
            gy, gx = ty * DEM_TILE - r0, tx * DEM_TILE - c0
            ys, xs = slice(max(gy, 0), min(gy + DEM_TILE, h)), slice(max(gx, 0), min(gx + DEM_TILE, w))
            out[ys, xs] = z[ys.start - gy:ys.stop - gy, xs.start - gx:xs.stop - gx]
    return out


def outline_mask(features: list, meta: dict) -> np.ndarray:
    """Pixels inside a set of lon/lat polygons, on the frame grid."""
    from rasterio.transform import Affine

    west, _, _, north = meta["bounds"]
    x0 = 6378137.0 * math.radians(west)
    y1 = 6378137.0 * math.log(math.tan(math.pi / 4 + math.radians(north) / 2))
    transform = Affine(RES, 0, round((x0 + ORIGIN) / RES) * RES - ORIGIN, 0, -RES, ORIGIN - round((ORIGIN - y1) / RES) * RES)
    shapes = [(transform_geom("EPSG:4326", "EPSG:3857", f["geometry"]), 1) for f in features]
    return rasterize(shapes, out_shape=(meta["height"], meta["width"]), transform=transform, fill=0, dtype="uint8") == 1


def lonlat(meta: dict, col: float, row: float) -> tuple[float, float]:
    """The lon/lat of a frame pixel corner."""
    west, _, _, north = meta["bounds"]
    x = 6378137.0 * math.radians(west) + col * RES
    y = 6378137.0 * math.log(math.tan(math.pi / 4 + math.radians(north) / 2)) - row * RES
    return round(math.degrees(x / 6378137.0), 6), round(math.degrees(2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2), 6)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", default="pego_oliva")
    ap.add_argument("--series", default="nisar_066_D_069")
    ap.add_argument("--before", type=int, default=9, help="frame of the series before the storm")
    ap.add_argument("--after", type=int, default=10, help="frame of the series after the storm")
    ap.add_argument("--s1-after", type=int, default=8, help="frame of the s1 series nearest the pass after")
    args = ap.parse_args()

    root = WEB / "public" / "layers" / args.site
    meta = json.loads((root / "meta.json").read_text())
    series = {s["id"]: s for s in meta["series"]}
    nisar, s1 = series[args.series], series["s1"]
    fb, fa, fs = nisar["frames"][args.before], nisar["frames"][args.after], s1["frames"][args.s1_after]

    seen_b, water_b, _ = frame(root / fb["file"])
    seen_a, water_a, _ = frame(root / fa["file"])
    seen_s, water_s, _ = frame(root / fs["file"])
    sea = np.asarray(Image.open(root / meta["base"]).convert("RGB"))[..., 0] == 255
    land = ~sea & seen_a & seen_b
    new = water_a & ~water_b & land
    gone = water_b & ~water_a & land
    hidden = new & seen_s & ~water_s
    elev = elevation(meta)
    outlines = json.loads((root / "outlines.json").read_text()) if (root / "outlines.json").exists() else {}
    ems = outline_mask(outlines["ems"]["features"], meta) if "ems" in outlines else np.zeros_like(land)
    row_ha = pixel_ha(_affine(meta), meta["height"])

    # every cell of the frame is measured; the playfield is then the flooded cells and a margin around them
    def cell(r, c):
        ys = slice(r * CELL_PX, (r + 1) * CELL_PX)
        xs = slice(c * CELL_PX, (c + 1) * CELL_PX)
        L = land[ys, xs]
        n_land = int(L.sum())
        if n_land < MIN_LAND * CELL_PX * CELL_PX:
            return None
        n_new = int(new[ys, xs].sum())
        z = elev[ys, xs][L]
        z = z[~np.isnan(z)]
        w, n = lonlat(meta, xs.start, ys.start)
        e, s = lonlat(meta, xs.stop, ys.stop)
        share = lambda m: round(float(m[ys, xs][L].sum()) / n_land, 3)  # noqa: E731
        new_share = share(new)
        return {
                "r": r, "c": c, "box": [w, s, e, n],
                "land": round(n_land / (CELL_PX * CELL_PX), 3),
                "before": share(water_b), "new": new_share, "gone": share(gone),
                "hidden": round(float(hidden[ys, xs].sum()) / n_new, 3) if n_new else 0.0,
                "ems": share(ems),
                "elev": round(float(z.mean()), 1) if z.size else None,
                "elev_min": round(float(z.min()), 1) if z.size else None,
                "new_ha": round(float((new[ys, xs] * row_ha[ys, None]).sum()), 1),
                "flood": new_share >= FLOOD_SHARE,
        }

    every = [x for r in range(meta["height"] // CELL_PX) for c in range(meta["width"] // CELL_PX) if (x := cell(r, c))]
    flooded = [x for x in every if x["flood"]]
    r0 = max(0, min(x["r"] for x in flooded) - PAD_CELLS)
    c0 = max(0, min(x["c"] for x in flooded) - PAD_CELLS)
    r1 = min(meta["height"] // CELL_PX, max(x["r"] for x in flooded) + PAD_CELLS + 1)
    c1 = min(meta["width"] // CELL_PX, max(x["c"] for x in flooded) + PAD_CELLS + 1)
    nr, nc = r1 - r0, c1 - c0
    cells = [x for x in every if r0 <= x["r"] < r1 and c0 <= x["c"] < c1]
    for i, x in enumerate(cells):
        x["i"], x["r"], x["c"] = i, x["r"] - r0, x["c"] - c0
    sw, ne = lonlat(meta, c0 * CELL_PX, r1 * CELL_PX), lonlat(meta, c1 * CELL_PX, r0 * CELL_PX)
    out = {
        "site": args.site,
        "made_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"Frames of {args.series} and s1 baked by bake_water.py (NISAR water by the team CV model, OPERA DSWx-S1), "
                  "Copernicus EMS EMSR935 outline, Mapterhorn terrain tiles (MDT02)",
        "cell_px": CELL_PX, "cell_m": round(CELL_PX * meta["pixel_m"]), "flood_share": FLOOD_SHARE,
        "grid": {"rows": nr, "cols": nc, "box": [sw[0], sw[1], ne[0], ne[1]]},
        "before": {"frame": args.before, "time_utc": fb["time_utc"], "water_ha": round(fb["open_ha"] + fb["veg_ha"], 1)},
        "after": {"frame": args.after, "time_utc": fa["time_utc"], "water_ha": round(fa["open_ha"] + fa["veg_ha"], 1)},
        "s1_after": {"frame": args.s1_after, "time_utc": fs["time_utc"], "water_ha": round(fs["open_ha"] + fs["veg_ha"], 1)},
        "totals": {
            "cells": len(cells), "flooded": len(flooded),
            "flooded_outside": len(flooded) - sum(x["flood"] for x in cells),
            "new_ha": round(float((new * row_ha[:, None]).sum()), 1),
            "hidden_ha": round(float((hidden * row_ha[:, None]).sum()), 1),
            "ems_ha": round(float(((ems & land) * row_ha[:, None]).sum()), 1) if ems.any() else None,
            "new_in_ems": round(float((new & ems).sum()) / max(1, int(new.sum())), 3) if ems.any() else None,
        },
        "cells": cells,
    }
    path = root / "game.json"
    path.write_text(json.dumps(out, separators=(",", ":")))
    t = out["totals"]
    print(f"{path}: {nr} x {nc} cells of {out['cell_m']} m, {t['cells']} on land, {t['flooded']} flooded "
          f"({t['new_ha']} ha new water, {t['hidden_ha']} ha of it not in the Sentinel-1 pass)")


def _affine(meta):
    from rasterio.transform import Affine

    west, _, _, north = meta["bounds"]
    x0 = 6378137.0 * math.radians(west)
    y1 = 6378137.0 * math.log(math.tan(math.pi / 4 + math.radians(north) / 2))
    return Affine(RES, 0, round((x0 + ORIGIN) / RES) * RES - ORIGIN, 0, -RES, ORIGIN - round((ORIGIN - y1) / RES) * RES)


if __name__ == "__main__":
    main()
