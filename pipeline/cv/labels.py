"""NISAR water labels per pass at Albufera and Pego-Oliva: the input labels for the "where will the
water go" model (discussion #29) and map layers for the app.

    python -m pipeline.cv.labels                        # both sites: the GeoTIFFs and the summary
    python -m pipeline.cv.labels --site pego_oliva
    python -m pipeline.cv.labels --export               # also the per-pixel table, one parquet per site
    python -m pipeline.cv.labels --export --no-build    # only the table, from the GeoTIFFs on disk
    python -m pipeline.cv.labels --fetch-municipalities # refresh data/labels/<site>_municipalities_osm.geojson

Every NISAR pass with HV of the site's stacks (Albufera 066_D_069 and 058_A_021; Pego-Oliva the same
two plus the partial frame 167_D_069), on the 20 m stack grid (pipeline.stack.site_grid, EPSG:32630).
Three uint8 GeoTIFFs per pass in data/labels_nisar/<site>_<stack>/:

<date>_class.tif
    0 not water, 1 open water, 2 water under plants (possible, not validated), 3 not assessed
    (built-up), 255 no data (NISAR not usable on the date) or sea (data/context/<site>_sea_20m.tif).
    - Open water: the v1 U-Net ensemble of docs/CV_RESULTS.md at its pre-registered threshold,
      p(open water) >= 0.3, read from the probability cache data/interim/cv_prob/v1 (written by
      python -m pipeline.cv.benchmark_optical --cache v1); no model runs here.
    - Water under plants is a CANDIDATE rule, not validated: none of our sources can see water
      under plants (optical cannot, and Sentinel-1's map is not ground truth). On vegetated land
      (ESA WorldCover 10 tree, 20 shrub, 30 grass, 40 crop, 90 herbaceous wetland) that is not
      open water: the 5x5 filtered HH is at least 3 dB above the pixel's median over the stack,
      while the 5x5 filtered HV stays within 1.5 dB of its median (water under stems raises HH by
      double bounce and leaves HV about flat).
    - Not assessed: ESA WorldCover 50 (built-up). At 20 m the radar cannot see water between
      buildings: in the optical benchmark the "other" land type (trees, built-up and the rest)
      scores an IoU below 0.05 for every radar method (data/metrics/cv_optical_benchmark.json).
    No data wins over every class, then not assessed, then open water, then water under plants.

<date>_confidence.tif
    0 to 100 on classes 0, 1 and 2, 255 elsewhere: the share of the available checks that agree
    with the class, rounded to steps of 5. A vote with equal weights, not a calibrated probability.
    Classes 0 and 1, each check scores 1 (agrees) or 0 (contradicts), or is left out:
    - the model, always: 0.5 + 0.5 x how far p(open water) lies from 0.3 on the class's side
      (0.5 at the threshold, 1 at p = 1 for open water or at p = 0 for not water);
    - darkness, where the 5x5 filtered HH is usable: below -15 dB says water;
    - coherence, where a GUNW pair describes the date (pipeline.cv.coherence.coherence_for):
      below 0.25, the cut chosen on the training sites (data/metrics/cv_optical_select.json), says
      water, 0.25 or more says not water;
    - optical, where the OPERA DSWx-HLS map within 1 day (data/optical) is clear: open water says
      water, not water says not water; partial water, cloud and the rest are left out.
    Class 2: darkness, coherence and optical cannot see water under plants (it is bright, not dark,
    its double bounce can stay coherent, and optical sees the canopy), so only the model's
    p(open water or inundated vegetation) checks it, against 0.3 as above, and the value is
    capped at 50.

<date>_s1.tif
    Only for passes with an OPERA DSWx-S1 map at most 2 h from the NISAR pass
    (pipeline.cv.evaluate.labelled_dates), a second label source in the same codes: 0 not water,
    1 open water, 2 inundated vegetation (DSWx class 3), 3 not assessed (built-up, as above),
    255 masked, fill, outside the map or sea.

data/metrics/nisar_labels_summary.json: hectares per class per pass, the share of the labelled
pixels that an optical or a coherence check covers and how often those checks agree, Sentinel-1 next
to NISAR, and what was still flooded after the DANA "Adam" rain of 18 to 19 Oct 2026 (16 to 28 Oct on
066 D and 058 A, 11 to 23 Oct on 167 D) in hectares, per site and per municipality (OpenStreetMap
boundaries with their INE codes, data/labels/<site>_municipalities_osm.geojson).

--export writes one parquet per site to data/interim/nisar-labels/ (gitignored): the table asked for
in discussion #29, one row per pixel and pass whose class is not 255, with x and y (pixel centre,
EPSG:32630 metres), row, col, date, track (the stack, track_direction_frame), label (the class),
confidence (255 on class 3), s1_label (255 without a same-pass map), split ("test" from 15 Oct to
15 Nov 2026, the DANA window, else "train") and permanent_water (WorldCover water or JRC occurrence
of 90 % or more, as in pipeline.cv.evaluate).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize

from pipeline.config import DATA_DIR, STACK_DIR, get_site
from pipeline.cv.baseline import PIXEL_HA
from pipeline.cv.benchmark_optical import CACHE_DIR, DARK_DB, V1_THRESHOLD, hv_dates, load_cached, stacks_of
from pipeline.cv.coherence import coherence_for, coherence_path
from pipeline.cv.data import open_stack
from pipeline.cv.dataset import OPTICAL_NOT_WATER, OPTICAL_OPEN_WATER, nan_quantile0, optical_classes
from pipeline.cv.evaluate import (
    CONTEXT_DIR, DSWX_INUNDATED_VEG, DSWX_OPEN_WATER, LABELS_DIR, METRICS_DIR, labelled_dates, scene_db,
    site_permanent_water,
)
from pipeline.stack import Grid, site_grid

SITES = ("albufera", "pego_oliva")
OUT_DIR = DATA_DIR / "labels_nisar"
SUMMARY_PATH = METRICS_DIR / "nisar_labels_summary.json"
EXPORT_DIR = DATA_DIR / "interim" / "nisar-labels"

NOT_WATER, OPEN_WATER, UNDER_PLANTS, NOT_ASSESSED, NO_DATA = 0, 1, 2, 3, 255
LABELLED = (NOT_WATER, OPEN_WATER, UNDER_PLANTS)
CLASS_NAMES = {NOT_WATER: "not_water", OPEN_WATER: "open_water", UNDER_PLANTS: "water_under_plants",
               NOT_ASSESSED: "not_assessed_built"}
OPEN_THRESHOLD = V1_THRESHOLD      # 0.3, pre-registered in docs/CV_RESULTS.md
COH_CUT = 0.25                     # data/metrics/cv_optical_select.json, chosen on the training sites
HH_RISE_DB, HV_FLAT_DB = 3.0, 1.5  # the water-under-plants candidate rule
VEGETATED = (10, 20, 30, 40, 90)   # ESA WorldCover tree, shrub, grass, crop, herbaceous wetland
BUILT = 50                         # ESA WorldCover built-up
DSWX_NOT_WATER = 0
UNDER_PLANTS_CAP = 50
CONF_STEP = 5
TEST_WINDOW = ("2026-10-15", "2026-11-15")  # the DANA window, held out of training (discussion #29)
# Before and after the DANA "Adam" rain (18 to 19 Oct 2026) on each stack's own track.
DANA = {"066_D_069": ("2026-10-16", "2026-10-28"), "058_A_021": ("2026-10-16", "2026-10-28"),
        "167_D_069": ("2026-10-11", "2026-10-23")}

CLASS_LEGEND = ("0 not water, 1 open water, 2 water under plants (possible, not validated), "
                "3 not assessed (built-up), 255 no data or sea")
RULES = {
    "open_water": f"v1 U-Net ensemble p(open water) >= {OPEN_THRESHOLD} (pre-registered, docs/CV_RESULTS.md)",
    "water_under_plants": (f"candidate rule, not validated: vegetated WorldCover land, 5x5 filtered HH at least "
                           f"{HH_RISE_DB} dB above its stack median and HV within {HV_FLAT_DB} dB of its median"),
    "not_assessed": "ESA WorldCover 50 built-up: the radar cannot see water between buildings at 20 m",
    "confidence": (f"share of agreeing checks, steps of {CONF_STEP}: model margin to {OPEN_THRESHOLD}; HH below "
                   f"{DARK_DB} dB; coherence below {COH_CUT}; clear optical DSWx-HLS within 1 day. Class 2: "
                   f"the model's p(any water) only, capped at {UNDER_PLANTS_CAP}"),
    "s1": "OPERA DSWx-S1 at most 2 h from the pass: 0 not water, 1 open water, 2 inundated vegetation, 3 built-up",
}
SI_NOTE = "Written with SI assistance (Claude Code), reviewed by the team."


def hectares(mask: np.ndarray) -> float:
    """Area in hectares, exact: a whole number of 0.04 ha pixels."""
    return round(float(np.count_nonzero(mask)) * PIXEL_HA, 2)


def share(part: np.ndarray, whole: np.ndarray) -> float | None:
    n = np.count_nonzero(whole)
    return round(float(np.count_nonzero(part & whole)) / n, 4) if n else None


def split_of(day: str) -> str:
    return "test" if TEST_WINDOW[0] <= day <= TEST_WINDOW[1] else "train"


# ---------------------------------------------------------------- the rules, on plain arrays

def under_plants(hh_db: np.ndarray, hv_db: np.ndarray, hh_median: np.ndarray, hv_median: np.ndarray,
                 cover: np.ndarray) -> np.ndarray:
    """Candidate water under plants (not validated): vegetated land, HH at least HH_RISE_DB above its
    stack median while HV stays within HV_FLAT_DB of its median. NaN anywhere means no."""
    rise = hh_db - hh_median
    flat = np.abs(hv_db - hv_median)
    return np.isin(cover, VEGETATED) & (rise >= HH_RISE_DB) & (flat <= HV_FLAT_DB)


def classify(p_open: np.ndarray, plants: np.ndarray, cover: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """Class per pixel from p(open water) (NaN where NISAR is not usable), the under-plants
    candidates, the land cover and the sea mask. No data > not assessed > open water > under plants."""
    usable = np.isfinite(p_open) & ~sea
    out = np.full(p_open.shape, NO_DATA, dtype="uint8")
    out[usable] = NOT_WATER
    out[usable & plants] = UNDER_PLANTS
    out[usable & (np.nan_to_num(p_open, nan=0.0) >= OPEN_THRESHOLD)] = OPEN_WATER
    out[usable & (cover == BUILT)] = NOT_ASSESSED
    return out


def agreement(p: np.ndarray, water: np.ndarray | bool, threshold: float = OPEN_THRESHOLD) -> np.ndarray:
    """How much a probability backs a class: 0.5 at the threshold, 1 at p = 1 for water (or at p = 0
    for not water), 0 at the other end, linear in between. NaN counts as the threshold."""
    p = np.clip(np.nan_to_num(np.asarray(p, dtype="float64"), nan=threshold), 0.0, 1.0)
    towards_water = np.where(p >= threshold, (p - threshold) / (1.0 - threshold), (p - threshold) / threshold)
    return 0.5 + 0.5 * np.where(water, towards_water, -towards_water)


def confidence(cls: np.ndarray, p_open: np.ndarray, p_any: np.ndarray, hh_db: np.ndarray, coh: np.ndarray,
               optical: np.ndarray | None) -> np.ndarray:
    """0 to 100 on classes 0, 1 and 2 (255 elsewhere): the share of the available checks that agree.

    hh_db: 5x5 filtered HH (NaN where not usable); coh: coherence (NaN where no pair); optical: the
    DSWx-HLS classes of the date or None. See the module docstring for the rule."""
    water = cls == OPEN_WATER
    score = agreement(p_open, water)
    count = np.ones(cls.shape, dtype="float64")
    checks = [(np.isfinite(hh_db), hh_db < DARK_DB), (np.isfinite(coh), coh < COH_CUT)]
    if optical is not None:
        checks.append((np.isin(optical, (OPTICAL_NOT_WATER, OPTICAL_OPEN_WATER)), optical == OPTICAL_OPEN_WATER))
    for available, says_water in checks:
        score += np.where(available, says_water == water, 0)
        count += available
    value = score / count
    plants = cls == UNDER_PLANTS
    value = np.where(plants, agreement(p_any, True) * UNDER_PLANTS_CAP / 100.0, value)
    out = np.full(cls.shape, NO_DATA, dtype="uint8")
    stepped = CONF_STEP * np.floor(100.0 * value / CONF_STEP + 0.5)
    keep = np.isin(cls, LABELLED)
    out[keep] = stepped[keep].astype("uint8")
    return out


def s1_classes(dswx: np.ndarray, cover: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """DSWx-S1 classes in the codes of the class layer (built-up not assessed, sea no data)."""
    out = np.full(dswx.shape, NO_DATA, dtype="uint8")
    out[dswx == DSWX_NOT_WATER] = NOT_WATER
    out[dswx == DSWX_OPEN_WATER] = OPEN_WATER
    out[dswx == DSWX_INUNDATED_VEG] = UNDER_PLANTS
    out[(out != NO_DATA) & (cover == BUILT)] = NOT_ASSESSED
    out[sea] = NO_DATA
    return out


def change(before: np.ndarray, after: np.ndarray, permanent: np.ndarray) -> dict:
    """Hectares of water before and after, new, on both and gone, on pixels labelled on both dates
    that are not permanent water; for open water and for open water or water under plants."""
    ok = np.isin(before, LABELLED) & np.isin(after, LABELLED) & ~permanent
    out: dict = {"compared_ha": hectares(ok)}
    for name, classes in (("open_water", (OPEN_WATER,)), ("open_water_or_under_plants", (OPEN_WATER, UNDER_PLANTS))):
        b, a = np.isin(before, classes) & ok, np.isin(after, classes) & ok
        out[name] = {"before_ha": hectares(b), "after_ha": hectares(a), "new_ha": hectares(a & ~b),
                     "on_both_ha": hectares(a & b), "gone_ha": hectares(b & ~a)}
    return out


def pass_summary(cls: np.ndarray, conf: np.ndarray, p_any: np.ndarray, coh: np.ndarray, optical: np.ndarray | None,
                 permanent: np.ndarray, sea: np.ndarray, s1: np.ndarray | None) -> dict:
    """Hectares per class, mean confidence, and how much the optical and coherence checks cover and agree."""
    labelled = np.isin(cls, LABELLED)
    changing_open = (cls == OPEN_WATER) & ~permanent
    has_coh = np.isfinite(coh)
    clear = np.zeros(cls.shape, bool) if optical is None else np.isin(optical, (OPTICAL_NOT_WATER, OPTICAL_OPEN_WATER))
    seen_open = clear & (optical == OPTICAL_OPEN_WATER) if optical is not None else clear
    out = {
        "hectares": {**{name: hectares(cls == c) for c, name in CLASS_NAMES.items()},
                     "open_water_on_permanent_water": hectares((cls == OPEN_WATER) & permanent),
                     "no_data_on_land": hectares((cls == NO_DATA) & ~sea),
                     "not_water_where_the_model_sees_inundated_vegetation":
                         hectares((cls == NOT_WATER) & (np.nan_to_num(p_any, nan=0.0) >= OPEN_THRESHOLD))},
        "mean_confidence": {CLASS_NAMES[c]: (round(float(conf[cls == c].mean()), 1) if (cls == c).any() else None)
                            for c in LABELLED},
        "checks": {
            "share_with_optical": share(clear, labelled),
            "share_with_coherence": share(has_coh, labelled),
            "share_with_optical_or_coherence": share(clear | has_coh, labelled),
            "changing_open_water_confirmed_by_optical": share(seen_open, changing_open & clear),
            "not_water_where_optical_sees_open_water": share(seen_open, (cls == NOT_WATER) & clear),
            "changing_open_water_with_low_coherence": share(coh < COH_CUT, changing_open & has_coh),
        },
    }
    if s1 is not None:
        both = np.isin(cls, LABELLED) & np.isin(s1, LABELLED) & ~permanent
        n_open, s_open = (cls == OPEN_WATER) & both, (s1 == OPEN_WATER) & both
        out["sentinel1"] = {
            "hectares": {name: hectares(s1 == c) for c, name in
                         ((0, "not_water"), (1, "open_water"), (2, "inundated_vegetation"), (3, "not_assessed_built"))},
            "changing_open_water_compared": {"compared_ha": hectares(both), "both_ha": hectares(n_open & s_open),
                                             "nisar_only_ha": hectares(n_open & ~s_open),
                                             "sentinel1_only_ha": hectares(s_open & ~n_open)},
        }
    return out


# ---------------------------------------------------------------- files

def read_band(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1)


def write_layer(path: Path, array: np.ndarray, grid: Grid, description: str, tags: dict) -> None:
    """A compressed uint8 GeoTIFF on the site grid, 255 = no data; written to a .part file first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".part.tif")
    with rasterio.open(tmp, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="uint8",
                       crs=grid.crs, transform=grid.transform, nodata=NO_DATA, compress="deflate", zlevel=9,
                       predictor=2, tiled=True, blockxsize=256, blockysize=256) as dst:
        dst.write(array, 1)
        dst.set_band_description(1, description)
        dst.update_tags(**{k: str(v) for k, v in tags.items()})
    tmp.replace(path)


def layer_paths(site: str, stack_id: str, day: str) -> dict[str, Path]:
    folder = OUT_DIR / f"{site}_{stack_id}"
    return {k: folder / f"{day}_{k}.tif" for k in ("class", "confidence", "s1")}


def stack_medians(ds) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel median of the 5x5 filtered HH and HV (dB) over the stack's usable dates."""
    out = []
    for pol in ("HH", "HV"):
        layers = np.stack([scene_db(ds[pol].values[t], ds["valid"].values[t])[0] for t in range(ds.sizes["time"])])
        out.append(nan_quantile0(layers, 0.5))
        del layers
    return out[0], out[1]


def context(site: str) -> tuple[Grid, np.ndarray, np.ndarray, np.ndarray]:
    """Site grid, WorldCover classes, sea mask and permanent water, all on the 20 m grid."""
    grid = site_grid(get_site(site))
    cover = read_band(CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif")
    sea = read_band(CONTEXT_DIR / f"{site}_sea_20m.tif") == 1
    if cover.shape != (grid.height, grid.width) or sea.shape != cover.shape:
        raise ValueError(f"{site}: the context layers are not on the site grid; rerun python -m pipeline.context")
    return grid, cover, sea, site_permanent_water(site)


# ---------------------------------------------------------------- one site

def build_stack(site: str, stack_id: str, grid: Grid, cover: np.ndarray, sea: np.ndarray,
                permanent: np.ndarray) -> tuple[list[dict], dict[str, np.ndarray]]:
    """Write the three layers of every pass with HV of one stack; return the pass summaries and the
    class maps of its DANA dates."""
    # Sentinel-1 first: labelled_dates opens the stack itself, so only one copy is in memory at a time.
    s1_maps = {day: (dswx, entry["hours_from_nisar"]) for _, day, _, entry, dswx, _ in labelled_dates(site, stack_id)
               if dswx is not None}
    ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
    if (not ds["HH"].rio.transform().almost_equals(grid.transform)
            or (ds.sizes["y"], ds.sizes["x"]) != (grid.height, grid.width)):
        raise ValueError(f"{site} {stack_id}: the stack is not on the site grid")
    medians = stack_medians(ds)
    summaries, dana_maps = [], {}
    for day, t in hv_dates(ds).items():
        cached = load_cached("v1", site, stack_id, day)
        if cached is None:
            raise SystemExit(f"no cached v1 probabilities for {site} {stack_id} {day}: "
                             "run python -m pipeline.cv.benchmark_optical --cache v1")
        p_open, p_any = cached
        hh_db, _ = scene_db(ds["HH"].values[t], ds["valid"].values[t])
        hv_db, _ = scene_db(ds["HV"].values[t], ds["valid"].values[t])
        cls = classify(p_open, under_plants(hh_db, hv_db, *medians, cover), cover, sea)
        coh = coherence_for(site, stack_id, day, cls.shape)
        optical = optical_classes(site, stack_id, day)
        conf = confidence(cls, p_open, p_any, hh_db, coh, optical)
        s1_entry = s1_maps.get(day)
        s1 = s1_classes(s1_entry[0], cover, sea) if s1_entry is not None else None

        paths = layer_paths(site, stack_id, day)
        tags = {"site": site, "stack": stack_id, "date": day, "note": SI_NOTE}
        write_layer(paths["class"], cls, grid, "NISAR water class",
                    {**tags, "classes": CLASS_LEGEND, "open_water": RULES["open_water"],
                     "water_under_plants": RULES["water_under_plants"], "not_assessed": RULES["not_assessed"]})
        write_layer(paths["confidence"], conf, grid, "confidence 0 to 100",
                    {**tags, "confidence": RULES["confidence"]})
        if s1 is not None:
            write_layer(paths["s1"], s1, grid, "Sentinel-1 DSWx-S1 water class",
                        {**tags, "classes": CLASS_LEGEND, "s1": RULES["s1"],
                         "hours_from_nisar": s1_entry[1]})
        elif paths["s1"].exists():
            paths["s1"].unlink()  # a same-pass map that is no longer in the index

        pair = coherence_path(site, stack_id, day)
        summaries.append({
            "site": site, "stack": stack_id, "date": day, "split": split_of(day),
            "maturity": str(ds["maturity"].values[t]), "crid": str(ds["crid"].values[t]),
            "coherence_pair": pair.stem if pair is not None else None,
            "sentinel1_hours_from_nisar": s1_entry[1] if s1_entry is not None else None,
            **pass_summary(cls, conf, p_any, coh, optical, permanent, sea, s1),
        })
        if day in DANA.get(stack_id, ()):
            dana_maps[day] = cls
        print(f"  {site} {stack_id} {day}: open water {summaries[-1]['hectares']['open_water']} ha, "
              f"under plants {summaries[-1]['hectares']['water_under_plants']} ha", flush=True)
    return summaries, dana_maps


def emsr935_flooded(grid: Grid) -> np.ndarray:
    """The EMSR935 flooded_area outline (imagery 20 to 21 Oct 2026) on the site grid."""
    import geopandas as gpd

    outlines = gpd.read_file(LABELS_DIR / "pego_oliva_emsr935_flood.geojson")
    geoms = [g for g in outlines[outlines["class"] == "flooded_area"].to_crs(grid.crs).geometry
             if g is not None and not g.is_empty]
    return rasterize(((g, 1) for g in geoms), out_shape=(grid.height, grid.width), transform=grid.transform,
                     fill=0, dtype="uint8").astype(bool)


def dana_summary(site: str, maps: dict[str, dict[str, np.ndarray]], grid: Grid, permanent: np.ndarray) -> dict:
    """Still flooded after the DANA: each stack's before and after pass on its own track; at
    Pego-Oliva also the EMSR935 flooded area still seen as water, and the 23 Oct water (167 D) still
    water on 28 Oct (066 D, 058 A), which mixes two viewing geometries and is descriptive only."""
    out: dict = {"rain": "DANA Adam, 18 to 19 Oct 2026 (pipeline/prediction/flood)",
                 "region": "land labelled on both dates (not sea, not built-up, not no data), not permanent water",
                 "stacks": {}}
    towns = municipality_ids(site, grid)
    for stack_id, (before, after) in DANA.items():
        m = maps.get(stack_id, {})
        if before in m and after in m:
            out["stacks"][stack_id] = {"before": before, "after": after, **change(m[before], m[after], permanent)}
            if towns is not None:
                out["stacks"][stack_id]["per_municipality"] = per_municipality(m[before], m[after], permanent, *towns)
    if towns is not None:
        out["municipalities"] = (f"{municipalities_path(site).relative_to(DATA_DIR.parent).as_posix()}: "
                                 "OpenStreetMap admin_level 8 with INE codes, (c) OpenStreetMap contributors, "
                                 "ODbL 1.0; built-up land is not assessed, so a town's numbers cover its fields only")
    if site != "pego_oliva":
        return out
    flooded = emsr935_flooded(grid) & ~permanent
    out["emsr935_flooded_area_still_water"] = {
        "outline": "EMSR935 flooded_area, imagery 20 to 21 Oct 2026, not permanent water",
        "outline_ha": hectares(flooded), "per_pass": {}}
    for stack_id, (_, after) in DANA.items():
        cls = maps.get(stack_id, {}).get(after)
        if cls is None:
            continue
        seen = flooded & np.isin(cls, LABELLED)
        out["emsr935_flooded_area_still_water"]["per_pass"][f"{stack_id} {after}"] = {
            "seen_ha": hectares(seen), "open_water_ha": hectares(seen & (cls == OPEN_WATER)),
            "open_water_or_under_plants_ha": hectares(seen & np.isin(cls, (OPEN_WATER, UNDER_PLANTS))),
            "open_water_share": share(cls == OPEN_WATER, seen)}
    first = maps.get("167_D_069", {}).get("2026-10-23")
    if first is not None:
        cross = {}
        for stack_id in ("066_D_069", "058_A_021"):
            last = maps.get(stack_id, {}).get("2026-10-28")
            if last is None:
                continue
            ok = np.isin(first, LABELLED) & np.isin(last, LABELLED) & ~permanent
            w23 = ok & (first == OPEN_WATER)
            cross[f"{stack_id} 2026-10-28"] = {"compared_ha": hectares(ok), "open_water_23_oct_ha": hectares(w23),
                                               "still_open_water_28_oct_ha": hectares(w23 & (last == OPEN_WATER)),
                                               "still_share": share(last == OPEN_WATER, w23)}
        out["open_water_23_oct_still_there_28_oct"] = {
            "note": "167 D on 23 Oct against another track on 28 Oct: two viewing geometries, descriptive only",
            "per_pass": cross}
    return out


OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def municipalities_path(site: str) -> Path:
    return LABELS_DIR / f"{site}_municipalities_osm.geojson"


def _polygons(members: list[dict], roles: tuple[str, ...]):
    """The union of the closed rings formed by a relation's member ways of these roles."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in members
             if m.get("type") == "way" and m.get("role", "") in roles and len(m.get("geometry") or []) >= 2]
    return unary_union(list(polygonize(lines)))


def fetch_municipalities(site: str) -> Path:
    """Municipal boundaries (OpenStreetMap admin_level 8, with their INE code) that touch the site box,
    from the Overpass API, to data/labels/<site>_municipalities_osm.geojson. (c) OpenStreetMap
    contributors, ODbL 1.0."""
    import geopandas as gpd
    import requests

    west, south, east, north = get_site(site).bbox
    query = (f'[out:json][timeout:120];relation["boundary"="administrative"]["admin_level"="8"]'
             f'({south},{west},{north},{east});out geom;')
    import time

    for attempt, url in enumerate(OVERPASS_URLS * 2):  # the public servers are often busy (502, 504)
        try:
            resp = requests.post(url, data={"data": query}, headers={"User-Agent": "sar-pipeline/0.1"}, timeout=180)
            resp.raise_for_status()
            elements = resp.json()["elements"]
            break
        except (requests.RequestException, ValueError) as ex:
            print(f"   {url}: {ex!r}, trying again", flush=True)
            time.sleep(10 * (attempt + 1))
    else:
        raise SystemExit("the Overpass API did not answer; try again later")
    rows = []
    for rel in elements:
        shape = _polygons(rel["members"], ("outer", "")).difference(_polygons(rel["members"], ("inner",)))
        if not shape.is_empty:
            tags = rel.get("tags", {})
            # OSM keeps the 11-digit INE code of the municipality's entity (46235000000); its first
            # 5 digits are the municipality code (46235, Sueca).
            code = tags.get("ref:ine") or tags.get("ine:municipio") or ""
            rows.append({"name": tags.get("name"), "ine": code[:5] or None,
                         "osm_relation": rel["id"], "geometry": shape.simplify(0.00005)})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").sort_values("name")
    path = municipalities_path(site)
    gdf.to_file(path, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": "6", "RFC7946": "YES"})
    print(f"-> {path}: {len(gdf)} municipalities")
    return path


def municipality_ids(site: str, grid: Grid) -> tuple[np.ndarray, list[dict]] | None:
    """Index of the municipality of each pixel (-1 outside every one) and their names, or None
    when the boundary file is missing."""
    import geopandas as gpd

    path = municipalities_path(site)
    if not path.exists():
        return None
    gdf = gpd.read_file(path).to_crs(grid.crs)
    ids = rasterize(((g, i) for i, g in enumerate(gdf.geometry) if g is not None and not g.is_empty),
                    out_shape=(grid.height, grid.width), transform=grid.transform, fill=-1, dtype="int32")
    return ids, [{"name": n, "ine": c} for n, c in zip(gdf["name"], gdf["ine"])]


def per_municipality(before: np.ndarray, after: np.ndarray, permanent: np.ndarray, ids: np.ndarray,
                     names: list[dict]) -> list[dict]:
    """change() per municipality (open water and open water or under plants), largest new water first."""
    ok = np.isin(before, LABELLED) & np.isin(after, LABELLED) & ~permanent & (ids >= 0)
    n = len(names)

    def count(mask: np.ndarray) -> np.ndarray:
        return np.bincount(ids[mask & ok], minlength=n) * PIXEL_HA

    compared = count(ok)
    parts = {}
    for name, classes in (("open_water", (OPEN_WATER,)), ("open_water_or_under_plants", (OPEN_WATER, UNDER_PLANTS))):
        b, a = np.isin(before, classes), np.isin(after, classes)
        parts[name] = {"before_ha": count(b), "after_ha": count(a), "new_ha": count(a & ~b)}
    out = [{**names[i], "compared_ha": round(float(compared[i]), 2),
            **{k: {kk: round(float(v[i]), 2) for kk, v in d.items()} for k, d in parts.items()}}
           for i in range(n) if compared[i] > 0]
    return sorted(out, key=lambda r: -r["open_water"]["new_ha"])


def cache_provenance() -> dict | None:
    path = CACHE_DIR / "v1" / "manifest.json"
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {"created_utc": manifest.get("created_utc"),
            "models": [{"path": Path(m["path"]).name, "sha256": m["sha256"], "epoch": m.get("epoch")}
                       for m in manifest.get("models", [])]}


def build_site(site: str) -> dict:
    grid, cover, sea, permanent = context(site)
    passes, maps = [], {}
    for stack_id in stacks_of(site):
        print(f"{site} {stack_id}", flush=True)
        rows, dana_maps = build_stack(site, stack_id, grid, cover, sea, permanent)
        passes += rows
        maps[stack_id] = dana_maps
    return {"stacks": stacks_of(site), "pass_count": len(passes), "land_ha": hectares(~sea),
            "permanent_water_ha": hectares(permanent & ~sea),
            "built_up_ha": hectares((cover == BUILT) & ~sea), "passes": passes,
            "dana": dana_summary(site, maps, grid, permanent)}


def save_summary(results: dict[str, dict]) -> None:
    """Merge the sites just built into the summary file (another site's entry is kept)."""
    old = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else {}
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "module": "pipeline/cv/labels.py", "grid": "pipeline.stack.site_grid, EPSG:32630, 20 m (0.04 ha)",
               "classes": CLASS_LEGEND, "rules": RULES, "test_window": list(TEST_WINDOW),
               "v1_probability_cache": cache_provenance(), "note": SI_NOTE,
               "sites": {**old.get("sites", {}), **results}}
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"-> {SUMMARY_PATH}")


# ---------------------------------------------------------------- the per-pixel table

def export_site(site: str, out_dir: Path = EXPORT_DIR) -> Path:
    """One parquet per site from the GeoTIFFs on disk: one row per pixel and pass with a class."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    grid = site_grid(get_site(site))
    permanent = site_permanent_water(site)
    xs, ys = grid.x, grid.y
    schema = pa.schema([("x", pa.float64()), ("y", pa.float64()), ("row", pa.int16()), ("col", pa.int16()),
                        ("date", pa.string()), ("track", pa.string()), ("label", pa.uint8()),
                        ("confidence", pa.uint8()), ("s1_label", pa.uint8()), ("split", pa.string()),
                        ("permanent_water", pa.bool_())])
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{site}_nisar_labels.parquet"
    tmp = path.with_name(path.stem + ".part.parquet")
    rows = 0
    # The label folders, not the stacks: the table can be rebuilt from the committed GeoTIFFs alone.
    stack_ids = [f.name[len(site) + 1:] for f in sorted(OUT_DIR.glob(f"{site}_*")) if f.is_dir()]
    if not stack_ids:
        raise SystemExit(f"no labels in {OUT_DIR} for {site}: run python -m pipeline.cv.labels --site {site}")
    with pq.ParquetWriter(tmp, schema, compression="zstd") as writer:
        for stack_id in stack_ids:
            for class_path in sorted((OUT_DIR / f"{site}_{stack_id}").glob("*_class.tif")):
                day = class_path.name[:10]
                paths = layer_paths(site, stack_id, day)
                cls = read_band(paths["class"])
                if cls.shape != (grid.height, grid.width):
                    raise ValueError(f"{class_path} is not on the site grid")
                conf = read_band(paths["confidence"])
                s1 = read_band(paths["s1"]) if paths["s1"].exists() else np.full(cls.shape, NO_DATA, "uint8")
                r, c = np.nonzero(cls != NO_DATA)
                n = r.size
                writer.write_table(pa.table({
                    "x": xs[c], "y": ys[r], "row": r.astype("int16"), "col": c.astype("int16"),
                    "date": pa.array([day] * n, pa.string()), "track": pa.array([stack_id] * n, pa.string()),
                    "label": cls[r, c], "confidence": conf[r, c], "s1_label": s1[r, c],
                    "split": pa.array([split_of(day)] * n, pa.string()), "permanent_water": permanent[r, c],
                }, schema=schema))
                rows += n
    tmp.replace(path)
    print(f"-> {path}: {rows} rows, {path.stat().st_size / 1e6:.1f} MB", flush=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", nargs="+", default=list(SITES), choices=list(SITES))
    parser.add_argument("--export", action="store_true", help="also write one parquet per site (gitignored)")
    parser.add_argument("--no-build", action="store_true", help="skip the GeoTIFFs and the summary")
    parser.add_argument("--out", type=Path, default=EXPORT_DIR, help="folder of the parquet files")
    parser.add_argument("--fetch-municipalities", action="store_true",
                        help="download the municipal boundaries (OpenStreetMap, Overpass API) to data/labels first")
    args = parser.parse_args()
    if args.fetch_municipalities:
        for site in args.site:
            fetch_municipalities(site)
    if not args.no_build:
        for site in args.site:  # one site at a time: one stack in memory, and a finished site is saved
            save_summary({site: build_site(site)})
    if args.export:
        for site in args.site:
            export_site(site, args.out)


if __name__ == "__main__":
    main()
