"""Bake the few facts a story page points at, so its labels sit on the map and no legend is needed.

    python scripts/bake_story.py --data-root ../data
    python scripts/bake_story.py --site pego_oliva --data-root ../data --check out_dir

For each site it writes public/layers/<site>/story.json:

    passes           the two radar passes the story compares (before, after)
    labels           what to point at: a place [longitude, latitude], a title and a value
    official         the official map of the event as ONE calm shape for a soft fill (null when there is none)
    depth            water depths measured on the ground, each as a small hexagon the map can raise into a column
    photos           the clear Sentinel-2 day to put under each of the two passes
    inside_official  how much of what the radar maps lies inside the official map
    landcover        what the radar maps lies on, by ESA WorldCover 2021 class

Everything is measured on the frames bake_water.py wrote (run that first), so a label sits on exactly the water the
page draws and the hectares match meta.json. A label goes to the point deepest inside the largest patch, never to a
centroid, so it cannot fall outside its shape. Hectares use the true ground area of each pixel.

Sites: pego_oliva (the DANA flood, 16 against 28 Oct), espada (the fire, 24 Jul against 16 Oct), albufera (the rice
season, a usual summer pass against 28 Oct).

Needs numpy, scipy, pillow, rasterio, geopandas, shapely and pyproj (the pipeline environment has them all);
matplotlib only for --check.
Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio import features
from scipy import ndimage
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bake_water as bw  # noqa: E402  the grid, the pixel areas and the site boxes are the ones of the frames

WEB = Path(__file__).resolve().parents[1]
METRIC = 25830  # ETRS89 / UTM zone 30N: metres, for buffers and hexagons
EQUAL_AREA = 3035  # ETRS89 LAEA Europe, for the area of a drawn shape
TO_DEG = Transformer.from_crs(3857, 4326, always_xy=True)
TO_MERC = Transformer.from_crs(4326, 3857, always_xy=True)
TO_UTM = Transformer.from_crs(4326, METRIC, always_xy=True)
FROM_UTM = Transformer.from_crs(METRIC, 4326, always_xy=True)
CLEAR_PCT = 10.0  # a picture counts as clear under this much cloud
HEX_ACROSS_M = 110.0
LANDCOVER = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare ground",
             70: "Snow and ice", 80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen"}
# How hard the official map is generalised: close gaps of this many metres, drop parts under this many hectares,
# fill holes under this many hectares, simplify to this many metres. The flood product is many flooded fields with
# dry strips between them (1,892 parts, 1,865 of them under 1 ha): closing gaps of 40 m adds a third to its area.
# So the gaps closed are narrow and the small scattered parts go instead, and the two cancel: the shape keeps the
# area of the product. The first setting whose area stays within 5 % of the product is kept.
CALM = [(8.0, 5.0, 2.0, 15.0), (8.0, 3.0, 0.5, 15.0), (6.5, 1.0, 0.5, 10.0), (4.0, 0.5, 0.25, 8.0), (0.0, 0.25, 0.1, 6.0)]

STORIES = {
    "pego_oliva": {"series": "nisar_066_D_069", "before": "2026-10-16", "after": "2026-10-28"},
    "espada": {"series": "burn_058_A_022", "before": "2026-07-24", "after": "2026-10-16", "event": "2026-07-25T07:09:00Z"},
    "albufera": {"series": "nisar_066_D_069", "before": None, "after": "2026-10-28"},
}


# ---------------------------------------------------------------- the grid of the frames

class Site:
    """One site as the page draws it: the grid of its frames, the pixel areas and the frame list of one series."""

    def __init__(self, name, layers, data_root):
        self.name, self.dir, self.data = name, layers / name, data_root
        self.meta = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        self.transform, self.width, self.height = bw.web_grid(bw.SITES[name]["bbox"])
        if (self.width, self.height) != (self.meta["width"], self.meta["height"]):
            raise SystemExit(f"{name}: the grid of meta.json is not the grid of bake_water.py, bake the layers again")
        self.row_ha = bw.pixel_ha(self.transform, self.height)
        self.series = next(s for s in self.meta["series"] if s["id"] == STORIES[name]["series"])

    def frame(self, day):
        return next(f for f in self.series["frames"] if f["time_utc"].startswith(day))

    def mask(self, file):
        """The pixels the page draws for one baked frame: where the distance field of all water is below zero."""
        return np.asarray(Image.open(self.dir / file).convert("RGB"))[..., 1] < 128

    def ha(self, mask):
        return float((self.row_ha[:, None] * mask).sum())

    def lonlat(self, row, col):
        x = self.transform.c + (col + 0.5) * bw.RES
        y = self.transform.f - (row + 0.5) * bw.RES
        lon, lat = TO_DEG.transform(x, y)
        return [round(lon, 6), round(lat, 6)]

    def pixel(self, lon, lat):
        x, y = TO_MERC.transform(lon, lat)
        return int((self.transform.f - y) // bw.RES), int((x - self.transform.c) // bw.RES)

    def burn_in(self, geoms):
        """Shapes in degrees as a mask on the grid (a pixel counts when its centre is inside)."""
        shapes = gpd.GeoSeries(list(geoms), crs=4326).to_crs(3857)
        return features.rasterize(((g, 1) for g in shapes if not g.is_empty), out_shape=(self.height, self.width),
                                  transform=self.transform, fill=0, dtype="uint8") == 1

    def landcover(self, mask):
        path = self.data / "context" / f"{self.name}_worldcover_2021_20m.tif"
        if not path.exists():
            return []
        cover = bw.onto_grid(path, self.transform, self.width, self.height, nodata=0)
        rows = []
        for code in np.unique(cover[mask]):
            area = self.ha(mask & (cover == code))
            if area >= 1.0:
                rows.append({"name": LANDCOVER.get(int(code), "No class" if code == 0 else f"Class {int(code)}"), "ha": round(area, 1)})
        return sorted(rows, key=lambda r: -r["ha"])


def visual_centre(site, mask):
    """The point deepest inside the largest connected patch of a mask (so a label never falls outside its shape).
    Returns row, col, the hectares of that patch, how deep the point sits in pixels, and the number of patches."""
    labelled, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    if n == 0:
        return None
    areas = ndimage.sum_labels(np.broadcast_to(site.row_ha[:, None], mask.shape), labelled, index=np.arange(1, n + 1))
    k = int(np.argmax(areas)) + 1
    rows, cols = np.where((labelled == k).any(axis=1))[0], np.where((labelled == k).any(axis=0))[0]
    r0, c0 = rows[0], cols[0]
    patch = np.pad(labelled[r0:rows[-1] + 1, c0:cols[-1] + 1] == k, 1)
    depth = ndimage.distance_transform_edt(patch)
    r, c = np.unravel_index(int(np.argmax(depth)), depth.shape)
    return int(r0 + r - 1), int(c0 + c - 1), float(areas[k - 1]), float(depth[r, c]), n


def label(site, ident, title, value, mask):
    row, col, patch_ha, deep, n = visual_centre(site, mask)
    if not mask[row, col]:
        raise SystemExit(f"{site.name}: the label {ident} fell outside its shape")
    at = site.lonlat(row, col)
    print(f"  label {ident:8s} {title!r} = {value!r} at {at}, largest of {n} patches {patch_ha:.1f} ha, {deep * site.meta['pixel_m']:.0f} m inside")
    return {"id": ident, "at": at, "title": title, "value": value}


def hectares(x, sign=False):
    return f"{'+' if sign else ''}{round(x):,} ha"


def check(site, what, got, want, tol=0.5):
    flag = "ok" if abs(got - want) <= tol else "DIFFERS"
    print(f"  check {what}: {got:.1f} against {want:.1f} ha in meta.json: {flag}")
    if flag != "ok":
        raise SystemExit(f"{site.name}: {what} does not match meta.json")


# ---------------------------------------------------------------- shapes

def geometry(geom):
    """A shape in degrees as GeoJSON with 6 decimals."""
    def rounded(c):
        return [round(c[0], 6), round(c[1], 6)] if isinstance(c[0], (int, float)) else [rounded(x) for x in c]
    m = mapping(geom)
    return {"type": m["type"], "coordinates": rounded(m["coordinates"])}


def polygons(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for part in getattr(geom, "geoms", []) for g in polygons(part)]


def drawn_ha(geom_metric):
    return float(gpd.GeoSeries([geom_metric], crs=METRIC).to_crs(EQUAL_AREA).area.iloc[0] / 1e4)


def calm_shape(gdf, close_m, min_part_ha, min_hole_ha, simplify_m):
    """Many polygons as one calm shape: merged, narrow gaps closed, small parts dropped, small holes filled, simplified."""
    merged = unary_union([p for g in gdf.to_crs(METRIC).geometry for p in polygons(make_valid(g))])
    if close_m:
        merged = merged.buffer(close_m, quad_segs=4).buffer(-close_m, quad_segs=4)
    kept = [Polygon(p.exterior, [h for h in p.interiors if Polygon(h).area >= min_hole_ha * 1e4])
            for p in polygons(merged) if p.area >= min_part_ha * 1e4]
    shape = make_valid(unary_union(kept).simplify(simplify_m, preserve_topology=True))
    return MultiPolygon(polygons(shape))


def to_degrees(geom_metric):
    return gpd.GeoSeries([geom_metric], crs=METRIC).to_crs(4326).iloc[0]


def hexagon(lon, lat):
    x, y = TO_UTM.transform(lon, lat)
    r = HEX_ACROSS_M / 2
    ring = [FROM_UTM.transform(x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    ring = [[round(px, 6), round(py, 6)] for px, py in ring]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


# ---------------------------------------------------------------- pictures

def clear_day(site, when, clearest=False, not_before=None):
    """The clear Sentinel-2 day for a pass: the latest clear picture at or before it (or the clearest of them),
    else the clear day nearest in time, else the nearest day of all."""
    scenes = json.loads((site.dir / "optical.json").read_text(encoding="utf-8"))["scenes"]
    stamp = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
    t = stamp(when)
    clear = [s for s in scenes if s["cloud_pct"] < CLEAR_PCT]
    before = [s for s in clear if stamp(s["time_utc"]) <= t and (not_before is None or stamp(s["time_utc"]) >= stamp(not_before))]
    if before:
        pick = min(before, key=lambda s: (s["cloud_pct"], -stamp(s["time_utc"]).timestamp())) if clearest else max(before, key=lambda s: stamp(s["time_utc"]))
    else:
        pick = min(clear or scenes, key=lambda s: abs((stamp(s["time_utc"]) - t).total_seconds()))
    print(f"  photo for the pass of {when[:10]}: {pick['day']} ({pick['cloud_pct']} % cloud)")
    return pick["day"]


# ---------------------------------------------------------------- the three stories

def flood(site):
    cfg = STORIES[site.name]
    fa, fb = site.frame(cfg["before"]), site.frame(cfg["after"])
    a, b = site.mask(fa["file"]), site.mask(fb["file"])
    check(site, "water before", site.ha(a), fa["open_ha"] + fa["veg_ha"])
    check(site, "water after", site.ha(b), fb["open_ha"] + fb["veg_ha"])
    new, gone = b & ~a, a & ~b
    net = site.ha(b) - site.ha(a)
    print(f"  water {site.ha(a):.1f} -> {site.ha(b):.1f} ha: net {net:+.1f} ha, new ground under water {site.ha(new):.1f} ha, gone {site.ha(gone):.1f} ha")

    points = gpd.read_file(site.data / "labels" / "pego_oliva_water_depth_points.geojson")
    depths = [(float(str(r["AlturaAguam"]).replace(",", ".")), str(r["Cuenca"]), r.geometry.x, r.geometry.y) for _, r in points.iterrows()]
    deepest = max(depths)
    print(f"  {len(depths)} measured depths, {min(d[0] for d in depths)} to {deepest[0]} m, deepest in {deepest[1]}")

    ems = gpd.read_file(site.data / "labels" / "pego_oliva_emsr935_flood.geojson")
    product = json.loads((site.dir / "outlines.json").read_text(encoding="utf-8"))["ems"]["features"][0]["properties"]
    official_ha = float(product["drawn_ha"])  # the product as the page has drawn it so far: 1,118 ha
    for close_m, min_part_ha, min_hole_ha, simplify_m in CALM:
        shape = calm_shape(ems, close_m, min_part_ha, min_hole_ha, simplify_m)
        area = drawn_ha(shape)
        off = area / official_ha - 1
        print(f"  official shape: close {close_m:.0f} m, drop parts under {min_part_ha} ha, fill holes under {min_hole_ha} ha, "
              f"simplify {simplify_m:.0f} m -> {len(polygons(shape))} parts, "
              f"{area:.1f} ha against {official_ha} ha ({off:+.1%})")
        if abs(off) <= 0.05:
            break
    inside = site.burn_in(ems.geometry)
    share = site.ha(new & inside) / site.ha(new)
    print(f"  new water inside the official polygons: {site.ha(new & inside):.1f} of {site.ha(new):.1f} ha ({share:.1%})")

    labels = [
        label(site, "new", "New water", hectares(net, sign=True), new),
        label(site, "normal", "Normal water", hectares(site.ha(a)), a),
        {"id": "deepest", "at": [round(deepest[2], 6), round(deepest[3], 6)], "title": "Measured depth", "value": f"{deepest[0]:.2f} m"},
    ]
    print(f"  label deepest  'Measured depth' = '{deepest[0]:.2f} m' at {labels[2]['at']} ({deepest[1]})")
    return {
        "source": f"Frames of {site.series['id']} baked by bake_water.py (CV water), Copernicus EMS EMSR935 flood polygons, "
                  "depths measured by the Generalitat Valenciana, ESA WorldCover 2021",
        "passes": {"before": fa["time_utc"], "after": fb["time_utc"]},
        "labels": labels,
        "official": {"type": "Feature", "geometry": geometry(to_degrees(shape)),
                     "properties": {"name": "EU flood map", "detail": "Copernicus EMS, 20 to 21 Oct", "area_ha": official_ha, "drawn_ha": round(area, 1)}},
        "depth": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": hexagon(x, y), "properties": {"m": round(m, 2), "basin": basin}} for m, basin, x, y in depths]},
        "photos": {"before": clear_day(site, fa["time_utc"]), "after": clear_day(site, fb["time_utc"])},
        "inside_official": {"new_ha": round(site.ha(new), 1), "inside_ha": round(site.ha(new & inside), 1), "share": round(share, 2)},
        "landcover": site.landcover(new),
    }, {"before": a, "after": b, "official": to_degrees(shape)}


def fire(site):
    cfg = STORIES[site.name]
    fa, fb = site.frame(cfg["before"]), site.frame(cfg["after"])
    a, b = site.mask(fa["file"]), site.mask(fb["file"])
    check(site, "burn before", site.ha(a), fa["open_ha"])
    check(site, "burn after", site.ha(b), fb["open_ha"])

    effis = gpd.read_file(site.data / "labels" / "espada_effis_burnt_area.geojson")
    official_ha = float(effis.iloc[0]["effis_area_ha"])
    whole = unary_union([p for g in effis.to_crs(METRIC).geometry for p in polygons(make_valid(g))])
    outline = MultiPolygon(polygons(make_valid(whole.simplify(15.0, preserve_topology=True))))
    area = drawn_ha(outline)
    print(f"  official shape: EFFIS outline simplified to 15 m -> {len(polygons(outline))} part, {area:.1f} ha against {official_ha} ha ({area / official_ha - 1:+.1%})")
    inside = site.burn_in(effis.geometry)
    share = site.ha(b & inside) / site.ha(b)
    print(f"  burn inside the EFFIS outline: {site.ha(b & inside):.1f} of {site.ha(b):.1f} ha ({share:.1%})")

    # the label of the official map sits on its outline, at the vertex farthest from any burn the radar confirms,
    # so the two labels never crowd each other; the northernmost vertex is taken when it is clear enough
    away = ndimage.distance_transform_edt(~b)
    ring = list(to_degrees(max(polygons(outline), key=lambda p: p.area)).exterior.coords)
    reach = []
    for lon, lat in ring:
        r, c = site.pixel(lon, lat)
        reach.append(away[r, c] if 0 <= r < site.height and 0 <= c < site.width else 0.0)
    north = max(range(len(ring)), key=lambda i: ring[i][1])
    pick = north if reach[north] * site.meta["pixel_m"] >= 150 else max(range(len(ring)), key=lambda i: reach[i])
    at = [round(ring[pick][0], 6), round(ring[pick][1], 6)]
    print(f"  label official 'EU burnt area map' = '{hectares(official_ha)}' at {at} on the outline "
          f"({'northernmost vertex' if pick == north else 'vertex farthest from the burn'}, {reach[pick] * site.meta['pixel_m']:.0f} m from the nearest burn)")

    return {
        "source": f"Frames of {site.series['id']} baked by bake_water.py (CV burn, the echo down on two passes in a row), "
                  "EFFIS burnt area 570518, ESA WorldCover 2021",
        "passes": {"before": fa["time_utc"], "after": fb["time_utc"]},
        "labels": [
            label(site, "burn", "Burn the radar confirms", hectares(site.ha(b)), b),
            {"id": "official", "at": at, "title": "EU burnt area map", "value": hectares(official_ha)},
        ],
        "official": {"type": "Feature", "geometry": geometry(to_degrees(outline)),
                     "properties": {"name": "EU burnt area map", "detail": "EFFIS, as of 26 Jul", "area_ha": official_ha, "drawn_ha": round(area, 1)}},
        "depth": {"type": "FeatureCollection", "features": []},
        "photos": {"before": clear_day(site, fa["time_utc"]), "after": clear_day(site, fb["time_utc"], clearest=True, not_before=cfg["event"])},
        "inside_official": {"new_ha": round(site.ha(b), 1), "inside_ha": round(site.ha(b & inside), 1), "share": round(share, 2)},
        "landcover": site.landcover(b),
    }, {"before": a, "after": b, "official": to_degrees(outline)}


def season(site):
    cfg = STORIES[site.name]
    frames = site.series["frames"]
    # the usual water: the pass with the median of all passes, as the page counts it
    usual = sorted(frames, key=lambda f: f["open_ha"] + f["veg_ha"])[len(frames) // 2]
    fa, fb = usual, site.frame(cfg["after"])
    print(f"  usual pass: {fa['time_utc'][:10]} with {fa['open_ha'] + fa['veg_ha']:.1f} ha (the median of {len(frames)} passes)")
    a, b = site.mask(fa["file"]), site.mask(fb["file"])
    always = site.mask(site.series["always"]["file"])
    check(site, "water before", site.ha(a), fa["open_ha"] + fa["veg_ha"])
    check(site, "water after", site.ha(b), fb["open_ha"] + fb["veg_ha"])
    check(site, "always water", site.ha(always), site.series["always"]["water_ha"])
    seasonal = b & ~always
    print(f"  water on {fb['time_utc'][:10]}: {site.ha(b):.1f} ha, always {site.ha(always):.1f} ha, of the season {site.ha(seasonal):.1f} ha")
    return {
        "source": f"Frames of {site.series['id']} baked by bake_water.py (CV water), ESA WorldCover 2021",
        "passes": {"before": fa["time_utc"], "after": fb["time_utc"]},
        "labels": [
            label(site, "always", "Lagoon, always water", hectares(site.ha(always)), always),
            label(site, "season", "Rice fields, flooded on purpose", hectares(site.ha(b) - site.ha(always), sign=True), seasonal),
        ],
        "official": None,
        "depth": {"type": "FeatureCollection", "features": []},
        "photos": {"before": clear_day(site, fa["time_utc"]), "after": clear_day(site, fb["time_utc"])},
        "inside_official": None,
        "landcover": site.landcover(seasonal),
    }, {"before": always, "after": b, "official": None}


KINDS = {"pego_oliva": flood, "espada": fire, "albufera": season}


def picture(site, doc, shapes, folder):
    """One picture to look at: the shapes on the grid and where the labels landed."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    west, south, east, north = site.meta["bounds"]
    rgb = np.full((site.height, site.width, 3), (24, 30, 34), "uint8")
    rgb[shapes["after"]] = (42, 143, 255)
    rgb[shapes["before"]] = (200, 222, 240)
    fig, ax = plt.subplots(figsize=(13, 13 * site.height / site.width))
    ax.imshow(rgb, extent=(west, east, south, north), aspect="auto", interpolation="nearest")
    if shapes["official"] is not None:
        gpd.GeoSeries([shapes["official"]], crs=4326).boundary.plot(ax=ax, color="#ff7ac8", linewidth=1.0)
    for f in doc["depth"]["features"]:
        ring = f["geometry"]["coordinates"][0]
        ax.plot([p[0] for p in ring], [p[1] for p in ring], color="#ffb347", linewidth=0.8)
    for lab in doc["labels"]:
        ax.plot(*lab["at"], "o", color="#ffe14d", markersize=7, markeredgecolor="black")
        ax.annotate(f"{lab['title']}: {lab['value']}", lab["at"], xytext=(8, 8), textcoords="offset points", color="white",
                    fontsize=10, bbox={"facecolor": "black", "alpha": 0.6, "pad": 2, "edgecolor": "none"})
    # zoom on what the story is about: the after shape and the labels, with a margin
    rows, cols = np.where(shapes["after"].any(axis=1))[0], np.where(shapes["after"].any(axis=0))[0]
    if shapes["official"] is not None:
        x0, y0, x1, y1 = shapes["official"].bounds
    else:
        (x0, y1), (x1, y0) = site.lonlat(rows[0], cols[0]), site.lonlat(rows[-1], cols[-1])
    xs, ys = [x0, x1] + [lab["at"][0] for lab in doc["labels"]], [y0, y1] + [lab["at"][1] for lab in doc["labels"]]
    pad = 0.12 * max(max(xs) - min(xs), max(ys) - min(ys))
    ax.set_xlim(max(west, min(xs) - pad), min(east, max(xs) + pad))
    ax.set_ylim(max(south, min(ys) - pad), min(north, max(ys) + pad))
    ax.set_aspect(1 / math.cos(math.radians((south + north) / 2)))
    ax.set_title(f"{site.name}: pale = before or always, blue = after, pink = official map, orange = measured depths")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{site.name}.png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  check picture -> {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", choices=sorted(STORIES), help="one site (default: all three)")
    ap.add_argument("--data-root", type=Path, default=WEB.parent / "data", help="the data folder of the repo")
    ap.add_argument("--layers", type=Path, default=WEB / "public" / "layers", help="where bake_water.py wrote the frames")
    ap.add_argument("--check", type=Path, help="also draw one picture per site into this folder")
    args = ap.parse_args()
    for name in [args.site] if args.site else list(STORIES):
        print(f"{name}:")
        site = Site(name, args.layers, args.data_root)
        body, shapes = KINDS[name](site)
        doc = {"site": name, "made_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **body}
        for lab in doc["labels"]:
            west, south, east, north = site.meta["bounds"]
            if not (west <= lab["at"][0] <= east and south <= lab["at"][1] <= north):
                raise SystemExit(f"{name}: the label {lab['id']} is outside the site")
        out = site.dir / "story.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        shape_kb = len(json.dumps(doc["official"], separators=(",", ":"))) / 1e3 if doc["official"] else 0
        print(f"  land cover: " + ", ".join(f"{r['name']} {r['ha']:.0f} ha" for r in doc["landcover"]))
        print(f"  story -> {out} ({out.stat().st_size / 1e3:.1f} kB, the official shape {shape_kb:.1f} kB, {len(doc['depth']['features'])} depths)")
        if args.check:
            picture(site, doc, shapes, args.check)


if __name__ == "__main__":
    sys.exit(main())
