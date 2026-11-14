"""Run the shared data steps in order, in one process: fetch, water labels, stacks.

    python -m pipeline.run               # fetch what is missing, then build every stack
    python -m pipeline.run --skip-fetch  # only rebuild the stacks from what is on disk

For every stack in config.STACKS (shared by the CV and ML models): fetch the
NISAR GCOV subsets through Harmony; then fetch the same-day Sentinel-1 water maps
for the sites in config.DSWX_LABEL_SITES; then build every stack and print a
summary. Fetch steps skip what is already on disk, so the command is safe to
re-run after an interruption. Everything runs one step after another in this
single process, so a stack is never built before its downloads have finished.

The fetch steps need the Earthdata login in your .netrc (see the README).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from pipeline import dswx, nisar_fetch, stack
from pipeline.config import DSWX_LABEL_SITES, STACKS, get_site
from pipeline.cv.data import open_stack


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def summarize(path: Path) -> str:
    """One line per stack: dates, grid size, valid share, HH-only dates, maturity."""
    ds = open_stack(path)
    days = [str(t)[:10] for t in ds["time"].values]
    hh_only = int(np.isnan(ds["HV"].values).all(axis=(1, 2)).sum())
    maturities = "+".join(sorted({str(m) for m in ds["maturity"].values}))
    return (f"{len(days)} dates {days[0]} to {days[-1]}, {ds.sizes['x']} x {ds.sizes['y']} px, "
            f"{float(ds['valid'].mean()):.1%} valid, {hh_only} HH-only date(s), {maturities}")


def run(skip_fetch: bool = False) -> list[tuple[str, str, str]]:
    if not skip_fetch:
        for site_name, stack_ids in STACKS.items():
            for stack_id in stack_ids:
                log(f"fetch NISAR {site_name} {stack_id}")
                nisar_fetch.fetch_stack(get_site(site_name), stack_id)
        for site_name in DSWX_LABEL_SITES:
            log(f"fetch DSWx-S1 water labels {site_name}")
            site = get_site(site_name)
            dswx.download(site, dswx.build_index(site, set(STACKS[site_name])))

    rows = []
    for site_name, stack_ids in STACKS.items():
        for stack_id in stack_ids:
            log(f"build stack {site_name} {stack_id}")
            path = stack.build_stack(get_site(site_name), stack_id)
            rows.append((site_name, stack_id, summarize(path)))
    log("done")
    for site_name, stack_id, text in rows:
        print(f"  {site_name} {stack_id}: {text}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-fetch", action="store_true", help="only rebuild the stacks from what is on disk")
    run(parser.parse_args().skip_fetch)


if __name__ == "__main__":
    main()
