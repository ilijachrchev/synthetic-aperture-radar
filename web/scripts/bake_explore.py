"""Bake the layers of the flat flood explorer (/explore): official zones, what really flooded, NISAR's view.

    python web/scripts/bake_explore.py          (from the repository root, with the pipeline environment)

The prediction layers come from bake_prediction.py (prediction.json and prediction/ of each site); this script writes
the rest, under web/public/layers/explore/:

    zones_horta_sud.json, zones_pego_oliva.json   official flood zones (SNCZI): frequent T10, occasional T100, rare
                                                  T500, clipped to the municipalities (data/zones, PR #36)
    floods_2024.json, buildings_2024.json         DANA of 29 Oct 2024, L'Horta Sud: Copernicus EMS EMSR773 observed
                                                  flood (flooded area and flood traces) and its graded buildings
    floods_2026.json                              DANA Adam, 18 to 19 Oct 2026, Pego and Oliva: EMSR935 observed flood
    municipalities.json                           the 12 municipalities the zones were checked in
    nisar_<site>_before.webp, _after.webp         NISAR open water before and after DANA Adam (16 and 28 Oct 2026,
                                                  track 066 D), from PR #35's DANA layer: after shows new water bright
                                                  and water on both dates deep blue
    still_flooded_pego_oliva.webp                 the EMSR935 flooded land NISAR still saw as open water on 28 Oct
    nisar_<site>.bin                              what a click reads (format PLN1 of bake_prediction.py): the DANA
                                                  code of every pixel of those pictures, and 1 where still flooded
    explore.json                                  the index: files and bytes, the corners of every picture, the
                                                  numbers the page shows, each with the file it comes from

The GeoJSON is copied as pipeline/zones.py wrote it (WGS84, 5 decimals, already simplified), with long text fields
left out. The pictures are RGBA on the zoom 13 Web Mercator lattice (about 15 m here), nearest neighbour from the 20 m
UTM labels, so MapLibre draws them as image sources without any code of ours.

Needs numpy, rasterio and pillow. Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import Resampling, reproject, transform_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bake_prediction import STORY_SERIES, bounds_of, planes, still_mask  # noqa: E402
from bake_water import RES, pixel_ha, web_grid  # noqa: E402

WEB = Path(__file__).resolve().parents[1]
REPO = WEB.parent
OUT = WEB / "public" / "layers" / "explore"
ZONES = REPO / "data" / "zones"
LABELS = REPO / "data" / "labels_nisar"
SUMMARY = REPO / "data" / "metrics" / "nisar_labels_summary.json"
SITES = {"pego_oliva": "Pego-Oliva", "albufera": "Albufera"}
# the GeoJSON of PR #36, and what the page calls it
VECTORS = {
    "zones_horta_sud": ("zones_horta_sud.geojson", ["zone", "area_ha"]),
    "zones_pego_oliva": ("zones_pego_oliva.geojson", ["zone", "area_ha"]),
    "floods_2024": ("floods_dana_2024_horta_sud.geojson", ["municipality", "zone", "observed", "area_ha"]),
    "buildings_2024": ("buildings_dana_2024_horta_sud.geojson", ["municipality", "zone", "damage"]),
    "floods_2026": ("floods_dana_adam_2026_pego_oliva.geojson", ["municipality", "zone", "observed", "area_ha"]),
    "municipalities": ("municipalities.geojson", ["name", "ine", "event", "flooded_ha", "outside_every_zone_pct", "only_rare_t500_pct", "frequent_or_occasional_pct"]),
}
# DANA codes of PR #35: 0 dry on both dates, 1 open water on both, 2 new open water, 3 gone, 4 permanent, 255 none
BOTH, NEW, GONE = 1, 2, 3
COLOURS = {
    "before": {BOTH: (34, 104, 214, 225), GONE: (34, 104, 214, 225)},
    "after": {NEW: (64, 170, 255, 240), BOTH: (20, 64, 150, 215)},
    "still": {1: (255, 160, 48, 240)},
}


def vectors() -> dict:
    out = {}
    for key, (name, keep) in VECTORS.items():
        src = ZONES / name
        if not src.exists():
            print(f"  {key}: {src} missing, skipped")
            continue
        doc = json.loads(src.read_text(encoding="utf-8"))
        for f in doc["features"]:
            f["properties"] = {k: f["properties"][k] for k in keep if k in f["properties"]}
        path = OUT / f"{key}.json"
        path.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        out[key] = {"file": f"{key}.json", "bytes": path.stat().st_size, "features": len(doc["features"]),
                    "source": src.relative_to(REPO).as_posix()}
        print(f"  {key}: {len(doc['features'])} features, {path.stat().st_size / 1e3:.0f} kB")
    return out


def picture(path: Path, codes: np.ndarray, colours: dict) -> int:
    rgba = np.zeros(codes.shape + (4,), "uint8")
    for code, c in colours.items():
        rgba[codes == code] = c
    Image.fromarray(rgba, "RGBA").save(path, "WEBP", lossless=True, quality=100, method=6)
    return path.stat().st_size


def nisar(site: str) -> dict | None:
    stack = STORY_SERIES[site].replace("nisar_", "")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))["sites"][site]["dana"]["stacks"].get(stack) if SUMMARY.exists() else None
    if not summary:
        return None
    f_dana = REPO / summary["layer"]
    with rasterio.open(f_dana) as s:
        dana, t, crs = s.read(1), s.transform, s.crs
        west, south, east, north = transform_bounds(crs, "EPSG:4326", *s.bounds)
    # the zoom 13 lattice window that holds the whole label grid
    wt, w, h = web_grid((west, south, east, north))
    codes = np.full((h, w), 255, "uint8")
    reproject(dana, codes, src_transform=t, src_crs=crs, src_nodata=255, dst_transform=wt, dst_crs="EPSG:3857",
              dst_nodata=255, resampling=Resampling.nearest)
    files = {}
    for when in ("before", "after"):
        path = OUT / f"nisar_{site}_{when}.webp"
        files[when] = {"file": path.name, "bytes": picture(path, codes, COLOURS[when])}
    row_ha = pixel_ha(wt, h)[:, None]
    drawn = {"new_ha": round(float((row_ha * (codes == NEW)).sum()), 1), "on_both_ha": round(float((row_ha * (codes == BOTH)).sum()), 1)}
    ow = summary["open_water"]
    rec = {
        "stack": stack, "before": summary["before"], "after": summary["after"], "bounds": bounds_of(wt, w, h), "size": [w, h], "pictures": files,
        "open_water": {k: ow[k] for k in ("before_ha", "after_ha", "new_ha", "on_both_ha", "gone_ha")},
        "drawn": drawn,
        "rule": "open water of the v1 U-Net ensemble at 0.3, outside permanent water, on land labelled on both dates (PR #35)",
        "sources": {"layer": summary["layer"], "numbers": f"{SUMMARY.relative_to(REPO).as_posix()} sites.{site}.dana.stacks.{stack}.open_water"},
    }
    still = still_mask(site)
    if still is not None:
        mask, mt, mcrs, entry, key = still
        sm = np.zeros((h, w), "uint8")
        reproject(mask.astype("uint8"), sm, src_transform=mt, src_crs=mcrs, dst_transform=wt, dst_crs="EPSG:3857",
                  src_nodata=None, dst_nodata=None, resampling=Resampling.nearest)
        path = OUT / f"still_flooded_{site}.webp"
        size = picture(path, sm, COLOURS["still"])
        numbers = entry["per_pass"][key]
        rec["still"] = {
            "file": path.name, "bytes": size, "date": key.split()[-1], "outline": entry["outline"], "outline_ha": entry["outline_ha"],
            "seen_ha": numbers["seen_ha"], "open_water_ha": numbers["open_water_ha"], "open_water_share": numbers["open_water_share"],
            "drawn_ha": round(float((row_ha * (sm == 1)).sum()), 1),
            "source": f"{SUMMARY.relative_to(REPO).as_posix()} sites.{site}.dana.emsr935_flooded_area_still_water.per_pass['{key}']",
        }
    still_plane = np.zeros((h, w), "uint8")
    if "still" in rec:
        still_plane = sm
    path = OUT / f"nisar_{site}.bin"
    rec["data"] = {"file": path.name, "bytes": planes(path, [codes, still_plane]), "planes": ["dana_code", "still_flooded"],
                   "codes": {"0": "dry on both dates", "1": "open water on both dates", "2": "new open water", "3": "open water gone",
                             "4": "permanent water", "255": "not compared (no data, sea or built-up)"}}
    print(f"  {site} NISAR {stack}: new {ow['new_ha']} ha (drawn {drawn['new_ha']}), both {ow['on_both_ha']} ha (drawn {drawn['on_both_ha']})"
          + (f", still flooded {rec['still']['open_water_ha']} ha (drawn {rec['still']['drawn_ha']})" if "still" in rec else ""), flush=True)
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("vectors (data/zones, PR #36)")
    vec = vectors()
    print("NISAR before and after DANA Adam (data/labels_nisar, PR #35)")
    sites = {site: {"name": name, "nisar": nisar(site)} for site, name in SITES.items()}
    doc = {
        "made_by": "web/scripts/bake_explore.py",
        "baked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vectors": vec,
        "sites": sites,
        "zones": {"frequent": "T10, high probability (1 in 10 each year)", "occasional": "T100, medium probability (1 in 100 each year)",
                  "rare": "T500, low probability (1 in 500 each year)", "source": "SNCZI, Ministerio para la Transicion Ecologica (MITECO), through data/zones (PR #36)"},
        "note": "Two DANAs, never mixed: 29 Oct 2024 at L'Horta Sud (before NISAR had data, context only) and DANA Adam, 18 to 19 Oct 2026, at Pego-Oliva (NISAR saw it). docs/ZONES.md",
    }
    (OUT / "explore.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.iterdir())
    print(f"explore: {len(list(OUT.iterdir()))} files, {total / 1e6:.1f} MB in web/public/layers/explore")


if __name__ == "__main__":
    main()
