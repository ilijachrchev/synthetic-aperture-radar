"""Hidden water: where NISAR's L-band sees water that the Sentinel-1 water map (C-band) does not.

    python -m pipeline.cv.hidden_water                        # every site with built stacks
    python -m pipeline.cv.hidden_water --site albufera ebro

For every acquisition with a same-day DSWx-S1 map at most MAX_GAP_H hours from the
NISAR pass, on land that is neither sea nor permanent water, where both are usable:
- NISAR water: 5x5 filtered HH darker than THRESHOLD_DB (-15 dB, the fixed threshold
  that held on both Albufera tracks in the NISAR check of the prediction model);
- Sentinel-1 water: DSWx-S1 open water or inundated vegetation;
- hidden water: NISAR water where Sentinel-1 says not water, in hectares, split by
  ESA WorldCover class; and the reverse, water only Sentinel-1 sees.
A dark NISAR pixel is a candidate, not proof: smooth bare soil, fresh tarmac and
radar shadow are dark too. That is why the land cover of the hidden water matters,
and why an independent optical water map is the referee before any claim.
Writes data/metrics/cv_hidden_water.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import rasterio

from pipeline.config import CV_LABEL_SITES, site_stacks
from pipeline.cv.baseline import area_ha
from pipeline.cv.evaluate import (
    CONTEXT_DIR, DSWX_INUNDATED_VEG, DSWX_INVALID, DSWX_OPEN_WATER, EXTRA_TEST_STACKS, MAX_GAP_H, METRICS_DIR,
    _built, labelled_dates, scene_db,
)

THRESHOLD_DB = -15.0
WORLDCOVER = {10: "tree", 20: "shrub", 30: "grass", 40: "cropland", 50: "built", 60: "bare", 70: "snow",
              80: "water", 90: "herbaceous wetland", 95: "mangroves", 100: "moss", 0: "no data"}


def compare(nisar: np.ndarray, s1: np.ndarray, scoring: np.ndarray, cover: np.ndarray) -> dict:
    """Hectares of NISAR water, Sentinel-1 water, both, each alone, and the hidden water per land cover."""
    nisar, s1 = nisar & scoring, s1 & scoring
    hidden, s1_only = nisar & ~s1, s1 & ~nisar
    by_class = {WORLDCOVER.get(int(c), str(int(c))): round(area_ha(hidden & (cover == c)), 1)
                for c in np.unique(cover[hidden])}
    return {
        "scored_ha": round(area_ha(scoring), 1),
        "nisar_ha": round(area_ha(nisar), 1),
        "s1_ha": round(area_ha(s1), 1),
        "both_ha": round(area_ha(nisar & s1), 1),
        "hidden_ha": round(area_ha(hidden), 1),
        "s1_only_ha": round(area_ha(s1_only), 1),
        "hidden_by_cover_ha": dict(sorted(by_class.items(), key=lambda kv: -kv[1])),
    }


def site_rows(site: str) -> list[dict]:
    with rasterio.open(CONTEXT_DIR / f"{site}_worldcover_2021_20m.tif") as src:
        cover = src.read(1)
    rows = []
    for stack_id in site_stacks(site) + EXTRA_TEST_STACKS.get(site, ()):
        if not _built(site, stack_id):
            continue
        for ds, day, t, entry, dswx, perm in labelled_dates(site, stack_id):
            if dswx is None:
                continue
            hh_db, ok = scene_db(ds["HH"].values[t], ds["valid"].values[t])
            scoring = ok & ~np.isin(dswx, DSWX_INVALID) & ~perm
            if not scoring.any():
                continue
            nisar = hh_db < THRESHOLD_DB
            s1 = np.isin(dswx, (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG))
            rows.append({"site": site, "stack": stack_id, "date": day, "gap_h": entry["hours_from_nisar"],
                         **compare(nisar, s1, scoring, cover)})
    return rows


def summarize(rows: list[dict]) -> dict:
    """Totals per site and per month: the season matters (young rice in June, harvest in autumn)."""
    out: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        for key in (r["site"], f"{r['site']} {r['date'][:7]}"):
            for k in ("scored_ha", "nisar_ha", "s1_ha", "both_ha", "hidden_ha", "s1_only_ha"):
                out[key][k] += r[k]
            out[key]["dates"] += 1
            for c, ha in r["hidden_by_cover_ha"].items():
                out[key][f"hidden_{c}_ha"] += ha
    return {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in sorted(out.items())}


OPTICAL_WINDOW_DAYS = 3
HLS_NOT_WATER, HLS_OPEN, HLS_PARTIAL, HLS_CLOUD = 0, 1, 2, 253  # OPERA DSWx-HLS B01_WTR classes
HIDDEN_COVERS = (40, 90)  # cropland and herbaceous wetland: where water under crops can hide


def hls_wtr_urls(site, day: str, window: int = OPTICAL_WINDOW_DAYS) -> dict[str, list[str]]:
    """B01_WTR file URLs of OPERA DSWx-HLS granules over the site, grouped by acquisition date."""
    from datetime import date, timedelta

    import earthaccess

    d = date.fromisoformat(day)
    found = earthaccess.search_data(short_name="OPERA_L3_DSWX-HLS_V1", bounding_box=site.bbox,
                                    temporal=((d - timedelta(days=window)).isoformat(),
                                              (d + timedelta(days=window)).isoformat()))
    by_date: dict[str, list[str]] = defaultdict(list)
    for g in found:
        start = g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10]
        by_date[start] += [u for u in g.data_links() if u.endswith("_B01_WTR.tif")]
    return dict(by_date)


def referee(site_name: str, stack_id: str, day: str) -> dict:
    """What an optical water map (OPERA DSWx-HLS, within OPTICAL_WINDOW_DAYS) says about three groups
    of pixels on one NISAR date: hidden water on cropland and wetland, water both radars agree on,
    and land both call dry. The two agreeing groups show how far the optical map can be trusted."""
    import earthaccess

    from pipeline.config import RAW_DIR, get_site
    from pipeline.cv.data import dswx_on_grid

    site = get_site(site_name)
    with rasterio.open(CONTEXT_DIR / f"{site_name}_worldcover_2021_20m.tif") as src:
        cover = src.read(1)
    for ds, d, t, entry, dswx, perm in labelled_dates(site_name, stack_id):
        if d == day:
            break
    else:
        raise ValueError(f"{site_name} {stack_id}: no labelled date {day}")
    hh_db, ok = scene_db(ds["HH"].values[t], ds["valid"].values[t])
    scoring = ok & ~np.isin(dswx, DSWX_INVALID) & ~perm
    nisar, s1 = (hh_db < THRESHOLD_DB) & scoring, np.isin(dswx, (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG)) & scoring
    groups = {"hidden water on cropland and wetland": nisar & ~s1 & np.isin(cover, HIDDEN_COVERS),
              "water both radars see": nisar & s1,
              "land both radars call dry": scoring & ~nisar & ~s1}
    earthaccess.login(strategy="netrc")
    out = {"site": site_name, "stack": stack_id, "nisar_date": day, "optical": []}
    for opt_day, urls in sorted(hls_wtr_urls(site, day).items(),
                                key=lambda kv: abs((np.datetime64(kv[0]) - np.datetime64(day)).astype(int))):
        folder = RAW_DIR / "dswx_hls" / site_name / opt_day.replace("-", "")
        folder.mkdir(parents=True, exist_ok=True)
        todo = [u for u in urls if not (folder / u.rsplit("/", 1)[-1]).exists()]
        if todo:
            earthaccess.download(todo, local_path=str(folder))
        opt = dswx_on_grid(ds, [folder / u.rsplit("/", 1)[-1] for u in urls])
        row = {"optical_date": opt_day, "days_from_nisar": int(abs((np.datetime64(opt_day) - np.datetime64(day))
                                                                  .astype(int))), "tiles": len(urls)}
        for name, mask in groups.items():
            n = int(mask.sum())
            seen = mask & np.isin(opt, (HLS_NOT_WATER, HLS_OPEN, HLS_PARTIAL))
            row[name] = {
                "ha": round(area_ha(mask), 1),
                "cloud_or_no_data": round(1 - float(seen.sum()) / max(n, 1), 3),
                "optical_open_water": round(float((mask & (opt == HLS_OPEN)).sum()) / max(int(seen.sum()), 1), 3),
                "optical_partial_water": round(float((mask & (opt == HLS_PARTIAL)).sum()) / max(int(seen.sum()), 1), 3),
                "optical_not_water": round(float((mask & (opt == HLS_NOT_WATER)).sum()) / max(int(seen.sum()), 1), 3),
            }
        out["optical"].append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", nargs="+", default=list(CV_LABEL_SITES))
    parser.add_argument("--optical", nargs=3, action="append", metavar=("SITE", "STACK", "DATE"),
                        help="check one NISAR date against optical water maps (repeatable)")
    args = parser.parse_args()
    if args.optical:
        results = [referee(site, stack, day) for site, stack, day in args.optical]
        for r in results:
            print(f"\n{r['site']} {r['stack']} NISAR {r['nisar_date']}")
            for o in r["optical"]:
                print(f"  optical {o['optical_date']} ({o['days_from_nisar']} d, {o['tiles']} tiles)")
                for name in ("hidden water on cropland and wetland", "water both radars see", "land both radars call dry"):
                    g = o[name]
                    print(f"    {name:38s} {g['ha']:8.0f} ha | cloud or no data {g['cloud_or_no_data']:.0%} | "
                          f"optical: open {g['optical_open_water']:.0%}, partial {g['optical_partial_water']:.0%}, "
                          f"not water {g['optical_not_water']:.0%}")
        path = METRICS_DIR / "cv_hidden_water_optical.json"
        path.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "window_days": OPTICAL_WINDOW_DAYS, "cases": results}, indent=1), encoding="utf-8")
        print(f"-> {path}")
        return
    rows = [r for site in args.site for r in site_rows(site)]
    summary = summarize(rows)
    print(f"{'site and stack':28s} {'date':10s} {'S1 ha':>8s} {'NISAR ha':>9s} {'hidden ha':>10s} {'S1 only ha':>11s}  hidden by land cover")
    for r in rows:
        top = ", ".join(f"{c} {ha:.0f}" for c, ha in list(r["hidden_by_cover_ha"].items())[:3])
        print(f"{r['site'] + ' ' + r['stack']:28s} {r['date']:10s} {r['s1_ha']:8.0f} {r['nisar_ha']:9.0f} "
              f"{r['hidden_ha']:10.0f} {r['s1_only_ha']:11.0f}  {top}")
    path = METRICS_DIR / "cv_hidden_water.json"
    path.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "threshold_db": THRESHOLD_DB, "max_gap_h": MAX_GAP_H, "rows": rows,
                                "summary": summary}, indent=1), encoding="utf-8")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
