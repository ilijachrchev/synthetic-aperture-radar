"""New-flood labels from the water series, rain features, threshold fit and scores.

Label, per Sentinel-1 date (passes of one day averaged):
    baseline = median flooded ha over the previous BASELINE_DAYS (at least MIN_PRIOR dates)
    spread   = 1.4826 x MAD of those values (robust standard deviation, at least 1 ha)
    flooded  = value - baseline >= max(MIN_EXCESS_HA, K_SPREAD x spread)
    new      = flooded now and not flooded on the previous date
Dates whose previous date was already flooded are left out: the water is still
there from before, so the rain since the last pass did not cause it.

Rain feature, per date: the largest 3-day rain total ending on any day from the
previous date to the day before this one (no rain from the pass day itself, it
may fall after the pass). Dates more than MAX_GAP_DAYS after the previous one
are left out.

All numbers above are fixed before looking at any result.
"""

from __future__ import annotations

from datetime import date

import numpy as np

BASELINE_DAYS = 30
MIN_PRIOR = 3
MIN_EXCESS_HA = 50.0
K_SPREAD = 5.0
WINDOW_DAYS = 3
MAX_GAP_DAYS = 12
ALERT = {"amber": 0.1, "red": 0.5}   # share of ensemble members above the threshold (context only)
LIVE_DAYS = 3        # the alert looks at the first 3 forecast days (day 0 = the run day)
AMBER_FRACTION = 0.5 # amber from half the threshold
STORM_GAP_DAYS = 7   # alarms at one site less than this apart belong to one storm


def daily_values(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """(ordinal days, mean flooded ha) from usable pass rows."""
    by_day: dict[int, list[float]] = {}
    for r in rows:
        if str(r["usable"]).lower() in ("true", "1"):
            by_day.setdefault(date.fromisoformat(r["date"]).toordinal(), []).append(float(r["flooded_ha"]))
    days = np.array(sorted(by_day), dtype=int)
    return days, np.array([np.mean(by_day[d]) for d in days], dtype=float)


def label(days: np.ndarray, values: np.ndarray) -> list[dict]:
    out = []
    prev_flooded = None
    for i, (d, v) in enumerate(zip(days, values)):
        prior = values[(days >= d - BASELINE_DAYS) & (days < d)]
        if prior.size < MIN_PRIOR:
            out.append({"day": int(d), "value_ha": v, "baseline_ha": None, "excess_ha": None,
                        "flooded": None, "new_flood": None, "persisting": None})
            prev_flooded = None
            continue
        base = float(np.median(prior))
        spread = max(1.0, 1.4826 * float(np.median(np.abs(prior - base))))
        excess = v - base
        flooded = bool(excess >= max(MIN_EXCESS_HA, K_SPREAD * spread))
        out.append({"day": int(d), "value_ha": round(v, 2), "baseline_ha": round(base, 2),
                    "excess_ha": round(excess, 2), "flooded": bool(flooded),
                    "new_flood": bool(flooded and prev_flooded is False),
                    "persisting": bool(prev_flooded)})
        prev_flooded = flooded
    return out


def rolling_sum(rain_days: np.ndarray, rain: np.ndarray, window: int = WINDOW_DAYS) -> dict[int, float]:
    """window-day totals keyed by the last day; needs every day present."""
    lookup = dict(zip(rain_days.tolist(), rain.tolist()))
    out = {}
    for d in rain_days.tolist():
        vals = [lookup.get(d - k) for k in range(window)]
        if all(v is not None and np.isfinite(v) for v in vals):
            out[d] = float(sum(vals))
    return out


def rain_feature(day: int, prev_day: int, sums: dict[int, float]) -> float | None:
    vals = [sums[e] for e in range(prev_day, day) if e in sums]
    return max(vals) if vals else None


def samples(site: str, labels: list[dict], sums: dict[int, float]) -> list[dict]:
    """One sample per labelled date: rain feature and new-flood outcome (persisting floods left out)."""
    out = []
    for prev, cur in zip(labels, labels[1:]):
        if cur["flooded"] is None or cur["persisting"] or prev["flooded"] is None:
            continue
        if cur["day"] - prev["day"] > MAX_GAP_DAYS:
            continue
        r = rain_feature(cur["day"], prev["day"], sums)
        if r is None:
            continue
        out.append({"site": site, "date": date.fromordinal(cur["day"]).isoformat(),
                    "previous_date": date.fromordinal(prev["day"]).isoformat(),
                    "rain_3d_max_mm": round(float(r), 1), "excess_ha": float(cur["excess_ha"]),
                    "new_flood": int(cur["new_flood"])})
    return out


def contingency(pred: np.ndarray, obs: np.ndarray) -> dict:
    hits = int(np.sum(pred & obs)); misses = int(np.sum(~pred & obs))
    false_alarms = int(np.sum(pred & ~obs)); correct_neg = int(np.sum(~pred & ~obs))
    pod = hits / (hits + misses) if hits + misses else None
    pofd = false_alarms / (false_alarms + correct_neg) if false_alarms + correct_neg else None
    far = false_alarms / (hits + false_alarms) if hits + false_alarms else None
    return {"n": int(obs.size), "events": hits + misses, "hits": hits, "misses": misses,
            "false_alarms": false_alarms, "correct_negatives": correct_neg,
            "hit_rate": None if pod is None else round(pod, 3),
            "false_alarm_rate": None if pofd is None else round(pofd, 3),
            "false_alarm_ratio": None if far is None else round(far, 3),
            "peirce_skill": None if pod is None or pofd is None else round(pod - pofd, 3)}


def fit_threshold(rain: np.ndarray, obs: np.ndarray) -> float:
    """Rain threshold with the best Peirce skill (hit rate minus false alarm rate); ties go to the higher one."""
    obs = obs.astype(bool)
    if not obs.any() or obs.all():
        raise ValueError("Training needs both flood and no-flood samples")
    best, best_t = -np.inf, None
    for t in np.unique(rain[obs]):
        pss = contingency(rain >= t, obs)["peirce_skill"]
        if pss is not None and (pss > best or (pss == best and t > best_t)):
            best, best_t = pss, float(t)
    return best_t


def fit_logistic(rain: np.ndarray, obs: np.ndarray, l2: float = 1e-2, iters: int = 50) -> tuple[float, float]:
    """p(new flood) = sigmoid(a + b log1p(rain)); Newton steps with a small ridge penalty."""
    x = np.column_stack([np.ones(rain.size), np.log1p(rain)])
    y = obs.astype(float)
    w = np.zeros(2)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-x @ w))
        grad = x.T @ (p - y) + l2 * w
        hess = x.T @ (x * (p * (1 - p))[:, None]) + l2 * np.eye(2)
        w -= np.linalg.solve(hess, grad)
    return float(w[0]), float(w[1])


def probability(a: float, b: float, rain: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(a + b * np.log1p(rain))))


def brier(prob: np.ndarray, obs: np.ndarray, base_rate: float) -> dict:
    bs = float(np.mean((prob - obs) ** 2))
    ref = float(np.mean((base_rate - obs) ** 2))
    return {"brier": round(bs, 4), "brier_climatology": round(ref, 4),
            "brier_skill": None if ref == 0 else round(1 - bs / ref, 3)}


def deterministic_level(total_mm: float, threshold_mm: float) -> str:
    """The alert from one forecast: red at the threshold, amber from half of it."""
    if total_mm >= threshold_mm:
        return "red"
    return "amber" if total_mm >= AMBER_FRACTION * threshold_mm else "green"


def alert_rule_total(daily_mm: np.ndarray) -> float:
    """The quantity the alert uses: the 3-day total over the first LIVE_DAYS forecast days."""
    return max_window_total(np.nan_to_num(np.asarray(daily_mm, float))[:LIVE_DAYS])


def storms(rows: list[dict], gap_days: int = STORM_GAP_DAYS) -> list[dict]:
    """Group alarm samples (same site, dates less than gap_days apart) into storms."""
    out: list[dict] = []
    for r in sorted(rows, key=lambda r: (r["site"], r["date"])):
        day = date.fromisoformat(r["date"]).toordinal()
        last = out[-1] if out else None
        if last and last["site"] == r["site"] and day - last["_last"] < gap_days:
            last["dates"].append(r["date"]); last["_last"] = day
            last["max_rain_3d_mm"] = max(last["max_rain_3d_mm"], r["rain_3d_max_mm"])
            last["max_excess_ha"] = max(last["max_excess_ha"], r["excess_ha"])
            last["new_flood"] = last["new_flood"] or bool(r["new_flood"])
        else:
            out.append({"site": r["site"], "dates": [r["date"]], "_last": day,
                        "max_rain_3d_mm": r["rain_3d_max_mm"], "max_excess_ha": r["excess_ha"],
                        "new_flood": bool(r["new_flood"])})
    for s in out:
        del s["_last"]
    return out


def alert_level(share_above: float) -> str:
    if share_above >= ALERT["red"]:
        return "red"
    return "amber" if share_above >= ALERT["amber"] else "green"


def max_window_total(daily: np.ndarray, window: int = WINDOW_DAYS) -> float:
    """Largest window-day total in a forecast (shorter forecasts use their full length)."""
    w = min(window, daily.size)
    return float(max(daily[i:i + w].sum() for i in range(daily.size - w + 1)))
