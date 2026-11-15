"""DANA "Adam": what the IFS 9 km runs of 13 and 14 October forecast for Pego-Oliva (raised on #29).

The alert replay (``fit``) starts at the 15 October run. This adds the two earlier runs, read the same
way (wettest 0.1 deg lattice point, ``rain.past_run``), with 7 forecast days so they reach 18-20 Oct.

    python -m pipeline.prediction.flood.early_runs

Writes data/prediction/flood/early_runs_pego_oliva.json.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone

from pipeline.config import DATA_DIR, get_site
from pipeline.prediction.flood import rain

RUNS = ("2026-10-13", "2026-10-14", "2026-10-15")


def main() -> int:
    site = get_site("pego_oliva")
    out = {"issued_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "site": "pego_oliva",
           "source": "Open-Meteo Single Runs API, ECMWF IFS 9 km, wettest lattice point of the site (rain.past_run)",
           "runs": []}
    for r in RUNS:
        run = rain.past_run(site, date.fromisoformat(r), days=7)
        mm = [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 1) for v in run["max_mm"]]
        out["runs"].append({"run": r, "dates": run["dates"], "max_mm": mm})
        print(r, dict(zip(run["dates"], mm)))
    path = DATA_DIR / "prediction" / "flood" / "early_runs_pego_oliva.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
