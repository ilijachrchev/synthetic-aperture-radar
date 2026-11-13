"""List every NISAR file over a site from NASA's public CMR catalog (no login).

Writes data/catalog/<site>.json: one entry per granule with its stack
(track, direction, frame), mode, polarizations, maturity, dates, links
and footprint. CV and ML use it to pick comparable dates; the stack
builder uses it to know what to request from Harmony.

Usage:
    python -m pipeline.catalog --site albufera
    python -m pipeline.catalog --all

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any

import requests
from shapely.geometry import Polygon, box

from pipeline.config import CATALOG_DIR, SITES, Site, get_site

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
PAGE_SIZE = 2000
TIMEOUT_S = 120

# Collections searched for each site. BETA is skipped on purpose: it is
# not calibrated and must not be mixed with newer data.
COLLECTIONS = {
    "GCOV": ["NISAR_L2_GCOV_PROVISIONAL_V1", "NISAR_L2_GCOV_V1"],
    "GUNW": ["NISAR_L2_GUNW_PROVISIONAL_V1", "NISAR_L2_GUNW_V1"],
}

_CRID = re.compile(r"_(P\d{5})_")
_DATES = re.compile(r"_(\d{8}T\d{6})")


def maturity_of(short_name: str) -> str:
    """PROVISIONAL / VALIDATED / BETA from a collection short name."""
    for level in ("PROVISIONAL", "BETA"):
        if level in short_name:
            return level
    return "VALIDATED"


def parse_title_dates(granule_ur: str) -> list[str]:
    """All YYYYMMDDTHHMMSS stamps in a NISAR granule name, in order."""
    return _DATES.findall(granule_ur)


def _attrs(umm: dict[str, Any]) -> dict[str, list[str]]:
    return {a["Name"]: a.get("Values", []) for a in umm.get("AdditionalAttributes", [])}


def _first(attrs: dict[str, list[str]], key: str) -> str | None:
    values = attrs.get(key)
    return values[0] if values else None


def _iso(stamp: str) -> str:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).isoformat()


def site_coverage(footprint: list[tuple[float, float]], bbox: tuple[float, float, float, float]) -> float:
    """Share of the site bbox inside the granule footprint (0 to 1, in degree area).

    CMR returns any granule that touches the bbox, including frames that only
    clip a corner, so this tells full coverage apart from an edge hit.
    """
    site = box(*bbox)
    frame = Polygon(footprint)
    if not frame.is_valid:
        frame = frame.buffer(0)
    return round(site.intersection(frame).area / site.area, 3)


def granule_entry(umm: dict[str, Any], short_name: str, product: str) -> dict[str, Any]:
    """Flatten one CMR UMM-G record into the fields the pipeline needs."""
    ur = umm["GranuleUR"]
    attrs = _attrs(umm)
    urls = [u["URL"] for u in umm.get("RelatedUrls", []) if u.get("URL", "").startswith("https")]
    crid = _CRID.search(ur)
    stamps = parse_title_dates(ur)
    rng = umm.get("TemporalExtent", {}).get("RangeDateTime", {})
    polygon = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]

    entry: dict[str, Any] = {
        "granule_ur": ur,
        "collection": short_name,
        "product": product,
        "maturity": maturity_of(short_name),
        "crid": crid.group(1) if crid else None,
        "product_version": _first(attrs, "PRODUCT_VERSION"),
        "track": _first(attrs, "TRACK_NUMBER"),
        "direction": _first(attrs, "ASCENDING_DESCENDING"),
        "frame": _first(attrs, "FRAME_NUMBER"),
        "stack_id": _first(attrs, "STACK_ID"),
        "full_frame": _first(attrs, "FULL_FRAME") == "TRUE",
        "bandwidth_mhz": _first(attrs, "RANGE_BANDWIDTH_CONCAT"),
        "pols_a": attrs.get("FREQUENCY_A_POLARIZATION", []),
        "begin_utc": rng.get("BeginningDateTime"),
        "end_utc": rng.get("EndingDateTime"),
        "h5_url": next((u for u in urls if u.endswith(".h5")), None),
        "browse_url": next((u for u in urls if u.endswith("_LATLON.png")), None),
        "footprint": [(p["Longitude"], p["Latitude"]) for p in polygon],
    }
    if product == "GUNW" and len(stamps) >= 4:
        # GUNW names carry reference start/end, then secondary start/end.
        entry["reference_utc"] = _iso(stamps[0])
        entry["secondary_utc"] = _iso(stamps[2])
    return entry


def search_collection(short_name: str, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """All UMM-G records of one collection that intersect bbox (pages through CMR)."""
    params = {
        "short_name": short_name,
        "bounding_box": ",".join(str(v) for v in bbox),
        "page_size": PAGE_SIZE,
        "sort_key": "start_date",
    }
    headers: dict[str, str] = {}
    items: list[dict[str, Any]] = []
    while True:
        resp = requests.get(CMR_GRANULES, params=params, headers=headers, timeout=TIMEOUT_S)
        resp.raise_for_status()
        page = resp.json().get("items", [])
        items.extend(page)
        search_after = resp.headers.get("CMR-Search-After")
        if not page or not search_after or len(page) < PAGE_SIZE:
            break
        headers["CMR-Search-After"] = search_after
    return items


def build_catalog(site: Site) -> dict[str, Any]:
    """Query every collection for one site and return the catalog document."""
    entries: list[dict[str, Any]] = []
    for product, short_names in COLLECTIONS.items():
        for short_name in short_names:
            for item in search_collection(short_name, site.bbox):
                entry = granule_entry(item["umm"], short_name, product)
                entry["site_coverage"] = site_coverage(entry["footprint"], site.bbox)
                entries.append(entry)
    entries.sort(key=lambda e: (e["product"], e["stack_id"] or "", e["begin_utc"] or ""))
    return {
        "site": site.name,
        "bbox": list(site.bbox),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": CMR_GRANULES,
        "collections": [s for names in COLLECTIONS.values() for s in names],
        "count": len(entries),
        "granules": entries,
    }


def write_catalog(site: Site) -> dict[str, Any]:
    doc = build_catalog(site)
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    path = CATALOG_DIR / f"{site.name}.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"{site.name}: {doc['count']} granules -> {path.relative_to(CATALOG_DIR.parents[1])}")
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--site", help=f"one of: {', '.join(SITES)}")
    group.add_argument("--all", action="store_true", help="every site in pipeline.config")
    args = parser.parse_args()
    for site in SITES.values() if args.all else [get_site(args.site)]:
        write_catalog(site)


if __name__ == "__main__":
    main()
