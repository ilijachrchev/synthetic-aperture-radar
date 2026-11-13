"""Same-day Sentinel-1 water maps (OPERA DSWx-S1) as labels for the CV model.

For every NISAR acquisition date of a site, finds the DSWx-S1 tiles of the same
UTC day over the site box (public CMR search) and downloads only their water
classification layer, B01_WTR (needs the Earthdata login in your .netrc).

B01_WTR classes (OPERA DSWx-S1 product spec JPL D-108761 Rev A, July 2024,
the version of the v1.0 files we use; the older v0.2.1 table differs):
    0 not water, 1 open water, 3 inundated vegetation,
    250 HAND masked, 251 layover/shadow masked, 255 fill (no data)

Output:
    data/raw/dswx/<site>/<YYYYMMDD>/<granule>_B01_WTR.tif
    data/raw/dswx/<site>/index.json

Usage:
    python -m pipeline.dswx --site albufera --dry-run
    python -m pipeline.dswx --site albufera

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

import requests

from pipeline.config import CATALOG_DIR, RAW_DIR, Site, get_site

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
DSWX_COLLECTION = "OPERA_L3_DSWX-S1_V1"
DSWX_RAW = RAW_DIR / "dswx"
MIN_COVERAGE = 0.99

WTR_CLASSES = {
    0: "not_water",
    1: "open_water",
    3: "inundated_vegetation",
    250: "hand_masked",
    251: "layover_shadow_masked",
    255: "fill",
}
WTR_INVALID = (250, 251, 255)


def nisar_dates(site: Site, min_coverage: float = MIN_COVERAGE) -> dict[str, list[str]]:
    """NISAR GCOV acquisition times per UTC date, for frames that cover the whole site."""
    catalog = json.loads((CATALOG_DIR / f"{site.name}.json").read_text(encoding="utf-8"))
    dates: dict[str, list[str]] = {}
    for g in catalog["granules"]:
        if g["product"] == "GCOV" and g["site_coverage"] >= min_coverage:
            dates.setdefault(g["begin_utc"][:10], []).append(g["begin_utc"])
    return dict(sorted(dates.items()))


def wtr_url(umm: dict[str, Any]) -> str | None:
    """HTTPS link of the B01_WTR layer in one DSWx-S1 granule record."""
    for u in umm.get("RelatedUrls", []):
        url = u.get("URL", "")
        if url.startswith("https") and url.endswith("_B01_WTR.tif"):
            return url
    return None


def search_day(site: Site, day: str) -> list[dict[str, Any]]:
    """DSWx-S1 granules over the site box on one UTC day."""
    params = {
        "short_name": DSWX_COLLECTION,
        "bounding_box": ",".join(str(v) for v in site.bbox),
        "temporal": f"{day}T00:00:00Z,{day}T23:59:59Z",
        "page_size": 200,
    }
    resp = requests.get(CMR_GRANULES, params=params, timeout=120)
    resp.raise_for_status()
    out = []
    for item in resp.json().get("items", []):
        umm = item["umm"]
        out.append({
            "granule_ur": umm["GranuleUR"],
            "begin_utc": umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"],
            "wtr_url": wtr_url(umm),
        })
    return sorted(out, key=lambda g: g["begin_utc"])


def hours_apart(a_iso: str, b_iso: str) -> float:
    a = datetime.fromisoformat(a_iso.replace("Z", "+00:00"))
    b = datetime.fromisoformat(b_iso.replace("Z", "+00:00"))
    return abs((a - b).total_seconds()) / 3600


def _tile(granule_ur: str) -> str:
    return granule_ur.split("_")[3]  # OPERA_L3_DSWx-S1_<TILE>_<acq>Z_<production>Z_...


def _production(granule_ur: str) -> str:
    return granule_ur.split("_")[5]


def select_closest_pass(granules: list[dict[str, Any]], window_h: float = 0.5) -> list[dict[str, Any]]:
    """Keep the Sentinel-1 pass closest to NISAR, one (newest) granule per tile.

    A day can hold a morning and an evening Sentinel-1 pass, and reprocessed
    duplicates of a tile. Labels should come from the pass nearest the NISAR
    acquisition, so we keep granules within window_h of the best match.
    """
    if not granules:
        return []
    best = min(g["hours_from_nisar"] for g in granules)
    close = [g for g in granules if g["hours_from_nisar"] - best <= window_h]
    newest: dict[str, dict[str, Any]] = {}
    for g in close:
        tile = _tile(g["granule_ur"])
        if tile not in newest or _production(g["granule_ur"]) > _production(newest[tile]["granule_ur"]):
            newest[tile] = g
    return sorted(newest.values(), key=lambda g: _tile(g["granule_ur"]))


def build_index(site: Site) -> list[dict[str, Any]]:
    """For each NISAR date: its acquisition times, every same-day DSWx-S1 granule and the selected ones."""
    index = []
    for day, nisar_times in nisar_dates(site).items():
        granules = search_day(site, day)
        for g in granules:
            g["hours_from_nisar"] = round(min(hours_apart(g["begin_utc"], t) for t in nisar_times), 2)
        index.append({"date": day, "nisar_utc": nisar_times, "dswx": granules, "selected": select_closest_pass(granules)})
    return index


def download(site: Site, index: list[dict[str, Any]]) -> None:
    import earthaccess  # imported here so --dry-run needs no login

    earthaccess.login(strategy="netrc")
    for entry in index:
        urls = [g["wtr_url"] for g in entry["selected"] if g["wtr_url"]]
        if not urls:
            continue
        day_dir = DSWX_RAW / site.name / entry["date"].replace("-", "")
        day_dir.mkdir(parents=True, exist_ok=True)
        todo = [u for u in urls if not (day_dir / u.rsplit("/", 1)[-1]).exists()]
        if todo:
            earthaccess.download(todo, local_path=str(day_dir))
        print(f"  {entry['date']}: {len(urls)} WTR tile(s)")
    out = DSWX_RAW / site.name / "index.json"
    out.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"  index -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True)
    parser.add_argument("--dry-run", action="store_true", help="show the matches, no login needed")
    args = parser.parse_args()

    site = get_site(args.site)
    index = build_index(site)
    matched = sum(1 for e in index if e["dswx"])
    print(f"{site.name}: {matched} of {len(index)} NISAR dates have a same-day DSWx-S1 map")
    for e in index:
        sel = e["selected"]
        tiles = [_tile(g["granule_ur"]) for g in sel]
        gap = max((g["hours_from_nisar"] for g in sel), default=None)
        print(f"  {e['date']}: {len(e['dswx'])} found, {len(sel)} selected {tiles}, at most {gap} h from NISAR")
    if not args.dry_run:
        download(site, index)


if __name__ == "__main__":
    main()
