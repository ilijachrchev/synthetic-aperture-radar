"""Every OPERA DSWx-S1 pass over a site in a date range (not only NISAR days).

``pipeline.dswx`` fetches the one pass nearest each NISAR acquisition, as CV
labels. The forecast needs the whole history, so this module pages through CMR
for a date range and keeps, per Sentinel-1 pass, the newest reprocessing of each
tile. Only the small B01_WTR layer is downloaded (about 0.15 MB per tile).

Output:
    data/raw/dswx_history/<site>/<pass_id>/<granule>_B01_WTR.tif
    data/raw/dswx_history/<site>/index.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from pipeline.config import RAW_DIR, Site
from pipeline.dswx import CMR_GRANULES, DSWX_COLLECTION, _platform, _production, _tile, group_passes, wtr_url

HISTORY_RAW = RAW_DIR / "dswx_history"


def search_range(site: Site, start: str, end: str) -> list[dict[str, Any]]:
    """DSWx-S1 granules over the site box between two ISO dates (inclusive), all pages."""
    params = {
        "short_name": DSWX_COLLECTION,
        "bounding_box": ",".join(str(v) for v in site.bbox),
        "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
        "page_size": 2000,
    }
    headers: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    while True:
        resp = requests.get(CMR_GRANULES, params=params, headers=headers, timeout=120)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            umm = item["umm"]
            out.append({
                "granule_ur": umm["GranuleUR"],
                "begin_utc": umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"],
                "wtr_url": wtr_url(umm),
            })
        token = resp.headers.get("CMR-Search-After")
        if not items or not token:
            break
        headers = {"CMR-Search-After": token}
    return sorted(out, key=lambda g: g["begin_utc"])


def newest_per_tile(granules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the newest production (reprocessing) of each tile."""
    newest: dict[str, dict[str, Any]] = {}
    for g in granules:
        tile = _tile(g["granule_ur"])
        if tile not in newest or _production(g["granule_ur"]) > _production(newest[tile]["granule_ur"]):
            newest[tile] = g
    return sorted(newest.values(), key=lambda g: _tile(g["granule_ur"]))


def build_index(granules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per Sentinel-1 pass: id, start time, platform and the chosen tiles."""
    index = []
    for group in group_passes(granules):
        chosen = [g for g in newest_per_tile(group) if g["wtr_url"]]
        if not chosen:
            continue
        begin = min(g["begin_utc"] for g in chosen)
        platform = _platform(chosen[0]["granule_ur"])
        stamp = begin[:19].replace("-", "").replace(":", "")
        index.append({
            "pass_id": f"{stamp}_{platform}",
            "date": begin[:10],
            "begin_utc": begin,
            "platform": platform,
            "tiles": [_tile(g["granule_ur"]) for g in chosen],
            "selected": chosen,
        })
    return sorted(index, key=lambda e: e["begin_utc"])


def download(site: Site, index: list[dict[str, Any]], root: Path = HISTORY_RAW, workers: int = 8) -> Path:
    """Download each pass's WTR tiles (skips files already on disk), several passes at once, and write index.json."""
    from concurrent.futures import ThreadPoolExecutor

    import earthaccess  # imported here so searching needs no login

    earthaccess.login(strategy="netrc")
    site_dir = root / site.name

    def fetch(entry: dict[str, Any]) -> None:
        pass_dir = site_dir / entry["pass_id"]
        pass_dir.mkdir(parents=True, exist_ok=True)
        urls = [g["wtr_url"] for g in entry["selected"]]
        todo = [u for u in urls if not (pass_dir / u.rsplit("/", 1)[-1]).exists()]
        if todo:
            earthaccess.download(todo, local_path=str(pass_dir), threads=1, show_progress=False)
        entry["files"] = [(pass_dir / u.rsplit("/", 1)[-1]).relative_to(site_dir).as_posix() for u in urls]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fetch, index))
    complete = [e for e in index if all((site_dir / f).exists() for f in e.get("files", []))]
    out = site_dir / "index.json"
    out.write_text(json.dumps(complete, indent=1), encoding="utf-8")
    return out
