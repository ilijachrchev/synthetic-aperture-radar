"""Map layers for the web app: one CV water layer per NISAR date, plus manifest entries.

    python -m pipeline.cv.export --model data/models/cv_unet.pt
    python -m pipeline.cv.export --model data/models/a.pt data/models/b.pt   # their ensemble

For every site, stack and date (all dates of the stack, labelled or not):

    data/cv/<site>_<stack>/<YYYY-MM-DD>_water.tif
        uint8 classes, web-optimized COG (EPSG:3857) with a colormap:
        0 not water (transparent), 1 open water, 2 flooded vegetation (only
        with --flooded-veg and a three-class model), 255 no data or sea

    data/cv/<site>_<stack>/<YYYY-MM-DD>_water_p.tif
        uint8 round(P(water) x 200), 0 to 200, 255 no data or sea; the same
        web grid, for drawing the uncertain band at a pass

and per stack, for animations that show water spreading and receding smoothly
between radar passes:

    data/cv/<site>_<stack>/first_water_doy.tif, last_water_doy.tif
        uint16 day of year (2026) of the first and the last date the pixel is
        water; 0 never water on a seen date, 65535 never seen or sea

plus one data/manifest.json entry per layer (the shared list format of
pipeline.ml.export): model "cv", site, stack, layer, date, file, classes, the
water area in hectares, the source granule, the model and the threshold.
Entries are keyed by (model, site, stack, layer, date), so a rerun replaces them.

The sea (data/context/<site>_sea_20m.tif) is left out: it is always water and
the base map already shows it. Flooded vegetation is off by default: on the
validation blocks the three-class models find only 1 to 6 % of it.

    python -m pipeline.cv.export --burn          # the Espadà burn scar, no model needed

    data/cv/espada_058_A_022/<YYYY-MM-DD>_burn.tif
        uint8, 0 not burned, 1 burned so far, 255 no data, sea or permanent water

Burn rule (the CV baseline): HV, 5x5 filtered, at least 1.5 dB below the last
date before ignition, on WorldCover tree cover, shrub or grass, and on two
NISAR passes in a row. A burned pixel stays burned, dated from the first of the
two passes. Against the EFFIS outline (9,230 ha) on 28 Oct: 4,932 ha inside,
84 ha within 2 km, 313 ha farther, precision 0.93; it finds about half of the
fire area. A single drop without the second pass flickers and fires farther out
(precision 0.83), which is why the rule asks for two.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import morecantile
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from pipeline.config import DATA_DIR, DSWX_LABEL_SITES, REPO_ROOT, STACK_DIR, STACKS
from pipeline.cv.baseline import BURN_DROP_DB, area_ha, burn_candidate
from pipeline.cv.data import grid_of, open_stack
from pipeline.cv.evaluate import (
    BURN, CONTEXT_DIR, EXTRA_TEST_STACKS, date_index, load_predictor, permanent_water, scene_db,
)
from pipeline.stack import Grid

CV_OUT_DIR = DATA_DIR / "cv"
MANIFEST = DATA_DIR / "manifest.json"
NODATA = 255
DOY_NEVER, DOY_NODATA = 0, 65535
CLASSES = ["not_water", "open_water", "flooded_vegetation"]
COLORMAP = {0: (0, 0, 0, 0), 1: (30, 110, 255, 255), 2: (0, 190, 160, 255), NODATA: (0, 0, 0, 0)}
BURN_COLORMAP = {0: (0, 0, 0, 0), 1: (205, 75, 35, 255), NODATA: (0, 0, 0, 0)}
KEY_FIELDS = ("model", "site", "stack", "layer", "date")   # one entry per date (water, probability, burn)
STACK_KEY_FIELDS = ("model", "site", "stack", "layer")     # one entry per stack (first and last water day)
PER_STACK_LAYERS = ("first_water_doy", "last_water_doy")
VEGETATION = (10, 20, 30)  # WorldCover tree cover, shrubland, grassland: what a wildfire burns
BURN_STACK = "058_A_022"
BURN_METHOD = (f"HV (5x5 filtered) at least {BURN_DROP_DB} dB below the last date before ignition, on WorldCover "
               "tree cover, shrub or grass, on two NISAR passes in a row; burned stays burned, dated from the first "
               "of the two passes")


def water_classes(p_open: np.ndarray, p_any: np.ndarray, threshold: float, three: bool,
                  sea: np.ndarray | None = None) -> np.ndarray:
    """uint8 map: water where p_any >= threshold; within it open water (1) or, for a
    three-class model, flooded vegetation (2) where that class is the likelier one."""
    ok = np.isfinite(p_open) & np.isfinite(p_any)
    out = np.full(p_open.shape, NODATA, "uint8")
    out[ok] = 0
    water = ok & (p_any >= threshold)
    if three:
        p_veg = p_any - p_open
        out[water & (p_open >= p_veg)] = 1
        out[water & (p_open < p_veg)] = 2
    else:
        out[water] = 1
    if sea is not None:
        out[sea] = NODATA
    return out


def probability_u8(p_any: np.ndarray, sea: np.ndarray | None = None) -> np.ndarray:
    """uint8 round(P(water) x 200), 0 to 200; NODATA where unknown or sea."""
    out = np.full(p_any.shape, NODATA, "uint8")
    ok = np.isfinite(p_any)
    out[ok] = np.clip(np.round(p_any[ok] * 200), 0, 200).astype("uint8")
    if sea is not None:
        out[sea] = NODATA
    return out


def water_days(water: np.ndarray, seen: np.ndarray, doy: np.ndarray,
               sea: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(first, last) day of year a pixel is water, from (t, H, W) water and seen masks.

    DOY_NEVER where the pixel was seen but never water, DOY_NODATA where it was
    never seen (or is sea).
    """
    t = water.shape[0]
    idx = np.arange(t)[:, None, None]
    hit = water & seen
    any_hit = hit.any(axis=0)
    first_i = np.where(hit, idx, t).min(axis=0)
    last_i = np.where(hit, idx, -1).max(axis=0)
    doy = np.asarray(doy, dtype=np.uint16)
    first = np.where(any_hit, doy[np.minimum(first_i, t - 1)], DOY_NEVER).astype(np.uint16)
    last = np.where(any_hit, doy[np.maximum(last_i, 0)], DOY_NEVER).astype(np.uint16)
    never_seen = ~seen.any(axis=0)
    if sea is not None:
        never_seen |= sea
    first[never_seen] = DOY_NODATA
    last[never_seen] = DOY_NODATA
    return first, last


def lasting_start(drops: list[np.ndarray]) -> np.ndarray:
    """Per pixel, the index of the first pass that starts a drop seen on it and the next pass; -1 if none."""
    start = np.full(drops[0].shape, -1, np.int16)
    for i in range(len(drops) - 1):
        new = (start < 0) & drops[i] & drops[i + 1]
        start[new] = i
    return start


def export_burn(site: str = BURN["site"], stack_id: str = BURN_STACK, out_dir: Path = CV_OUT_DIR) -> list[dict]:
    """One 'burned so far' COG per date of the burn stack (see BURN_METHOD); returns manifest entries."""
    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    crs, transform, (h, w) = grid_of(ds)
    grid = Grid(crs, transform, w, h)
    days = date_index(ds)
    with rasterio.open(CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif") as src:
        vegetation = np.isin(src.read(1), VEGETATION)
    excluded = permanent_water(ds, site)
    sea = sea_mask(site, (h, w))
    if sea is not None:
        excluded |= sea
    reference = max(d for d in days if d < BURN["ignition"])
    hv_ref, ok_ref = scene_db(ds["HV"].values[days[reference]], ds["valid"].values[days[reference]])
    after, drops = [], []
    for day, t in days.items():
        if day <= BURN["ignition"]:
            continue
        hv, ok = scene_db(ds["HV"].values[t], ds["valid"].values[t])
        if ok.any():  # HH-only dates have no HV and cannot show a drop
            after.append(day)
            drops.append(vegetation & burn_candidate(hv_ref, hv, ok_ref & ok & ~excluded))
    start = lasting_start(drops)
    entries = []
    for day, t in days.items():
        burned = (start >= 0) & np.isin(start, [i for i, d in enumerate(after) if d <= day])
        out = np.full((h, w), NODATA, "uint8")
        out[ok_ref & ~excluded] = 0
        out[burned] = 1
        path = write_cog(out, grid, out_dir / f"{site}_{stack_id}" / f"{day}_burn.tif", colormap=BURN_COLORMAP)
        source = {k: str(ds[k].values[t]) for k in ("granule_ur", "crid", "maturity", "pols") if k in ds}
        entries.append({
            "model": "cv", "site": site, "stack": stack_id, "layer": "burn", "date": day, "file": _rel(path),
            "classes": ["not_burned", "burned"], "burned_ha": round(area_ha(burned), 1),
            "source": source, "reference_date": reference, "method": BURN_METHOD, "model_file": "baseline",
        })
        print(f"  {site} {stack_id} {day}: burned so far {entries[-1]['burned_ha']} ha", flush=True)
    return entries


def write_cog(array: np.ndarray, grid: Grid, path: Path, colormap: dict | None = COLORMAP) -> Path:
    """Web-optimized (EPSG:3857) COG, nearest resampling, like pipeline.ml.export (uint8 or uint16)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nodata = NODATA if array.dtype == np.uint8 else DOY_NODATA
    profile = {"driver": "GTiff", "height": grid.height, "width": grid.width, "count": 1, "dtype": array.dtype.name,
               "crs": grid.crs, "transform": grid.transform, "nodata": nodata}
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(array, 1)
            if colormap:
                dst.write_colormap(1, colormap)
        with mem.open() as src:
            cog_translate(src, str(path), cog_profiles.get("deflate"), tms=morecantile.tms.get("WebMercatorQuad"),
                          colormap=colormap, resampling="nearest", overview_resampling="nearest", quiet=True)
    return path


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sea_mask(site: str, shape: tuple[int, int]) -> np.ndarray | None:
    path = CONTEXT_DIR / f"{site}_sea_20m.tif"
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        sea = src.read(1) == 1
    return sea if sea.shape == shape else None


def export_stack(site: str, stack_id: str, predictor, threshold: float, out_dir: Path = CV_OUT_DIR,
                 flooded_veg: bool = False, model_label: str = "cv_unet") -> list[dict]:
    """Write one water COG per date of a stack plus the first/last water days; returns manifest entries."""
    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    crs, transform, (h, w) = grid_of(ds)
    grid = Grid(crs, transform, w, h)
    sea = sea_mask(site, (h, w))
    three = flooded_veg and predictor.checkpoint["config"].get("label_mode") == "three"
    days = date_index(ds)
    doy = np.array([(np.datetime64(d) - np.datetime64(d[:4] + "-01-01")).astype(int) + 1 for d in days], np.uint16)
    water_t = np.zeros((len(days), h, w), bool)
    seen_t = np.zeros((len(days), h, w), bool)
    entries = []
    for i, (day, t) in enumerate(days.items()):
        p_open, p_any = predictor.probabilities(ds, t)
        classes = water_classes(p_open, p_any, threshold, three, sea)
        water_t[i], seen_t[i] = np.isin(classes, (1, 2)), classes != NODATA
        path = write_cog(classes, grid, out_dir / f"{site}_{stack_id}" / f"{day}_water.tif")
        source = {k: str(ds[k].values[t]) for k in ("granule_ur", "crid", "maturity", "pols") if k in ds}
        entries.append({
            "model": "cv", "site": site, "stack": stack_id, "layer": "water", "date": day, "file": _rel(path),
            "classes": CLASSES if three else CLASSES[:2],
            "open_water_ha": round(area_ha(classes == 1), 1),
            "flooded_vegetation_ha": round(area_ha(classes == 2), 1) if three else None,
            "valid_fraction": round(float(seen_t[i].mean()), 3),
            "source": source, "model_file": model_label, "threshold": threshold,
        })
        print(f"  {site} {stack_id} {day}: open water {entries[-1]['open_water_ha']} ha"
              + (f", flooded vegetation {entries[-1]['flooded_vegetation_ha']} ha" if three else ""), flush=True)
        ppath = write_cog(probability_u8(p_any, sea), grid, out_dir / f"{site}_{stack_id}" / f"{day}_water_p.tif",
                          colormap=None)
        entries.append({
            "model": "cv", "site": site, "stack": stack_id, "layer": "water_probability", "date": day,
            "file": _rel(ppath), "units": "round(P(water) x 200), 0 to 200; 255 no data or sea",
            "source": source, "model_file": model_label,
        })
    first, last = water_days(water_t, seen_t, doy, sea)
    period = f"{min(days)}/{max(days)}"
    for name, array in (("first_water_doy", first), ("last_water_doy", last)):
        path = write_cog(array, grid, out_dir / f"{site}_{stack_id}" / f"{name}.tif", colormap=None)
        entries.append({
            "model": "cv", "site": site, "stack": stack_id, "layer": name, "date": period, "file": _rel(path),
            "units": "day of year 2026; 0 never water on a seen date, 65535 never seen or sea",
            "dates_doy": doy.tolist(), "model_file": model_label, "threshold": threshold,
        })
    return entries


def main() -> None:
    from pipeline.ml.export import upsert_manifest

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, nargs="+", help="U-Net checkpoint(s); several = ensemble")
    parser.add_argument("--burn", action="store_true", help="only the Espadà burn layers (no model needed)")
    parser.add_argument("--threshold", type=float, default=0.5, help="water probability threshold")
    parser.add_argument("--sites", nargs="+", default=list(DSWX_LABEL_SITES))
    parser.add_argument("--flooded-veg", action="store_true", help="separate flooded vegetation (three-class models)")
    parser.add_argument("--out-dir", type=Path, default=CV_OUT_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    if args.burn:
        entries = export_burn(out_dir=args.out_dir)
        upsert_manifest(args.manifest, entries, key_fields=KEY_FIELDS)
        print(f"{len(entries)} burn layers -> {_rel(args.out_dir)}, manifest {_rel(args.manifest)}")
        return
    if not args.model:
        parser.error("--model is required unless --burn is given")
    predictor = load_predictor(args.model, args.threshold)
    label = "+".join(p.stem for p in args.model)
    entries = []
    for site in args.sites:
        stacks = STACKS[site] + tuple(s for s in EXTRA_TEST_STACKS.get(site, ())
                                      if (STACK_DIR / f"{site}_{s}.nc").exists())
        for stack_id in stacks:
            entries += export_stack(site, stack_id, predictor, args.threshold, args.out_dir,
                                    flooded_veg=args.flooded_veg, model_label=label)
    # Per-stack layers carry a date range, which changes when a stack gains a date:
    # key them without the date so a rerun replaces them instead of leaving a stale entry.
    upsert_manifest(args.manifest, [e for e in entries if e["layer"] not in PER_STACK_LAYERS], key_fields=KEY_FIELDS)
    upsert_manifest(args.manifest, [e for e in entries if e["layer"] in PER_STACK_LAYERS], key_fields=STACK_KEY_FIELDS)
    print(f"{len(entries)} layers -> {_rel(args.out_dir)}, manifest {_rel(args.manifest)}")


if __name__ == "__main__":
    main()
