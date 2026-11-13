"""Fetch NISAR GCOV subsets for one site and stack through Harmony.

Needs an Earthdata login saved in your .netrc (see the README). Harmony cuts the
site box out of each HDF5 file and returns one GeoTIFF per layer, kept in the
granule's native grid: no reprojection here, so the stack builder does a single
controlled reprojection later (bilinear on power, nearest on the mask).

Output, one folder per acquisition:
    data/raw/nisar/<site>/<stack_id>/<YYYYMMDD>/<LAYER>.tif
    data/raw/nisar/<site>/<stack_id>/<YYYYMMDD>/request.json   (provenance)

Usage:
    python -m pipeline.nisar_fetch --site albufera --stack 066_D_069 --dry-run
    python -m pipeline.nisar_fetch --site albufera --stack 066_D_069

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from pipeline.config import CATALOG_DIR, RAW_DIR, Site, get_site

GCOV_GROUP = "/science/LSAR/GCOV/grids/frequencyA"
GCOV_LAYERS = ("HHHH", "HVHV", "mask", "numberOfLooks")
CMR_COLLECTIONS = "https://cmr.earthdata.nasa.gov/search/collections.json"
NISAR_RAW = RAW_DIR / "nisar"
MIN_COVERAGE = 0.99  # only frames that cover the whole site box


def load_catalog(site: Site) -> dict[str, Any]:
    path = CATALOG_DIR / f"{site.name}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run python -m pipeline.catalog --site {site.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def select_granules(catalog: dict[str, Any], stack_id: str, min_coverage: float = MIN_COVERAGE) -> list[dict[str, Any]]:
    """GCOV granules of one stack that cover the site box, oldest first."""
    chosen = [
        g for g in catalog["granules"]
        if g["product"] == "GCOV" and g["stack_id"] == stack_id and g["site_coverage"] >= min_coverage
    ]
    return sorted(chosen, key=lambda g: g["begin_utc"])


def acquisition_stamp(granule: dict[str, Any]) -> str:
    """YYYYMMDDTHHMMSS of the acquisition start, as it appears in NISAR file names."""
    return re.search(r"_(\d{8}T\d{6})_", granule["granule_ur"]).group(1)


def match_layer(filename: str) -> str | None:
    """Which GCOV layer a Harmony output file holds, from its name."""
    for layer in GCOV_LAYERS:
        if re.search(rf"(^|[^A-Za-z]){layer}([^A-Za-z]|$)", filename):
            return layer
    return None


def collection_concept_id(short_name: str) -> str:
    resp = requests.get(CMR_COLLECTIONS, params={"short_name": short_name}, timeout=60)
    resp.raise_for_status()
    entries = resp.json()["feed"]["entry"]
    if len(entries) != 1:
        raise RuntimeError(f"expected one CMR collection for {short_name}, got {len(entries)}")
    return entries[0]["id"]


def plan(site: Site, stack_id: str, overwrite: bool) -> dict[str, list[dict[str, Any]]]:
    """Granules still to fetch, grouped by collection (one Harmony job per collection)."""
    jobs: dict[str, list[dict[str, Any]]] = {}
    for g in select_granules(load_catalog(site), stack_id):
        day_dir = NISAR_RAW / site.name / stack_id / acquisition_stamp(g)[:8]
        if (day_dir / "request.json").exists() and not overwrite:
            continue
        jobs.setdefault(g["collection"], []).append(g)
    return jobs


def run_job(site: Site, stack_id: str, short_name: str, granules: list[dict[str, Any]]) -> None:
    from harmony import BBox, Client, Collection, Request  # imported here so --dry-run needs no login

    concept_id = collection_concept_id(short_name)
    request = Request(
        collection=Collection(id=concept_id),
        spatial=BBox(*site.bbox),
        granule_name=[g["granule_ur"] for g in granules],
        variables=[f"{GCOV_GROUP}/{layer}" for layer in GCOV_LAYERS],
        format="image/tiff",
        skip_preview=True,
    )
    client = Client()  # uses the Earthdata login in your .netrc
    job_id = client.submit(request)
    print(f"  Harmony job {job_id} ({len(granules)} granules from {short_name})")
    client.wait_for_processing(job_id, show_progress=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)  # the temp folder lives here, on the same disk as the output
    with tempfile.TemporaryDirectory(dir=RAW_DIR) as tmp:
        files = [Path(f.result()) for f in client.download_all(job_id, directory=tmp, overwrite=True)]
        for g in granules:
            stamp = acquisition_stamp(g)
            day_dir = NISAR_RAW / site.name / stack_id / stamp[:8]
            day_dir.mkdir(parents=True, exist_ok=True)
            got = {}
            for f in files:
                layer = match_layer(f.name)
                if stamp in f.name and layer:
                    shutil.move(str(f), day_dir / f"{layer}.tif")
                    got[layer] = f.name
            (day_dir / "request.json").write_text(json.dumps({
                "granule_ur": g["granule_ur"],
                "collection": short_name,
                "concept_id": concept_id,
                "crid": g["crid"],
                "maturity": g["maturity"],
                "pols_a": g["pols_a"],
                "bbox": list(site.bbox),
                "harmony_job_id": job_id,
                "layers": got,
                "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, indent=1), encoding="utf-8")
            missing = [lay for lay in GCOV_LAYERS if lay not in got]
            note = f" (missing: {', '.join(missing)})" if missing else ""
            print(f"  {stamp[:8]}: {len(got)} layers{note}")
        leftovers = [f.name for f in files if f.exists()]
        if leftovers:
            print(f"  WARNING: {len(leftovers)} Harmony files did not match a granule and layer: {leftovers[:3]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True)
    parser.add_argument("--stack", required=True, help="stack id from the catalog, e.g. 066_D_069")
    parser.add_argument("--dry-run", action="store_true", help="show what would be requested, no login needed")
    parser.add_argument("--overwrite", action="store_true", help="fetch dates that are already on disk again")
    args = parser.parse_args()

    site = get_site(args.site)
    jobs = plan(site, args.stack, args.overwrite)
    total = sum(len(v) for v in jobs.values())
    print(f"{site.name} {args.stack}: {total} granule(s) to fetch, layers {', '.join(GCOV_LAYERS)}")
    for short_name, granules in jobs.items():
        print(f" {short_name}: {', '.join(acquisition_stamp(g)[:8] for g in granules)}")
    if args.dry_run or not jobs:
        return
    for short_name, granules in jobs.items():
        run_job(site, args.stack, short_name, granules)


if __name__ == "__main__":
    main()
