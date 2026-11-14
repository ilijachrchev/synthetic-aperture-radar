"""Fetch NISAR public browse previews for the app's sites and cut each one to its site box.

    python -I scripts/fetch_radar.py --raw <folder for the full PNGs, outside the repo>

Queries NASA CMR (public, no login) for GCOV and GUNW granules over each site and downloads each granule's browse
PNG (about 3 MB, never the 1 to 7 GB granule). The browse is a lat/lon grid, so its extent is the bounding box of
the granule polygon. Each preview is cut to the site box, pixels outside the radar footprint become transparent,
and the result is written as WebP to public/radar/<site>/, with every pass listed in src/data/passes.json.
Run from the web/ folder.
"""
import argparse, io, json, os, re, sys, urllib.parse, urllib.request
import numpy as np
from PIL import Image, ImageDraw

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
UA = {"User-Agent": "space-apps-nisar-demo"}
COLLECTIONS = {
    "GCOV": ["NISAR_L2_GCOV_PROVISIONAL_V1", "NISAR_L2_GCOV_V1"],
    "GUNW": ["NISAR_L2_GUNW_PROVISIONAL_V1", "NISAR_L2_GUNW_V1"],
}
# box is (west, south, east, north) in degrees
SITES = {
    "albufera": {"product": "GCOV", "point": (-0.35, 39.33), "box": (-0.52, 39.15, -0.16, 39.50), "start": "2026-06-01"},
    "pego": {"product": "GCOV", "point": (-0.07, 38.87), "box": (-0.24, 38.76, 0.08, 38.99), "start": "2026-09-01"},
    "espada": {"product": "GCOV", "point": (-0.45, 39.95), "box": (-0.72, 39.78, -0.20, 40.10), "start": "2026-07-01"},
    "lorca": {"product": "GUNW", "point": (-1.70, 37.68), "box": (-1.98, 37.48, -1.42, 37.86), "start": "2026-06-01"},
    # the M7.7 struck on 9 Oct at 17:56 UTC; pairs that start before it and end after it hold the co-seismic signal
    # the epicentre sits on the east edge of track 141 D frame 085, and GUNW masks the sea, so the box hugs the fringes
    "panama": {"product": "GUNW", "point": (-80.76, 7.61), "box": (-81.37, 7.55, -80.56, 8.12), "start": "2026-09-15", "end": "2026-10-12",
               "tracks": ["141"], "min_valid": 0.25},
    # a wider view of the Valencia coast for the landing, one track so every pass shares one geometry
    "valencia": {"product": "GCOV", "point": (-0.35, 39.33), "box": (-0.78, 38.92, 0.02, 39.70), "start": "2026-06-01", "tracks": ["066"]},
}
END = "2026-11-14"


def get_json(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90))


def granules(short_name, point, start, end):
    q = urllib.parse.urlencode({"short_name": short_name, "point": f"{point[0]},{point[1]}", "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z", "page_size": 2000, "sort_key": "start_date"})
    return get_json(f"{CMR}?{q}")["feed"]["entry"]


def polygon(entry):
    """CMR polygons are 'lat lon lat lon ...' strings; returns [(lon, lat), ...]."""
    if entry.get("polygons"):
        nums = [float(v) for v in entry["polygons"][0][0].split()]
        return [(nums[i + 1], nums[i]) for i in range(0, len(nums), 2)]
    if entry.get("boxes"):
        s, w, n, e = (float(v) for v in entry["boxes"][0].split())
        return [(w, s), (e, s), (e, n), (w, n)]
    return None


def browse_url(entry):
    for link in entry.get("links", []):
        href = link.get("href", "")
        if href.startswith("https") and href.lower().endswith(".png") and "thumbnail" not in href.lower():
            return href
    return None


def parse_name(title):
    # GCOV: ..._GCOV_<cycle>_<track>_<A|D>_<frame>_<mode>_...; GUNW adds the second cycle before the mode
    m = re.match(r"NISAR_L2_\w+?_(GCOV|GUNW)_(\d{3})_(\d{3})_([AD])_(\d{3})(?:_\d{3})?_(\d{4})_", title)
    stamps = re.findall(r"(\d{8})T\d{6}", title)
    crid = re.search(r"_(P\d{5})_", title)
    info = {"cycle": m.group(2), "track": m.group(3), "dir": m.group(4), "frame": m.group(5), "mode": m.group(6)} if m else {}
    info["dates"] = sorted({f"{s[:4]}-{s[4:6]}-{s[6:]}" for s in stamps})
    info["crid"] = crid.group(1) if crid else None
    return info


def cut(png_path, poly, box, out_path, product):
    im = Image.open(png_path).convert("RGB")
    w, h = im.size
    lons = [p[0] for p in poly]
    lats = [p[1] for p in poly]
    west, east, south, north = min(lons), max(lons), min(lats), max(lats)

    def px(lon, lat):
        return ((lon - west) / (east - west) * w, (north - lat) / (north - south) * h)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([px(lon, lat) for lon, lat in poly], fill=255)
    # no-data inside the footprint: pure black on backscatter previews, pure white where GUNW masks water
    rgb = np.asarray(im)
    nodata = (rgb >= 252).all(axis=2) if product == "GUNW" else (rgb <= 3).all(axis=2)
    m = np.asarray(mask).copy()
    m[nodata] = 0
    mask = Image.fromarray(m)
    rgba = im.copy()
    rgba.putalpha(mask)
    x0, y0 = px(box[0], box[3])
    x1, y1 = px(box[2], box[1])
    crop = rgba.crop((round(x0), round(y0), round(x1), round(y1)))
    alpha = crop.getchannel("A")
    valid = sum(1 for v in alpha.getdata() if v > 0) / (crop.width * crop.height)
    crop.save(out_path, "WEBP", quality=86, method=6)
    return valid, crop.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="folder for the full browse PNGs (kept out of the repo)")
    ap.add_argument("--min-valid", type=float, default=0.55)
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)
    manifest = {"source": "NASA CMR granule search and NISAR browse images (ASF DAAC), public, no login", "sites": {}}
    for site, cfg in SITES.items():
        out_dir = os.path.join("public", "radar", site)
        os.makedirs(out_dir, exist_ok=True)
        passes, seen = [], set()
        for short in COLLECTIONS[cfg["product"]]:
            for e in granules(short, cfg["point"], cfg["start"], cfg.get("end", END)):
                info, poly, url = parse_name(e["title"]), polygon(e), browse_url(e)
                if not (info.get("track") and poly and url):
                    continue
                if cfg.get("tracks") and info["track"] not in cfg["tracks"]:
                    continue
                key = (tuple(info["dates"]), info["track"], info["dir"])
                if key in seen:
                    continue
                seen.add(key)
                raw = os.path.join(a.raw, os.path.basename(urllib.parse.urlparse(url).path))
                if not os.path.exists(raw):
                    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
                    open(raw, "wb").write(data)
                stamp = "_".join(d.replace("-", "") for d in info["dates"])
                name = f"{stamp}_{info['track']}{info['dir']}.webp"
                valid, size = cut(raw, poly, cfg["box"], os.path.join(out_dir, name), cfg["product"])
                img = f"/radar/{site}/{name}"
                if valid < cfg.get("min_valid", a.min_valid):
                    # the pass is real and still counted; it just does not fill this box well enough to show
                    os.remove(os.path.join(out_dir, name))
                    img = None
                    print(f"  no image {site} {stamp} {info['track']}{info['dir']} (only {valid:.0%} of the box inside the footprint)")
                row = {"dates": info["dates"], "track": info["track"], "dir": info["dir"], "frame": info["frame"], "mode": info["mode"],
                       "crid": info["crid"], "collection": short, "granule": e["title"], "img": img,
                       "valid": round(valid, 3), "px": list(size)}
                passes.append(row)
                print(f"  {site} {' > '.join(info['dates'])} {info['track']}{info['dir']} {info['crid']} {valid:.0%}")
        passes.sort(key=lambda r: (r["dates"][-1], r["track"]))
        manifest["sites"][site] = {"product": cfg["product"], "box": list(cfg["box"]), "point": list(cfg["point"]), "passes": passes}
        print(f"{site}: {len(passes)} passes")
    os.makedirs(os.path.join("src", "data"), exist_ok=True)
    with open(os.path.join("src", "data", "passes.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)


if __name__ == "__main__":
    sys.exit(main())
