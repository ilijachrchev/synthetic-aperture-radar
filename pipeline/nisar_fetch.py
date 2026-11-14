"""Fetch NISAR GCOV subsets for one site and stack through Harmony.

Needs an Earthdata login saved in your .netrc (see the README). Harmony cuts the
site box out of each HDF5 file and returns one GeoTIFF per layer, kept in the
granule's native grid: no reprojection here, so the stack builder does a single
controlled reprojection later (bilinear on power, nearest on the mask).

One granule per acquisition date: if the catalog holds several for a date
(another bandwidth mode, a partial frame, a reprocessed copy), only the stack's
bandwidth is kept, then full frame, VALIDATED, newest CRID and highest product
counter win. A date counts as fetched only when HHHH and mask arrived; otherwise
no request.json is written and the next run tries it again.

Output, one folder per acquisition:
    data/raw/nisar/<site>/<stack_id>/<YYYYMMDD>/<LAYER>.tif
    data/raw/nisar/<site>/<stack_id>/<YYYYMMDD>/request.json   (provenance, written last)

Usage:
    python -m pipeline.nisar_fetch --site albufera --stack 066_D_069 --dry-run
    python -m pipeline.nisar_fetch --site albufera --stack 066_D_069

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from pipeline.config import CATALOG_DIR, RAW_DIR, Site, get_site

GCOV_GROUP = "/science/LSAR/GCOV/grids/frequencyA"
GCOV_LAYERS = ("HHHH", "HVHV", "mask", "numberOfLooks")
DEFAULT_LAYERS = ("HHHH", "HVHV", "mask")  # numberOfLooks is opt-in (--with-looks): a third of the volume
REQUIRED_LAYERS = ("HHHH", "mask")         # a date without these is not saved
DEFAULT_BANDWIDTH = "20+5"                 # MHz, frequency A + B: the 20 m GCOV posting our stacks use
CMR_COLLECTIONS = "https://cmr.earthdata.nasa.gov/search/collections.json"
NISAR_RAW = RAW_DIR / "nisar"
MIN_COVERAGE = 0.99  # only frames that cover the whole site box
_MATURITY_RANK = {"VALIDATED": 2, "PROVISIONAL": 1, "BETA": 0}


def load_catalog(site: Site) -> dict[str, Any]:
    path = CATALOG_DIR / f"{site.name}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run python -m pipeline.catalog --site {site.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def acquisition_stamp(granule: dict[str, Any]) -> str:
    """YYYYMMDDTHHMMSS of the acquisition start, as it appears in NISAR file names."""
    return re.search(r"_(\d{8}T\d{6})_", granule["granule_ur"]).group(1)


def granule_rank(granule: dict[str, Any]) -> tuple:
    """Preference among granules of one acquisition date (higher wins)."""
    counter = granule["granule_ur"].rsplit("_", 1)[-1]
    return (
        bool(granule.get("full_frame")),
        _MATURITY_RANK.get(granule.get("maturity") or "", 0),
        granule.get("crid") or "",
        int(counter) if counter.isdigit() else 0,
    )


def select_granules(catalog: dict[str, Any], stack_id: str, bandwidth: str | None = DEFAULT_BANDWIDTH,
                    min_coverage: float = MIN_COVERAGE) -> list[dict[str, Any]]:
    """One GCOV granule per acquisition date of a stack, covering the whole site, oldest first.

    Dates are the unit because each date gets one folder on disk.
    """
    best: dict[str, dict[str, Any]] = {}
    for g in catalog["granules"]:
        if g["product"] != "GCOV" or g["stack_id"] != stack_id or g["site_coverage"] < min_coverage:
            continue
        if bandwidth and g.get("bandwidth_mhz") != bandwidth:
            continue
        day = acquisition_stamp(g)[:8]
        if day not in best or granule_rank(g) > granule_rank(best[day]):
            best[day] = g
    return sorted(best.values(), key=lambda g: g["begin_utc"])


def match_layer(filename: str) -> str | None:
    """Which GCOV layer a Harmony output file holds, from its name."""
    for layer in GCOV_LAYERS:
        if re.search(rf"(^|[^A-Za-z]){layer}([^A-Za-z]|$)", filename):
            return layer
    return None


def assign_outputs(granules: list[dict[str, Any]], file_names: list[str]) -> dict[str, dict[str, str]]:
    """Map each granule UR to {layer: Harmony output file name}.

    Harmony names every output after the full granule UR plus the dataset path
    (checked on real jobs), so a file is assigned only when exactly one of the
    requested granule URs appears in its name.
    """
    out: dict[str, dict[str, str]] = {g["granule_ur"]: {} for g in granules}
    for name in file_names:
        layer = match_layer(name)
        owners = [ur for ur in out if ur in name]
        if layer and len(owners) == 1:
            out[owners[0]][layer] = name
    return out


def expected_layers(granule: dict[str, Any], layers: tuple[str, ...]) -> tuple[str, ...]:
    """Layers a granule should deliver: no HVHV for HH-only acquisitions."""
    if "HV" not in (granule.get("pols_a") or []):
        return tuple(lay for lay in layers if lay != "HVHV")
    return layers


def collection_concept_id(short_name: str) -> str:
    resp = requests.get(CMR_COLLECTIONS, params={"short_name": short_name}, timeout=60)
    resp.raise_for_status()
    entries = resp.json()["feed"]["entry"]
    if len(entries) != 1:
        raise RuntimeError(f"expected one CMR collection for {short_name}, got {len(entries)}")
    return entries[0]["id"]


def plan(site: Site, stack_id: str, overwrite: bool = False, dates: set[str] | None = None,
         bandwidth: str | None = DEFAULT_BANDWIDTH) -> dict[str, list[dict[str, Any]]]:
    """Granules still to fetch, grouped by collection (one Harmony job per collection)."""
    jobs: dict[str, list[dict[str, Any]]] = {}
    for g in select_granules(load_catalog(site), stack_id, bandwidth):
        day = acquisition_stamp(g)[:8]
        if dates and day not in dates:
            continue
        if (NISAR_RAW / site.name / stack_id / day / "request.json").exists() and not overwrite:
            continue
        jobs.setdefault(g["collection"], []).append(g)
    return jobs


def run_job(site: Site, stack_id: str, short_name: str, granules: list[dict[str, Any]],
            layers: tuple[str, ...] = DEFAULT_LAYERS) -> list[str]:
    """Run one Harmony job and save each complete date; returns the dates saved."""
    from harmony import BBox, Client, Collection, Request  # imported here so --dry-run needs no login

    concept_id = collection_concept_id(short_name)
    request = Request(
        collection=Collection(id=concept_id),
        spatial=BBox(*site.bbox),
        granule_name=[g["granule_ur"] for g in granules],
        # HVHV is asked for every granule: Harmony skips datasets a granule does not
        # have (checked: the HH-only date 20260922 of 058_A_021 returned HHHH and mask).
        variables=[f"{GCOV_GROUP}/{layer}" for layer in layers],
        format="image/tiff",
        skip_preview=True,
    )
    client = Client()  # uses the Earthdata login in your .netrc
    job_id = client.submit(request)
    print(f"  Harmony job {job_id} ({len(granules)} granules from {short_name}), processing...", flush=True)
    client.wait_for_processing(job_id, show_progress=False)

    saved: list[str] = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)  # the temp folder lives here, on the same disk as the output
    with tempfile.TemporaryDirectory(dir=RAW_DIR) as tmp:
        paths = [Path(f.result()) for f in client.download_all(job_id, directory=tmp, overwrite=True)]
        files = {p.name: p for p in paths}
        assigned = assign_outputs(granules, list(files))
        for g in granules:
            day = acquisition_stamp(g)[:8]
            got = assigned[g["granule_ur"]]
            lacking = [lay for lay in REQUIRED_LAYERS if lay not in got]
            if lacking:
                print(f"  {day}: NOT saved, Harmony returned no {', '.join(lacking)}; the next run retries")
                continue
            day_dir = NISAR_RAW / site.name / stack_id / day
            day_dir.mkdir(parents=True, exist_ok=True)
            for old in day_dir.glob("*.tif"):  # drop layers of an earlier, replaced granule
                old.unlink()
            for layer, name in got.items():
                os.replace(files[name], day_dir / f"{layer}.tif")
            (day_dir / "request.json").write_text(json.dumps({
                "granule_ur": g["granule_ur"],
                "collection": short_name,
                "concept_id": concept_id,
                "crid": g["crid"],
                "maturity": g["maturity"],
                "bandwidth_mhz": g.get("bandwidth_mhz"),
                "pols_a": g["pols_a"],
                "bbox": list(site.bbox),
                "harmony_job_id": job_id,
                "layers": got,
                "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, indent=1), encoding="utf-8")
            absent = [lay for lay in expected_layers(g, layers) if lay not in got]
            note = f" (missing: {', '.join(absent)})" if absent else ("" if "HV" in g["pols_a"] else " (HH only, as catalogued)")
            print(f"  {day}: {len(got)} layers{note}", flush=True)
            saved.append(day)
        used = {name for got in assigned.values() for name in got.values()}
        stray = sorted(set(files) - used)
        if stray:
            print(f"  WARNING: {len(stray)} Harmony files matched no granule and layer: {stray[:3]}")
    return saved


def fetch_stack(site: Site, stack_id: str, *, layers: tuple[str, ...] = DEFAULT_LAYERS,
                bandwidth: str | None = DEFAULT_BANDWIDTH, overwrite: bool = False,
                dates: set[str] | None = None, dry_run: bool = False) -> int:
    """Plan and run the Harmony jobs of one stack; returns how many granules were requested."""
    jobs = plan(site, stack_id, overwrite, dates, bandwidth)
    total = sum(len(v) for v in jobs.values())
    print(f"{site.name} {stack_id}: {total} granule(s) to fetch, layers {', '.join(layers)}", flush=True)
    for short_name, granules in jobs.items():
        print(f" {short_name}: {', '.join(acquisition_stamp(g)[:8] for g in granules)}")
    if not dry_run:
        for short_name, granules in jobs.items():
            run_job(site, stack_id, short_name, granules, layers)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True)
    parser.add_argument("--stack", required=True, help="stack id from the catalog, e.g. 066_D_069")
    parser.add_argument("--dry-run", action="store_true", help="show what would be requested, no login needed")
    parser.add_argument("--overwrite", action="store_true", help="fetch dates that are already on disk again")
    parser.add_argument("--date", action="append", help="only this acquisition date (YYYYMMDD); repeatable")
    parser.add_argument("--with-looks", action="store_true", help="also fetch numberOfLooks (not needed by the baseline)")
    parser.add_argument("--bandwidth", default=DEFAULT_BANDWIDTH, help="range bandwidth mode to keep (default 20+5)")
    args = parser.parse_args()

    fetch_stack(
        get_site(args.site), args.stack,
        layers=GCOV_LAYERS if args.with_looks else DEFAULT_LAYERS,
        bandwidth=args.bandwidth, overwrite=args.overwrite,
        dates=set(args.date) if args.date else None, dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
