"""Data quality of the CV training and test data, per site and stack (the dataset table).

    python -m pipeline.cv.quality                    # every site with same-day water maps
    python -m pipeline.cv.quality --site ebro donana

For every stack: dates, dates with HV, dates with a same-day DSWx-S1 map at most
MAX_GAP_H hours from the NISAR pass (the labelled scenes), and per labelled date:
- valid: share of the site grid where NISAR is usable;
- label_invalid: share of those pixels the water map leaves out (250, 251, 255);
- open, inundated_veg: share of scored pixels in each water class;
- changing_ha: open water outside the sea and permanent water, the class the
  models are scored on, in hectares;
- built_hh_db, built_hv_db: median backscatter over built-up land (WorldCover 50),
  which barely changes, so a jump between dates or tracks flags a calibration step;
- permanent_seen_as_water: share of permanent inland water (JRC 90 % or more, not
  sea) that the map calls water; a low value means the label misses easy water.
Writes data/metrics/cv_data_quality.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np
import rasterio

from pipeline.config import CV_LABEL_SITES, site_stacks
from pipeline.cv.baseline import area_ha
from pipeline.cv.data import to_db
from pipeline.cv.evaluate import (
    CONTEXT_DIR, DSWX_INUNDATED_VEG, DSWX_INVALID, DSWX_OPEN_WATER, EXTRA_TEST_STACKS, MAX_GAP_H, METRICS_DIR,
    _built, labelled_dates,
)

WORLDCOVER_BUILT = 50


def _read(site: str, name: str) -> np.ndarray:
    with rasterio.open(CONTEXT_DIR / f"{site}_{name}_20m.tif") as src:
        return src.read(1)


def stack_quality(site: str, stack_id: str) -> dict:
    built = _read(site, "worldcover_2021") == WORLDCOVER_BUILT
    sea = _read(site, "sea").astype(bool)
    occurrence = _read(site, "jrc_occurrence")
    inland_permanent = (occurrence >= 90) & (occurrence != 255) & ~sea
    rows, n_dates, n_hv = [], 0, 0
    for ds, day, t, entry, dswx, perm in labelled_dates(site, stack_id):
        has_hv = not np.isnan(ds["HV"].values[t]).all()
        valid = ds["valid"].values[t].astype(bool)
        row = {"date": day, "gap_h": entry["hours_from_nisar"], "has_hv": has_hv,
               "valid": round(float(valid.mean()), 3)}
        hh, hv = to_db(ds["HH"].values[t]), to_db(ds["HV"].values[t])
        on_built = valid & built
        row["built_hh_db"] = round(float(np.nanmedian(hh[on_built])), 2) if on_built.any() else None
        row["built_hv_db"] = round(float(np.nanmedian(hv[on_built])), 2) if on_built.any() and has_hv else None
        if dswx is not None:
            label_ok = valid & ~np.isin(dswx, DSWX_INVALID)
            scored = label_ok.sum()
            open_w, veg = label_ok & (dswx == DSWX_OPEN_WATER), label_ok & (dswx == DSWX_INUNDATED_VEG)
            seen = label_ok & inland_permanent
            row.update({
                "labelled": has_hv,
                "label_invalid": round(float(1 - scored / max(valid.sum(), 1)), 3),
                "open": round(float(open_w.sum() / max(scored, 1)), 4),
                "inundated_veg": round(float(veg.sum() / max(scored, 1)), 4),
                "changing_ha": round(area_ha(open_w & ~perm), 1),
                "permanent_seen_as_water": (round(float(np.isin(dswx[seen], (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG)).mean()), 3)
                                            if seen.sum() >= 500 else None),
            })
        rows.append(row)
        n_dates += 1
        n_hv += has_hv
    ds_all = len(ds["time"]) if rows else 0
    labelled = [r for r in rows if r.get("labelled")]
    return {
        "site": site, "stack": stack_id, "dates": ds_all, "dates_with_label_files": n_dates,
        "labelled_scenes": len(labelled),
        "label_gap_h_max": max((r["gap_h"] for r in labelled), default=None),
        "valid_mean": round(float(np.mean([r["valid"] for r in labelled])), 3) if labelled else None,
        "changing_ha_total": round(sum(r["changing_ha"] for r in labelled), 1),
        "built_hh_db_range": _spread([r["built_hh_db"] for r in rows]),
        "rows": rows,
    }


def _spread(values: list[float | None]) -> list[float] | None:
    v = [x for x in values if x is not None]
    return [min(v), max(v)] if v else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", nargs="+", default=list(CV_LABEL_SITES))
    args = parser.parse_args()
    out = []
    for site in args.site:
        for stack_id in site_stacks(site) + EXTRA_TEST_STACKS.get(site, ()):
            if not _built(site, stack_id):
                print(f"{site} {stack_id}: not built, skipped")
                continue
            q = stack_quality(site, stack_id)
            out.append(q)
            lab = [r for r in q["rows"] if r.get("labelled")]
            print(f"{site} {stack_id}: {q['dates']} dates, {q['labelled_scenes']} labelled (gap <= {MAX_GAP_H} h, "
                  f"max {q['label_gap_h_max']} h), valid {q['valid_mean']}, changing open water {q['changing_ha_total']} ha, "
                  f"label invalid median {np.median([r['label_invalid'] for r in lab]) if lab else None}, "
                  f"built HH {q['built_hh_db_range']} dB, permanent seen as water "
                  f"{[r['permanent_seen_as_water'] for r in lab]}")
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    path = METRICS_DIR / "cv_data_quality.json"
    path.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "max_gap_h": MAX_GAP_H, "stacks": out}, indent=1), encoding="utf-8")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
