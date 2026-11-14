"""A fake stack in exactly the format pipeline.stack writes, for testing before real data.

Same layout as data/stack/<site>_<stack>.nc: HH and HV in linear power (NaN
where not valid), valid, looks, per-date granule_ur / crid / maturity / pols,
CRS and transform written with rioxarray. Plus a `truth` (y, x) class map.

It also copies the awkward parts of the real stacks: sea along the east edge,
one HH-only date (HV all NaN, like 2026-09-22 on 058 A) and a last date from a
newer processing release with a +1.5 dB calibration step.

The class signatures are rough L-band shapes from RESEARCH.md section 5, not
measurements. The file is tagged synthetic=1; never publish results from it.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from rasterio.transform import from_origin

from . import config

# Albufera, track 066 D frame 069: 10 provisional dates + the first validated one.
ALBUFERA_066D_DATES = [
    "2026-06-18", "2026-06-30", "2026-07-12", "2026-07-24", "2026-08-17",
    "2026-08-29", "2026-09-10", "2026-09-22", "2026-10-04", "2026-10-16", "2026-10-28",
]
FIRE_DATE = np.datetime64("2026-07-25")  # Serra d'Espadà fire start
SEA = -1  # truth value for sea pixels (not a class)


def _signature(name: str, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean HH and HV in dB per date for one class."""
    doy = (times.astype("datetime64[D]") - np.datetime64("2026-01-01")).astype(int)
    n = times.size
    if name == "rice_paddy":
        # Flooded young rice, canopy peak in August, harvest in September,
        # then the winter flooding (perellona) in October.
        knots = [168, 200, 230, 255, 270, 290, 301]
        hh = np.interp(doy, knots, [-15, -9, -6, -8, -14, -20, -21])
        hv = np.interp(doy, knots, [-24, -17, -14, -16, -22, -27, -28])
    elif name in ("permanent_water", "sea"):
        hh, hv = np.full(n, -22.0), np.full(n, -28.0)
        hh[n // 3] += 7.0  # one windy date: water looks bright
    elif name == "urban":
        hh, hv = np.full(n, -3.0), np.full(n, -11.0)
    elif name == "orchard":  # sparse tree rows: a bit darker than forest, mildly seasonal
        hh = -9.5 + 0.8 * np.sin(doy / 40.0)
        hv = -16.0 + 0.8 * np.sin(doy / 40.0)
    elif name == "forest":
        hh, hv = np.full(n, -8.0), np.full(n, -13.0)
    elif name == "burned":
        after = times >= FIRE_DATE
        hh = np.where(after, -10.5, -8.0)
        hv = np.where(after, -19.0, -13.0)
    else:  # other_crops_shrub: dry, mildly seasonal
        hh = -11.0 + 1.5 * np.sin(doy / 30.0)
        hv = -18.0 + 1.0 * np.sin(doy / 30.0)
    return np.asarray(hh, float), np.asarray(hv, float)


def make_stack(
    size: int = 300, parcel_px: int = 15, looks: int = 10, seed: int = config.SEED,
    dates: list[str] = ALBUFERA_066D_DATES, hh_only_index: int | None = 7,
    sea_cols: int = 30, new_release_step_db: float = 1.5,
) -> xr.Dataset:
    rng = np.random.default_rng(seed)
    times = np.array(dates, dtype="datetime64[ns]")
    t = times.size

    # Parcels of random class, a lagoon, a burn scar over some forest, sea on the east.
    n_par = (size + parcel_px - 1) // parcel_px
    weights = np.array([0.30, 0.0, 0.12, 0.15, 0.0, 0.28, 0.15])  # last: orchard
    parcel_cls = rng.choice(len(config.CLASSES), size=(n_par, n_par), p=weights)
    truth = np.kron(parcel_cls, np.ones((parcel_px, parcel_px), int))[:size, :size]
    yy, xx = np.mgrid[:size, :size]
    truth[(yy - size * 0.3) ** 2 + (xx - size * 0.3) ** 2 < (size * 0.15) ** 2] = config.CLASS_INDEX["permanent_water"]
    scar = (yy - size * 0.75) ** 2 / 2 + (xx - size * 0.6) ** 2 < (size * 0.15) ** 2
    truth[scar & (truth == config.CLASS_INDEX["forest"])] = config.CLASS_INDEX["burned"]
    if sea_cols:
        truth[:, -sea_cols:] = SEA

    tile = np.ones((parcel_px, parcel_px))
    offset_hh = np.kron(rng.normal(0, 1.0, (n_par, n_par)), tile)[:size, :size]
    offset_hv = np.kron(rng.normal(0, 1.0, (n_par, n_par)), tile)[:size, :size]

    hh_db = np.empty((t, size, size))
    hv_db = np.empty((t, size, size))
    for c, name in [(i, n) for i, n in enumerate(config.CLASSES)] + [(SEA, "sea")]:
        m = truth == c
        s_hh, s_hv = _signature(name, times)
        hh_db[:, m] = s_hh[:, None] + offset_hh[m]
        hv_db[:, m] = s_hv[:, None] + offset_hv[m]

    # Multilooked speckle: gamma noise on linear power.
    hh = (10 ** (hh_db / 10) * rng.gamma(looks, 1.0 / looks, hh_db.shape)).astype(np.float32)
    hv = (10 ** (hv_db / 10) * rng.gamma(looks, 1.0 / looks, hv_db.shape)).astype(np.float32)

    crids = ["P05023"] * t
    maturity = ["PROVISIONAL"] * t
    if new_release_step_db:
        crids[-1], maturity[-1] = "P05036", "VALIDATED"
        hh[-1] *= 10 ** (new_release_step_db / 10)
        hv[-1] *= 10 ** (new_release_step_db / 10)

    valid = rng.random((t, size, size)) > 0.02
    valid[3, :, : size // 10] = False  # a date that misses the west edge
    hh[~valid] = np.nan
    hv[~valid] = np.nan
    pols = ["HH+HV"] * t
    if hh_only_index is not None:
        hv[hh_only_index] = np.nan
        pols[hh_only_index] = "HH"

    pixel = 20.0
    transform = from_origin(725_000.0, 4_365_000.0, pixel, pixel)
    x = transform.c + (np.arange(size) + 0.5) * pixel
    y = transform.f - (np.arange(size) + 0.5) * pixel
    stamps = [d.replace("-", "") + "T185318" for d in dates]
    dims = ("time", "y", "x")
    ds = xr.Dataset(
        {
            "HH": (dims, hh), "HV": (dims, hv),
            "valid": (dims, valid.astype(np.uint8)),
            "looks": (dims, np.full((t, size, size), float(looks), np.float32)),
            "granule_ur": (("time",), np.array(
                [f"NISAR_L2_PR_GCOV_000_066_D_069_2005_DHDH_M_{s}_{s}_{c}_N_F_J_001" for s, c in zip(stamps, crids)])),
            "crid": (("time",), np.array(crids)),
            "maturity": (("time",), np.array(maturity)),
            "pols": (("time",), np.array(pols)),
            "truth": (("y", "x"), truth.astype(np.int16)),
        },
        coords={"time": times, "y": y, "x": x},
        attrs={"site": "synthetic", "stack_id": "066_D_069", "synthetic": 1,
               "power_units": "gamma0, linear power", "note": "FAKE DATA for tests"},
    )
    return ds.rio.write_crs("EPSG:32630").rio.write_transform(transform)


def write_stack(ds: xr.Dataset, path: str | Path) -> Path:
    """Write like pipeline.stack does (h5netcdf, CRS kept)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, engine="h5netcdf")
    return path
