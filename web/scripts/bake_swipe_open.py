"""Bake the swipe of the guided flood map (/explore, step 4) with open water only on both sides.

    python web/scripts/bake_swipe_open.py        (from the repository root, pipeline environment, PYTHONPATH set to it)

The /views swipe (bake_views.py) shows water of any kind on both sides: Sentinel-1 OPERA DSWx-S1 classes 1 and 3
(open water and flooded vegetation) and NISAR's v1 model at 0.3 on p(open water or flooded vegetation). This bake
shows open water only on both sides, so the two pictures and their numbers measure the same thing:

    Sentinel-1   DSWx-S1 B01_WTR class 1 (open water)
    NISAR        v1 model (5 U-Nets) at 0.3 on p(open water), the rule of the NISAR labels (PR #35)

Everything else is bake_views.py's swipe for the same evening at Pego-Oliva (28 Oct 2026, track 066 D): the same grid
(the zoom 13 lattice of meta.json), the same land both maps cover, the same referee (an optical OPERA DSWx-HLS map
within a day, its open water outside permanent water, only where it is clear) and the same "finds" rule (the share
of that optical open water on each radar map). The numbers are written for both definitions, open water and any
water, so the step can say which one it shows; the any-water ones equal views.json.

Writes web/public/layers/guided/swipe_<day>_s1_open.webp, swipe_<day>_nisar_open.webp and swipe.json (bounds,
files, times, numbers with their sources). Needs the pipeline's data: data/stack, data/raw/dswx, data/optical and
data/interim/cv_prob (not in git). Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bake_views as bv  # noqa: E402  (its imports put the repository on the path)

OUT = bv.WEB / "public" / "layers" / "guided"
SITE = "pego_oliva"
DAY = "2026-10-28"
THIS = "web/scripts/bake_swipe_open.py"
# the sea under both pictures, one even colour: the base map's own sea is a patchwork of dark tiles with hard edges
SEA_RGBA = (14, 36, 49, 255)


def save_even_sea(classes: np.ndarray, path: Path) -> int:
    """bake_views.save_rgba, with the sea (meta.json's base.png, red 255 on the sea, the same lattice) in one colour
    wherever the picture paints nothing there or only "not covered" (alpha under 200); the water each radar sees
    along the coast stays on top."""
    from PIL import Image

    meta = json.loads((bv.WEB / "public" / "layers" / SITE / "meta.json").read_text(encoding="utf-8"))
    sea = np.asarray(Image.open(bv.WEB / "public" / "layers" / SITE / meta["base"]).convert("RGB"))[..., 0] == 255
    rgba = bv.LUT[classes].copy()
    rgba[sea & (rgba[..., 3] < 200)] = SEA_RGBA
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path, "WEBP", lossless=True, quality=100, method=6)
    return path.stat().st_size


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = bv.SITES[SITE]
    stack = cfg["stack"]
    grid = bv.Grid(cfg["bbox"])
    meta = json.loads((bv.OUT_ROOT / SITE / "meta.json").read_text(encoding="utf-8"))
    if (meta["width"], meta["height"]) != (grid.width, grid.height):
        raise SystemExit("the view grid is not the map grid of meta.json")
    ds = bv.open_stack(bv.stack_file(SITE, stack))
    sea = bv.sea_of(SITE, (ds.sizes["y"], ds.sizes["x"]))
    perm = bv.permanent_water(ds, SITE)
    view = bv.in_view(ds, grid)
    land = ~sea & view

    entry = bv.dswx_entry(SITE, stack, DAY)
    tiles = bv.dswx_files(entry)
    dswx = bv.dswx_on_grid(ds, tiles)
    p_open, p_any = bv.load_cached("v1", SITE, stack, DAY)
    n_ok = np.isfinite(p_any)
    s_ok = ~np.isin(dswx, bv.DSWX_INVALID)
    both = land & n_ok & s_ok
    maps = {
        "open": {"s1": s_ok & (dswx == bv.DSWX_OPEN_WATER),
                 "nisar": n_ok & (np.nan_to_num(p_open, nan=0.0) >= bv.V1_THRESHOLD)},
        "any": {"s1": s_ok & np.isin(dswx, (bv.DSWX_OPEN_WATER, bv.DSWX_INUNDATED_VEG)),
                "nisar": n_ok & (np.nan_to_num(p_any, nan=0.0) >= bv.V1_THRESHOLD)},
    }

    files = {}
    for name, ok in (("s1", s_ok), ("nisar", n_ok)):
        path = OUT / f"swipe_{DAY}_{name}_open.webp"
        size = save_even_sea(bv.on_web(bv.picture(maps["open"][name], ok, sea), ds, grid), path)
        files[name] = {"file": path.name, "bytes": size}

    t = bv.date_index(ds)[DAY]
    granule = bv.granule_at(ds, t)
    t_nisar, t_s1 = bv.nisar_time(granule, DAY), bv.s1_time(entry)
    optical = bv.optical_classes(SITE, stack, DAY)
    changing = both & ~perm
    clear = changing & np.isin(optical, (0, 1, 2))
    wet = changing & (optical == 1)
    src_o = str(bv.rel(bv.OPTICAL_DIR / f"{SITE}_{stack}" / f"{DAY}.tif"))
    src_n = [str(bv.rel(bv.stack_file(SITE, stack))), str(bv.rel(bv.cache_path("v1", SITE, stack, DAY)))]
    src_s = [Path(f).name for f in tiles]
    a = lambda m: round(float(bv.area_ha(m)), 1)  # noqa: E731
    numbers = {
        "optical_clear": {"value": round(bv.share(clear, changing), 3), "what": "of the changing land the optical map saw clear", "source": [src_o]},
        "optical_open_water_ha": {"value": a(wet), "what": "open water the optical map sees, outside permanent water", "source": [src_o]},
    }
    for kind, m in maps.items():
        label = "open water" if kind == "open" else "open water and flooded vegetation"
        numbers[f"nisar_finds_{kind}"] = {"value": round(bv.share(m["nisar"], wet), 3), "what": f"of that optical open water on NISAR's map of {label}", "source": src_n + [src_o]}
        numbers[f"s1_finds_{kind}"] = {"value": round(bv.share(m["s1"], wet), 3), "what": f"of that optical open water on Sentinel-1's map of {label}", "source": src_s + [src_o]}
        numbers[f"nisar_water_ha_{kind}"] = {"value": a(m["nisar"] & both), "what": f"{label} NISAR maps on the land both maps cover", "source": src_n}
        numbers[f"s1_water_ha_{kind}"] = {"value": a(m["s1"] & both), "what": f"{label} Sentinel-1 maps there", "source": src_s}
    doc = {
        "made_by": THIS,
        "baked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": SITE, "date": DAY, "bounds": grid.bounds, "width": grid.width, "height": grid.height,
        "shows": "open water only on both sides",
        "nisar": {**files["nisar"], "time_utc": t_nisar, "granule": granule,
                  "product": "NISAR GCOV, team CV model v1 (5 U-Nets) at 0.3 on p(open water)"},
        "s1": {**files["s1"], "time_utc": t_s1, "granules": src_s, "product": "OPERA DSWx-S1 B01_WTR class 1 (open water)"},
        "numbers": numbers,
        "rule": ("the swipe of bake_views.py for the same evening, open water only: DSWx-S1 class 1 against v1 p(open water) >= 0.3; "
                 "referee an optical OPERA DSWx-HLS map within a day, open water outside permanent water, where clear"),
        "views_json_any_water": "public/layers/pego_oliva/views.json views.swipe.items[2026-10-28].numbers (nisar_finds, s1_finds): any water",
    }
    (OUT / "swipe.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v["value"] for k, v in numbers.items()}, indent=1))
    print({k: v["bytes"] for k, v in files.items()}, flush=True)


if __name__ == "__main__":
    main()
