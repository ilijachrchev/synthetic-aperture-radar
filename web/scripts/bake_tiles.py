"""Bake the map tiles of the Valencia stories into the app, so the story pages need no remote tile server.

    python -I scripts/bake_tiles.py           # download what is missing, then write the index
    python -I scripts/bake_tiles.py --plan    # only count the tiles of the plan, download nothing
    python -I scripts/bake_tiles.py --check urls.txt   # which of these tile addresses the plan leaves out

The three story pages (/flood, /rice, /fire) draw four tiled maps under our own layers: the cloudless Sentinel-2
picture of EOX around the place, the relief of Mapterhorn under it, the Blue Marble of NASA for the Earth from far
out, and the names of EOX for the way in. This copies the tiles the stories show into web/public/tiles/ and writes
web/src/data/tiles.json, the boxes of tiles that are here, zoom by zoom. The page asks for a tile here first, and
only a tile outside the boxes goes to its own server (src/lib/tiles.ts).

The boxes follow the cameras of the stories (src/content/stories.ts): a tilted camera sees far, so the box of a
zoom grows as the zoom falls; from zoom 4 down the whole Earth is here, for the globe at the start of the film.
The tiles do not change with the radar layers: there is no need to run this again after a re-bake.

Licences: EOX cloudless 2017 is CC BY 4.0 (EOX IT Services GmbH, modified Copernicus Sentinel data 2017); the EOX
overlay holds OpenStreetMap data (ODbL); the Blue Marble is NASA Earth Observatory; Mapterhorn serves MDT02 of CNIG
(CC BY 4.0) and Copernicus GLO-30. The credits stay on the pages.
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

WEB = Path(__file__).resolve().parents[1]
OUT = WEB / "public" / "tiles"
INDEX = WEB / "src" / "data" / "tiles.json"

# remote: the address of a tile at its own server. These must match src/lib/tiles.ts.
SOURCES = {
    "base": {"remote": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2017_3857/default/g/{z}/{y}/{x}.jpg", "ext": "jpg"},
    "names": {"remote": "https://tiles.maps.eox.at/wmts/1.0.0/overlay_bright_3857/default/g/{z}/{y}/{x}.png", "ext": "png"},
    "far": {"remote": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg", "ext": "jpg"},
    "dem": {"remote": "https://tiles.mapterhorn.com/{z}/{x}/{y}.webp", "ext": "webp"},
}

# The plan: per source, per zoom, boxes of tiles [x0, y0, x1, y1] (inclusive), or the whole Earth. The boxes are the
# tiles the live pages asked their servers for on 14 Nov 2026 at 1920 x 1080, in the resting view and in the film
# of each story (from the globe down onto the place), with one tile more on every side where a box is a single place,
# widened where the pages of this version asked for a tile outside them (?offline on a page shows any such tile).
# The pages ask for less than before (src/components/flood/story-app.tsx, src/lib/scene3d.ts):
#   base   the picture fades in from zoom 5.2 and the source stops at 12: closer in, the page's own Sentinel-2
#          picture covers the place, and the bottom of the screen sits under the dark band of the caption
#   names  only shown from far out, until zoom 8.4, so its tiles stop at 9
#   far    only shown from far out, until zoom 7, so its tiles stop at 8
#   dem    the relief starts at zoom 6 and stops at 12, finer than the terrain mesh draws at these views
WORLD = "world"
FLOOD, RICE, FIRE = "flood", "rice", "fire"
PLAN = {
    "base": {
        6: [[26, 21, 37, 28]], 7: [[60, 46, 67, 51]], 8: [[123, 94, 132, 100]], 9: [[251, 190, 260, 198]],
        10: {FLOOD: [508, 388, 515, 393], RICE: [506, 388, 515, 392], FIRE: [507, 385, 514, 390]},
        11: {FLOOD: [1019, 780, 1027, 786], RICE: [1018, 777, 1026, 783], FIRE: [1018, 772, 1026, 779]},
        12: {FLOOD: [2043, 1564, 2050, 1570], RICE: [2038, 1558, 2049, 1564], FIRE: [2040, 1548, 2049, 1555]},
    },
    "names": {
        3: WORLD, 4: [[0, 0, 15, 9]], 5: [[10, 8, 21, 16]], 6: [[26, 20, 37, 28]], 7: [[60, 46, 67, 51]],
        8: [[123, 94, 132, 100]], 9: [[251, 192, 260, 198]],
    },
    "far": {
        0: WORLD, 1: WORLD, 2: WORLD, 3: WORLD, 4: [[0, 0, 15, 9]], 5: [[10, 8, 21, 16]], 6: [[26, 21, 37, 28]],
        7: [[60, 46, 67, 51]], 8: [[123, 94, 132, 100]],
    },
    "dem": {
        6: [[30, 23, 33, 25]], 7: [[62, 47, 65, 49]], 8: [[126, 96, 129, 98]], 9: [[254, 192, 257, 197]],
        10: {FLOOD: [510, 390, 512, 392], RICE: [510, 390, 512, 390], FIRE: [510, 386, 512, 388]},
        11: {FLOOD: [1022, 782, 1024, 784], RICE: [1021, 779, 1023, 781], FIRE: [1020, 775, 1023, 777]},
        12: {FLOOD: [2046, 1566, 2048, 1568], RICE: [2044, 1561, 2044, 1561], FIRE: [2045, 1552, 2046, 1554]},
    },
}
# tiles more on every side for the boxes of a single place, which a wider screen or a turned camera reaches: two of
# the light pictures, one of the heavier relief (a 2560 x 1440 screen turned all the way round, tilted to 70 degrees,
# still finds a few relief tiles at the edge; those come from Mapterhorn)
PAD = {"base": 2, "dem": 1}

# terrarium for a height of 0 m, for the open sea tiles that Mapterhorn does not have
SEA_RGB = (128, 0, 0)


def boxes(entry, z, pad):
    """the boxes of one zoom of the plan, as [[x0, y0, x1, y1], ...]"""
    n = 2**z
    if entry == WORLD:
        return [[0, 0, n - 1, n - 1]]
    if isinstance(entry, dict):
        # one box per place, wider on every side
        return [[max(0, x0 - pad), max(0, y0 - pad), min(n - 1, x1 + pad), min(n - 1, y1 + pad)] for x0, y0, x1, y1 in entry.values()]
    return [list(b) for b in entry]


def plan():
    """{source: {z: [[x0, y0, x1, y1], ...]}}"""
    return {source: {z: boxes(entry, z, PAD.get(source, 1)) for z, entry in zooms.items()} for source, zooms in PLAN.items()}


def tiles_in(boxes_by_zoom):
    seen = set()
    for z, bs in boxes_by_zoom.items():
        for x0, y0, x1, y1 in bs:
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    seen.add((z, x, y))
    return sorted(seen)


def sea_tile(path):
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (512, 512), SEA_RGB).save(path, "WEBP", lossless=True)


def fetch(session, source, z, x, y):
    spec = SOURCES[source]
    path = OUT / source / str(z) / str(x) / f"{y}.{spec['ext']}"
    if path.exists() and path.stat().st_size > 0:
        return "kept", path.stat().st_size
    url = spec["remote"].format(z=z, x=x, y=y)
    for attempt in range(4):
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException:
            time.sleep(1 + attempt)
            continue
        if r.status_code == 200 and r.content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            return "new", len(r.content)
        if r.status_code == 404 and source == "dem":
            sea_tile(path)
            return "sea", path.stat().st_size
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 + 2 * attempt)
            continue
        return f"failed {r.status_code}", 0
    return "failed", 0


def write_index(p):
    """src/data/tiles.json: per source its file type, its own server and the boxes that are here, one zoom a line"""
    lines = ['{', ' "note": "written by scripts/bake_tiles.py: the tiles in public/tiles, as boxes [x0, y0, x1, y1] per zoom",', ' "sources": {']
    for i, (source, by_zoom) in enumerate(p.items()):
        spec = SOURCES[source]
        lines.append(f'  "{source}": {{')
        lines.append(f'   "ext": {json.dumps(spec["ext"])},')
        lines.append(f'   "remote": {json.dumps(spec["remote"])},')
        lines.append('   "boxes": {')
        zooms = sorted(by_zoom.items())
        for j, (z, bs) in enumerate(zooms):
            lines.append(f'    "{z}": {json.dumps(bs)}' + ("," if j < len(zooms) - 1 else ""))
        lines.append('   }')
        lines.append('  }' + ("," if i < len(p) - 1 else ""))
    lines += [' }', '}']
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


PATTERNS = {
    "base": re.compile(r"s2cloudless-2017_3857/default/g/(\d+)/(\d+)/(\d+)\.jpg"),
    "names": re.compile(r"overlay_bright_3857/default/g/(\d+)/(\d+)/(\d+)\.png"),
    "far": re.compile(r"GoogleMapsCompatible_Level8/(\d+)/(\d+)/(\d+)\.jpeg"),
    "dem": re.compile(r"tiles\.mapterhorn\.com/(\d+)/(\d+)/(\d+)\.webp"),
}


def check(urls_file, p):
    """How many of the tile addresses in a file (one per line, as the live site asked for them) the plan holds."""
    have = {s: set(tiles_in(b)) for s, b in p.items()}
    missing = {}
    total = {}
    for line in Path(urls_file).read_text(encoding="utf-8").split():
        for source, pat in PATTERNS.items():
            m = pat.search(line)
            if not m:
                continue
            a, b, c = (int(v) for v in m.groups())
            # EOX and GIBS write z/y/x, Mapterhorn z/x/y
            z, x, y = (a, c, b) if source != "dem" else (a, b, c)
            total[source] = total.get(source, 0) + 1
            if (z, x, y) not in have[source]:
                missing.setdefault(source, set()).add((z, x, y))
    for source in SOURCES:
        miss = sorted(missing.get(source, ()))
        print(f"{source:6s} asked {total.get(source, 0):5d}, outside the plan {len(miss):4d}  {miss[:12]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true", help="count the tiles, download nothing")
    ap.add_argument("--check", metavar="FILE", help="a list of tile addresses to test against the plan")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    p = plan()
    if args.check:
        check(args.check, p)
        return 0
    for source, by_zoom in p.items():
        counts = {z: len(tiles_in({z: bs})) for z, bs in by_zoom.items()}
        print(f"{source:6s} {sum(counts.values()):5d} tiles  " + "  ".join(f"z{z}:{n}" for z, n in counts.items()))
    if args.plan:
        return 0
    session = requests.Session()
    # a plain client name, nothing about who runs it
    session.headers["User-Agent"] = "nisar-valencia-web tile bake (hackathon app, small regional extract)"
    failed = []
    for source, by_zoom in p.items():
        todo = tiles_in(by_zoom)
        sizes = {"new": 0, "kept": 0, "sea": 0}
        with ThreadPoolExecutor(args.workers) as pool:
            for (z, x, y), (state, size) in zip(todo, pool.map(lambda t: fetch(session, source, *t), todo)):
                if state.startswith("failed"):
                    failed.append((source, z, x, y, state))
                else:
                    sizes[state] += size
        total = sum(f.stat().st_size for f in (OUT / source).rglob(f"*.{SOURCES[source]['ext']}"))
        print(f"{source}: {len(todo)} tiles ({sizes['new'] / 1e6:.1f} MB new), {total / 1e6:.1f} MB on disk", flush=True)
    if failed:
        print(f"{len(failed)} tiles failed, run again: {failed[:10]}")
        return 1
    write_index(p)
    print(f"index written to {INDEX.relative_to(WEB)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
