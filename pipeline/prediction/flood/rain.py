"""Daily rain per site from Open-Meteo (no key; data CC BY 4.0, credit Open-Meteo and ECMWF).

The same model is used for history, past runs and live forecasts, so a
threshold fitted on it means the same thing when it is applied:

- history: ECMWF IFS 9 km archive (``archive-api``, ``models=ecmwf_ifs``).
- past runs: the deterministic IFS run started on a given day (``single-runs-api``).
- live: the 51-member ECMWF IFS 0.25 deg ensemble (``ensemble-api``).

Rain is read on a 0.1 deg lattice of points inside the site box, and the site
value of a day is the **largest** point value: floods answer to the heaviest
local rain, and a grid cell already smooths extremes (AEMET measured 634 mm at
Pego in the Oct 2026 DANA, the IFS cell about 72 mm).
"""

from __future__ import annotations

from datetime import date
import math

import numpy as np
import requests

from pipeline.config import Site

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
SINGLE_RUN = "https://single-runs-api.open-meteo.com/v1/forecast"
ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
STEP_DEG = 0.1
TIMEOUT_S = 120


def points(site: Site, step: float = STEP_DEG) -> list[tuple[float, float]]:
    """(lat, lon) on a step-degree lattice covering the site box, edges included."""
    w, s, e, n = site.bbox
    lats = np.round(np.arange(math.floor(s / step) * step, n + step / 2, step), 3)
    lons = np.round(np.arange(math.floor(w / step) * step, e + step / 2, step), 3)
    return [(float(la), float(lo)) for la in lats if s - step / 2 <= la <= n + step / 2
            for lo in lons if w - step / 2 <= lo <= e + step / 2]


def _get(url: str, site: Site, **params) -> list[dict]:
    pts = points(site)
    params = {"latitude": ",".join(str(p[0]) for p in pts), "longitude": ",".join(str(p[1]) for p in pts),
              "daily": "precipitation_sum", "timezone": "GMT", **params}
    resp = requests.get(url, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else [data]


def _matrix(responses: list[dict], key: str = "precipitation_sum") -> tuple[list[str], np.ndarray]:
    """(days, values[point, day]) with NaN for missing values."""
    days = responses[0]["daily"]["time"]
    values = np.array([[np.nan if v is None else float(v) for v in r["daily"][key]] for r in responses])
    return days, values


def history(site: Site, start: str, end: str) -> dict:
    """Daily IFS rain per point between two dates; site value = max over points."""
    days, values = _matrix(_get(ARCHIVE, site, start_date=start, end_date=end, models="ecmwf_ifs"))
    return {"dates": days, "max_mm": np.nanmax(values, axis=0), "mean_mm": np.nanmean(values, axis=0),
            "points": len(values)}


def past_run(site: Site, run: date, days: int = 5) -> dict:
    """What the deterministic IFS run of one day (00 UTC) forecast; site value = max over points."""
    d, values = _matrix(_get(SINGLE_RUN, site, models="ecmwf_ifs", run=f"{run.isoformat()}T00:00", forecast_days=days))
    with np.errstate(all="ignore"):  # the first day of a run can be empty (accumulation starts at 00 UTC)
        daily = np.where(np.all(np.isnan(values), axis=0), np.nan, np.nanmax(np.nan_to_num(values, nan=-1), axis=0))
    return {"run": run.isoformat(), "dates": d, "max_mm": daily}


def ensemble(site: Site, days: int = 7) -> dict:
    """Live ensemble: values[member, day] = max over points for each member."""
    responses = _get(ENSEMBLE, site, models="ecmwf_ifs025", forecast_days=days)
    keys = sorted(k for k in responses[0]["daily"] if k.startswith("precipitation_sum"))
    members = []
    for key in keys:
        _, values = _matrix(responses, key)
        members.append(np.nanmax(values, axis=0))
    return {"dates": responses[0]["daily"]["time"], "members": np.array(members)}
