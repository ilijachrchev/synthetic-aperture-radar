"""Same-day Sentinel-1 water maps (OPERA DSWx-S1) as labels for the CV model.

For every NISAR GCOV acquisition of a site (one per stack and time; a day can
hold a morning ascending and an evening descending acquisition), picks the one
Sentinel-1 pass closest in time on the same UTC day and downloads only its
water classification layer, B01_WTR, newest reprocessing per tile (needs the
Earthdata login in your .netrc). The real time gap is recorded per acquisition,
so labels far from the NISAR time can be filtered out.

B01_WTR classes (OPERA DSWx-S1 product spec JPL D-108761 Rev A, July 2024,
the version of the v1.0 files we use; the older v0.2.1 table differs):
    0 not water, 1 open water, 3 inundated vegetation,
    250 HAND masked, 251 layover/shadow masked, 255 fill (no data)

Output:
    data/raw/dswx/<site>/<stack_id>/<YYYYMMDD>/<granule>_B01_WTR.tif
    data/raw/dswx/<site>/index.json   (one entry per NISAR acquisition)

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
PASS_GAP_MIN = 10.0  # tiles of one Sentinel-1 pass start within minutes of each other

WTR_CLASSES = {
    0: "not_water",
    1: "open_water",
    3: "inundated_vegetation",
    250: "hand_masked",
    251: "layover_shadow_masked",
    255: "fill",
}
WTR_INVALID = (250, 251, 255)


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def hours_apart(a_iso: str, b_iso: str) -> float:
    return abs((_ts(a_iso) - _ts(b_iso)).total_seconds()) / 3600


def _tile(granule_ur: str) -> str:
    return granule_ur.split("_")[3]  # OPERA_L3_DSWx-S1_<TILE>_<acq>Z_<production>Z_<platform>_30_v1.0


def _production(granule_ur: str) -> str:
    return granule_ur.split("_")[5]


def _platform(granule_ur: str) -> str:
    return granule_ur.split("_")[6]


def nisar_acquisitions(site: Site, min_coverage: float = MIN_COVERAGE) -> list[dict[str, str]]:
    """One entry per NISAR GCOV acquisition whose frame covers the whole site."""
    catalog = json.loads((CATALOG_DIR / f"{site.name}.json").read_text(encoding="utf-8"))
    seen, out = set(), []
    for g in catalog["granules"]:
        if g["product"] != "GCOV" or g["site_coverage"] < min_coverage:
            continue
        key = (g["stack_id"], g["begin_utc"])
        if key not in seen:
            seen.add(key)
            out.append({"stack_id": g["stack_id"], "nisar_utc": g["begin_utc"], "granule_ur": g["granule_ur"]})
    return sorted(out, key=lambda a: (a["nisar_utc"], a["stack_id"]))


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


def group_passes(granules: list[dict[str, Any]], gap_min: float = PASS_GAP_MIN) -> list[list[dict[str, Any]]]:
    """Group granules into Sentinel-1 passes: same platform, start times within gap_min."""
    passes: list[list[dict[str, Any]]] = []
    for g in sorted(granules, key=lambda x: (_platform(x["granule_ur"]), x["begin_utc"])):
        last = passes[-1] if passes else None
        if (last and _platform(last[-1]["granule_ur"]) == _platform(g["granule_ur"])
                and hours_apart(last[-1]["begin_utc"], g["begin_utc"]) * 60 <= gap_min):
            last.append(g)
        else:
            passes.append([g])
    return passes


def pick_pass(granules: list[dict[str, Any]], nisar_utc: str) -> tuple[list[dict[str, Any]], float | None]:
    """The pass closest to one NISAR acquisition, newest reprocessing per tile, and its time gap (h)."""
    passes = group_passes(granules)
    if not passes:
        return [], None
    best = min(passes, key=lambda p: min(hours_apart(g["begin_utc"], nisar_utc) for g in p))
    newest: dict[str, dict[str, Any]] = {}
    for g in best:
        tile = _tile(g["granule_ur"])
        if tile not in newest or _production(g["granule_ur"]) > _production(newest[tile]["granule_ur"]):
            newest[tile] = g
    chosen = sorted(newest.values(), key=lambda g: _tile(g["granule_ur"]))
    gap = round(max(hours_apart(g["begin_utc"], nisar_utc) for g in chosen), 2)
    return chosen, gap


def build_index(site: Site, stacks: set[str] | None = None) -> list[dict[str, Any]]:
    """One entry per NISAR acquisition: its stack and time, the chosen pass and the time gap."""
    by_day: dict[str, list[dict[str, Any]]] = {}
    index = []
    for acq in nisar_acquisitions(site):
        if stacks and acq["stack_id"] not in stacks:
            continue
        day = acq["nisar_utc"][:10]
        if day not in by_day:
            by_day[day] = search_day(site, day)
        chosen, gap = pick_pass(by_day[day], acq["nisar_utc"])
        index.append({**acq, "date": day, "hours_from_nisar": gap,
                      "platform": _platform(chosen[0]["granule_ur"]) if chosen else None, "selected": chosen})
    return index


def download(site: Site, index: list[dict[str, Any]]) -> None:
    import earthaccess  # imported here so --dry-run needs no login

    earthaccess.login(strategy="netrc")
    for entry in index:
        urls = [g["wtr_url"] for g in entry["selected"] if g["wtr_url"]]
        if not urls:
            continue
        acq_dir = DSWX_RAW / site.name / entry["stack_id"] / entry["date"].replace("-", "")
        acq_dir.mkdir(parents=True, exist_ok=True)
        todo = [u for u in urls if not (acq_dir / u.rsplit("/", 1)[-1]).exists()]
        if todo:
            earthaccess.download(todo, local_path=str(acq_dir))
        # POSIX-style relative paths, so the index works on Windows, Linux and Colab alike
        entry["files"] = [(acq_dir / u.rsplit("/", 1)[-1]).relative_to(DSWX_RAW).as_posix() for u in urls]
        print(f"  {entry['stack_id']} {entry['date']}: {len(urls)} WTR tile(s), {entry['hours_from_nisar']} h")
    out = DSWX_RAW / site.name / "index.json"
    out.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"  index -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True)
    parser.add_argument("--stack", action="append", help="only this stack id; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="show the matches, no login needed")
    args = parser.parse_args()

    site = get_site(args.site)
    index = build_index(site, set(args.stack) if args.stack else None)
    matched = sum(1 for e in index if e["selected"])
    print(f"{site.name}: {matched} of {len(index)} NISAR acquisitions have a same-day DSWx-S1 pass")
    for e in index:
        tiles = [_tile(g["granule_ur"]) for g in e["selected"]]
        print(f"  {e['stack_id']} {e['nisar_utc'][:16]}: {e['platform']} {tiles} gap {e['hours_from_nisar']} h")
    if not args.dry_run:
        download(site, index)


if __name__ == "__main__":
    main()
