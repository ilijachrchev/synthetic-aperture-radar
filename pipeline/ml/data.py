"""Read one shared stack (written by pipeline.stack) into what the ML model needs.

The stack keeps HH and HV in linear power with NaN where not valid; here they
become dB with NaN for "not seen". HV is checked on its own, so the HH-only
date of the 058 A stacks still gives HH information.

The newest date of the stacks comes from a newer processing release (CRID
P05036, VALIDATED). Ilija measured the step into it on stable urban pixels:
-0.10 to -0.34 dB in HH, inside normal 12-day changes (DATA.md), so every date
is kept by default. crid="majority" or a CRID name keeps only those dates.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pipeline.config import SITES, get_site
from pipeline.cv.data import grid_of, open_stack, to_db
from pipeline.stack import Grid, site_grid

PROVENANCE_VARS = ("granule_ur", "crid", "maturity", "pols")


@dataclass
class MLStack:
    site: str
    stack_id: str
    grid: Grid
    times: np.ndarray            # (t,) datetime64
    hh_db: np.ndarray            # (t, y, x) float32, NaN = not seen
    hv_db: np.ndarray
    provenance: list[dict]       # one dict per kept date
    dropped: list[dict] = field(default_factory=list)  # dates left out, with the reason
    synthetic: bool = False
    extra: dict[str, np.ndarray] = field(default_factory=dict)  # other (y, x) variables, e.g. truth

    @property
    def shape(self) -> tuple[int, int]:
        return self.grid.height, self.grid.width

    @property
    def dates(self) -> list[str]:
        return [str(np.datetime_as_string(t, unit="D")) for t in self.times]


def stack_path(site: str, stack_id: str, stack_dir: Path) -> Path:
    return stack_dir / f"{site}_{stack_id}.nc"


def load(path: str | Path, crid: str = "all") -> MLStack:
    """Load a stack. crid: "all" (default), "majority", or one CRID such as "P05023"."""
    ds = open_stack(path)
    for var in ("HH", "HV", "valid"):
        if var not in ds or ds[var].dims != ("time", "y", "x"):
            raise ValueError(f"{path}: {var} must exist with dims (time, y, x)")
    crs, transform, (h, w) = grid_of(ds)
    grid = Grid(crs, transform, w, h)
    site = str(ds.attrs.get("site", Path(path).stem))
    if site in SITES and site_grid(get_site(site)) != grid:
        raise ValueError(f"{path}: grid differs from site_grid({site!r}); rebuild the stack")

    rows = []
    for i, t in enumerate(ds["time"].values):
        row = {"date": str(np.datetime_as_string(t, unit="D"))}
        for name in PROVENANCE_VARS:
            if name in ds and ds[name].dims == ("time",):
                row[name] = str(ds[name].values[i])
        rows.append(row)

    keep = np.ones(len(rows), bool)
    dropped = []
    crids = [r.get("crid", "") for r in rows]
    # Applied even when the stack holds one release, so asking for a release it does not
    # have fails below instead of silently keeping every date.
    if crid != "all":
        wanted = Counter(crids).most_common(1)[0][0] if crid == "majority" else crid
        for i, c in enumerate(crids):
            if c != wanted:
                keep[i] = False
                dropped.append({**rows[i], "reason": f"CRID {c} differs from {wanted}"})
    if keep.sum() == 0:
        raise ValueError(f"{path}: no dates left after the CRID filter {crid!r}")

    valid = ds["valid"].values.astype(bool)[keep]
    hh = to_db(ds["HH"].values[keep])
    hv = to_db(ds["HV"].values[keep])
    hh[~valid] = np.nan
    hv[~valid] = np.nan
    extra = {v: ds[v].values for v in ds.data_vars if ds[v].dims == ("y", "x")}
    return MLStack(
        site=site,
        stack_id=str(ds.attrs.get("stack_id", "")),
        grid=grid,
        times=ds["time"].values[keep],
        hh_db=hh,
        hv_db=hv,
        provenance=[r for r, k in zip(rows, keep) if k],
        dropped=dropped,
        synthetic=bool(int(ds.attrs.get("synthetic", 0))),
        extra=extra,
    )
