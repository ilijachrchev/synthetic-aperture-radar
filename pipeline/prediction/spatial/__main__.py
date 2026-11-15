"""Where will the water go: local commands.

    python -m pipeline.prediction.spatial prepare   terrain layers and the Sentinel-1 label stack per site
    python -m pipeline.prediction.spatial train     development check, then the final model
    python -m pipeline.prediction.spatial predict   held-out October scores, replays and rain scenarios
    python -m pipeline.prediction.spatial nisar     the 28 Oct replays scored against the NISAR water maps (data/cv)
    python -m pipeline.prediction.spatial all       the four steps above for the base model

    train and predict take --variant: base (Sentinel-1 labels), soil (+ NISAR soil moisture as an input),
    nisar (+ NISAR water labels), nisar_soil (both), nisar_flag (NISAR labels plus two columns that say which
    radar a water map comes from). nisar also takes --variant. Only base writes maps; the others write scores to
    data/prediction/spatial/variants/<name>/.
    python -m pipeline.prediction.spatial compare   one table of the held-out scores of every trained variant
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone

import lightgbm as lgb
import numpy as np

import rasterio
from rasterio.warp import Resampling, reproject

from pipeline.config import DATA_DIR, get_site
from pipeline.ml.split import split_blocks
from pipeline.stack import site_grid

from . import HOLDOUT_END, HOLDOUT_START, SITES, export, features as F, labels, model as M, terrain
from .. import manifest as manifest_mod
from ..flood import rain as rain_mod

OUT = DATA_DIR / "prediction" / "spatial"
POOL_SIZE = 40_000
SCORE_SAMPLE = 200_000
REPLAY_DATES = ("2026-10-22", "2026-10-28")
SCENARIO_MM = (0, 50, 100, 200)
SCENARIO_LEAD_DAYS = 4
MANIFEST = DATA_DIR / "manifest.json"
CV_DIR = DATA_DIR / "cv"
NISAR_BEFORE, NISAR_AFTER = "2026-10-16", "2026-10-28"   # the NISAR passes on either side of the DANA
PRE_STORM = np.datetime64("2026-10-17T23:59:59")          # last moment before the rain of 18 and 19 Oct
NISAR_EXPORT_STACK = "066_D_069"                          # the track both sites share
# variant: (labels, soil moisture as an input, sensor columns)
VARIANTS = {"base": ("s1", False, False), "soil": ("s1", True, False), "nisar": ("s1+nisar", False, False),
            "nisar_soil": ("s1+nisar", True, False), "nisar_flag": ("s1+nisar", False, True)}
FORECAST_TARGET = "2026-10-22"                            # first Sentinel-1 pass after the DANA rain
STORM_DATES = ("2026-10-22", "2026-10-23")


def _vdir(variant):
    return OUT if variant == "base" else OUT / "variants" / variant


def _names(variant):
    return F.FEATURES + (F.SOIL if VARIANTS[variant][1] else ()) + (F.SENSOR if VARIANTS[variant][2] else ())


def _boosters(variant="base"):
    d = _vdir(variant)
    return {"rain_and_state": (lgb.Booster(model_file=str(d / "model.txt")), _names(variant)),
            "terrain_only": (lgb.Booster(model_file=str(d / "model_terrain_only.txt")), F.TERRAIN_ONLY)}


def _write_index(entries, replace):
    """Merge scenario entries into index.json (replace(e) says which old entries go) and refresh the manifest."""
    path = OUT / "index.json"
    old = json.loads(path.read_text(encoding="utf-8"))["scenarios"] if path.exists() else []
    scenarios = [e for e in old if not replace(e)] + entries
    sha = hashlib.sha256((OUT / "model.txt").read_bytes()).hexdigest()[:16]
    _json({"model_sha256_16": sha, "scenarios": scenarios}, path)
    today = datetime.now(timezone.utc)
    manifest_mod.upsert(MANIFEST, [{
        "model": "prediction", "site": name, "stack": "dswx-s1+open-meteo-ifs", "layer": "water_likelihood",
        "date": today.date().isoformat(), "id": f"prediction-water-likelihood-{name}",
        "file": "data/prediction/spatial/index.json", "metrics": "data/prediction/spatial/holdout_s1_metrics.json",
        "schema": "data/prediction/spatial/feature_schema.json", "source_type": "dswx-s1 + open-meteo + terrain",
        "units": "relative water likelihood 0-1 (web copies 0-100, 255 no data)", "model_sha256_16": sha,
        "scenarios": [{k: e[k] for k in ("scenario_id", "mode", "dir")} for e in scenarios if e["site"] == name],
        "issued_at_utc": today.isoformat(timespec="seconds"),
    } for name in SITES])


def _json(obj, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _site(name, label_set="s1"):
    """Everything fixed about a site: stack, passes, static layers, past wet counts over the fit passes."""
    stack, passes = labels.load_set(name, label_set)
    static = F.load_static(name)
    days = [p["date"] for p in passes]
    fit = np.array([not F.in_holdout(d) for d in days])
    cache = terrain.static_dir(name) / ("counts.npz" if label_set == "s1" else "counts_s1_nisar.npz")
    if cache.exists():
        c = np.load(cache)
        wet, obs = c["wet"], c["obs"]
    else:
        wet, obs = F.counts(lambda k: labels.to_water(np.asarray(stack[k])), len(passes), fit, stack.shape[1:])
        np.savez_compressed(cache, wet=wet, obs=obs)
    return {"name": name, "stack": stack, "passes": passes, "days": days, "times": labels.pass_times(passes),
            "is_nisar": np.array([p.get("platform") == "NISAR" for p in passes]), "static": static, "fit": fit, "wet": wet, "obs": obs, "grid": site_grid(get_site(name)),
            "rain": F.load_rain(name)}


def prepare(_args):
    report = {}
    for name in SITES:
        site = get_site(name)
        grid = site_grid(site)
        report[name] = {"terrain": terrain.prepare(site, grid)}
        passes = labels.build(name, grid)
        for cache in ("counts.npz", "counts_s1_nisar.npz"):
            (terrain.static_dir(name) / cache).unlink(missing_ok=True)
        report[name]["passes"] = len(passes)
        report[name]["first"], report[name]["last"] = passes[0]["date"], passes[-1]["date"]
        print(name, report[name], flush=True)
    _json(report, terrain.INTERIM / "prepare.json")


def train(args):
    variant = getattr(args, "variant", "base")
    label_set, use_soil, _ = VARIANTS[variant]
    out, full = _vdir(variant), _names(variant)
    rng = np.random.default_rng(M.SEED)
    parts, manifest = [], {}
    for name in SITES:
        s = _site(name, label_set)
        domain = F.train_domain(s["static"])
        pool, pool_w = F.pick_pool(domain, s["wet"], s["obs"], POOL_SIZE, rng, n_fit=int(s["fit"].sum()))
        pool_water = np.stack([labels.to_water(np.asarray(s["stack"][k]).ravel()[pool]) for k in range(len(s["passes"]))])
        tab = F.build_table(pool_water, s["times"], s["days"], F.static_columns(s["static"], pool), pool_w, s["rain"], rng,
                            soil=F.soil_reader(name, pool) if use_soil else None, is_nisar=s["is_nisar"])
        train_blocks, val_blocks = split_blocks(domain.shape)
        late = np.array([d >= M.DEV_SPLIT for d in s["days"]])[tab["t"]]
        tab["dev_train"] = ~late & train_blocks.ravel()[pool][tab["p"]]
        tab["dev_val"] = late & val_blocks.ravel()[pool][tab["p"]]
        tab["site"] = np.full(tab["y"].size, SITES.index(name), "int8")
        parts.append(tab)
        used = sorted(set(tab["t"].tolist()))
        between = [F.rain_features(s["rain"], date.fromisoformat(s["days"][F.issue_index(s["times"], t)]).toordinal(),
                                   date.fromisoformat(s["days"][t]).toordinal())["rain_between_mm"] for t in used]
        manifest[name] = {
            "passes_in_index": len(s["passes"]), "target_passes_used": len(used),
            "first_target": s["days"][used[0]], "last_target": s["days"][used[-1]],
            "held_out_passes": int((~s["fit"]).sum()), "pool_pixels": int(pool.size),
            "domain_ha": round(float(domain.sum()) * export.PIXEL_HA, 1), "samples": int(tab["y"].size),
            "wet_samples": int(tab["y"].sum()),
            "nisar_target_passes": int(sum(s["passes"][t].get("platform") == "NISAR" for t in used)),
            "samples_with_soil_moisture": int(np.isfinite(tab["X"][:, F.ALL.index("soil_moisture")]).sum()),
            "rain_between_mm": {"max": round(float(np.nanmax(between)), 1), "p99": round(float(np.nanpercentile(between, 99)), 1),
                                "p90": round(float(np.nanpercentile(between, 90)), 1),
                                "targets_over_100mm": int(np.sum(np.array(between) >= 100))},
            "label_granules_sha256": hashlib.sha256("\n".join(g for p in s["passes"] for g in p["granules"]).encode()).hexdigest(),
        }
        print(name, manifest[name], flush=True)
    T = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    X, y, w = T["X"], T["y"], T["w"]
    tr, va = T["dev_train"], T["dev_val"]
    new_cand = X[:, F.FEATURES.index("prev_water")] == 0

    dev, rounds = {}, {}
    scores = M.baselines(X[va])
    for label, names in (("terrain_only", F.TERRAIN_ONLY), ("rain_and_state", full)):
        b = M.fit(X[tr], y[tr], w[tr], names, valid=(X[va], y[va], w[va]))
        rounds[label] = int(b.best_iteration)
        scores[label] = M.predict(b, X[va], names)
    thresholds = {k: {"water": M.best_threshold(y[va], s, w[va]),
                      "new_water": M.best_threshold(y[va][new_cand[va]], s[new_cand[va]], w[va][new_cand[va]])}
                  for k, s in scores.items() if k != "persistence"}
    dev["both_sites"] = M.score_all(y[va], w[va], scores, new_cand[va], thresholds)
    for i, name in enumerate(SITES):
        m = T["site"][va] == i
        dev[name] = M.score_all(y[va][m], w[va][m], {k: v[m] for k, v in scores.items()}, new_cand[va][m], thresholds)

    out.mkdir(parents=True, exist_ok=True)
    importance = {}
    for label, names, fname in (("terrain_only", F.TERRAIN_ONLY, "model_terrain_only.txt"), ("rain_and_state", full, "model.txt")):
        b = M.fit(X, y, w, names, rounds=rounds[label])
        b.save_model(str(out / fname))
        gain = b.feature_importance("gain")
        importance[label] = {n: round(float(g / gain.sum()), 4) for n, g in sorted(zip(names, gain), key=lambda x: -x[1])}
    _json({"variant": variant, "features": list(full), "terrain_only_features": list(F.TERRAIN_ONLY), "categorical": list(F.CATEGORICAL),
           "units": F.UNITS, "target": "water (DSWx-S1 class 1 or 3) at the target pass; 0 = class 0; other classes are not used",
           "timing": {"min_lead_days": F.MIN_LEAD_DAYS, "max_lead_days": F.MAX_LEAD_DAYS, "max_observation_age_days": F.MAX_OBS_AGE_DAYS,
                      "rule": "issue pass = latest pass at least min_lead_days before the target; rain 'between' is realized rain in fits and replays"},
           "grid": "pipeline.stack.site_grid, EPSG:32630, 20 m"}, out / "feature_schema.json")
    _json({"made_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "holdout": {"start": HOLDOUT_START, "end": HOLDOUT_END, "sites": list(SITES)},
           "variant": variant,
           "labels": "OPERA DSWx-S1 B01_WTR, newest reprocessing per tile, data/raw/dswx_history"
                     + ("; plus the team's NISAR water labels, data/labels_nisar (open water wet, water under plants unknown)"
                        if label_set != "s1" else ""),
           "soil_moisture": "NISAR SME2 (data/context/<site>_sme2_*), newest map before the issue day" if use_soil else None,
           "sampling": {"pool_size_per_site": POOL_SIZE, "pool": "half ever-wet, half never-wet pixels, weighted back to the domain",
                        "dry_keep": 0.1, "seed": M.SEED},
           "domain": "land, not JRC permanent water, not WorldCover built-up, with HAND, seen in at least half of the passes",
           "params": M.PARAMS, "rounds": rounds, "sites": manifest}, out / "training_manifest.json")
    _json({"split": {"train": f"targets before {M.DEV_SPLIT} on training blocks", "check": f"targets from {M.DEV_SPLIT} to the held-out window on held-back 1 km blocks",
                     "n_train": int(tr.sum()), "n_check": int(va.sum())},
           "reading": "water_ap / new_water_ap = weighted average precision; new water = samples that were dry at the issue pass. "
                      "Persistence cannot rank new water (its score there is constant), so past_wet_share is the fair comparison.",
           "thresholds": thresholds, "scores": dev, "importance_gain_share": importance}, out / "development_metrics.json")
    for k, v in dev["both_sites"]["methods"].items():
        print(f"dev {k:16s} water AP {v['water_ap']}  new-water AP {v['new_water_ap']}")
    print("rounds", rounds)


def _predict_pass(s, idx, static_cols, freq, boosters, issue_j, target_time, target_day, lead, rain_feats, soil=None,
                  target_nisar=False):
    get = lambda k: labels.to_water(np.asarray(s["stack"][k]).ravel()[idx])
    src = np.empty(idx.size, dtype="int64")
    state, age = F.prev_state(get, s["times"], issue_j, target_time, idx.size, source=src)
    prev_nisar = np.where(src >= 0, s["is_nisar"][np.maximum(src, 0)], False)
    sm, sm_age = soil(s["days"][issue_j], date.fromordinal(target_day).isoformat()) if soil is not None else (None, None)
    X = F.assemble(static_cols, freq, target_day, lead, rain_feats, state, age, sm, sm_age, target_nisar, prev_nisar)
    out = {name: M.predict(b, X, names) for name, (b, names) in boosters.items()}
    out.update(M.baselines(X))
    return out, state


def _forecast_rain(name, run_day, n_days):
    """Daily site rain the IFS run of run_day (00 UTC) forecast for its first n_days, cached in ifs_runs.json."""
    path = OUT / "ifs_runs.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    key = f"{name}/{run_day.isoformat()}/{n_days}"
    if key not in cache:
        run = rain_mod.past_run(get_site(name), run_day, days=n_days)
        cache[key] = {"run": run["run"] + "T00:00Z", "dates": list(run["dates"]),
                      "max_mm": [None if not np.isfinite(v) else round(float(v), 1) for v in run["max_mm"]],
                      "source": "Open-Meteo Single Runs API, ECMWF IFS 9 km, wettest lattice point of the site"}
        _json(cache, path)
    return cache[key]


def predict(args):
    variant = getattr(args, "variant", "base")
    label_set, use_soil, _ = VARIANTS[variant]
    vdir, primary = _vdir(variant), variant == "base"
    dev = json.loads((vdir / "development_metrics.json").read_text(encoding="utf-8"))
    thresholds = dev["thresholds"]
    manifest = json.loads((vdir / "training_manifest.json").read_text(encoding="utf-8"))
    model_sha = hashlib.sha256((vdir / "model.txt").read_bytes()).hexdigest()[:16]
    boosters = _boosters(variant)
    rng = np.random.default_rng(M.SEED + 1)
    report, index = {}, []
    for name in SITES:
        s = _site(name, label_set)
        st, grid = s["static"], s["grid"]
        shape = (grid.height, grid.width)
        idx = np.flatnonzero((st["land"] & np.isfinite(st["hand_m"])).ravel())
        soil = F.soil_reader(name, idx) if use_soil else None
        static_cols = F.static_columns(st, idx)
        freq = F.wet_frequency(s["wet"].ravel()[idx], s["obs"].ravel()[idx])
        scoring = F.train_domain(st).ravel()[idx]
        sample = np.zeros(idx.size, bool)
        sample[rng.choice(np.flatnonzero(scoring), size=min(SCORE_SAMPLE, int(scoring.sum())), replace=False)] = True
        per_pass, pooled = [], {"y": [], "new": [], "s": {}}
        common = {"site": name, "model": "spatial water likelihood (LightGBM)", "model_sha256_16": model_sha,
                  "rain_source": "Open-Meteo, ECMWF IFS 9 km, wettest lattice point of the site per day",
                  "holdout": {"start": HOLDOUT_START, "end": HOLDOUT_END},
                  "validation_status": "retrospective check on the held-out October 2026 window against Sentinel-1 maps; "
                                       "not yet scored against Copernicus EMSR935"}
        for t in np.flatnonzero(~s["fit"]):
            j = F.issue_index(s["times"], t)
            if j is None or s["passes"][t].get("platform") == "NISAR":
                continue                  # every variant is scored on the same Sentinel-1 target passes
            target_day = date.fromisoformat(s["days"][t]).toordinal()
            rf = F.rain_features(s["rain"], date.fromisoformat(s["days"][j]).toordinal(), target_day)
            lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
            scores, state = _predict_pass(s, idx, static_cols, freq, boosters, j, s["times"][t], target_day, lead, rf, soil)
            lab = labels.to_water(np.asarray(s["stack"][t]).ravel()[idx])
            ok = scoring & (lab != labels.UNKNOWN)
            y, w1 = lab[ok], np.ones(int(ok.sum()), "float32")
            row = {"pass_id": s["passes"][t]["pass_id"], "date": s["days"][t], "issue_pass": s["passes"][j]["pass_id"],
                   "soil_moisture_share": round(float(np.isfinite(soil(s["days"][j], s["days"][t])[0]).mean()), 3)
                   if soil is not None and soil(s["days"][j], s["days"][t])[0] is not None else 0.0,
                   "lead_days": round(lead, 2), **{k: round(v, 1) for k, v in rf.items()},
                   "observed_water_ha": round(float(y.sum()) * export.PIXEL_HA, 1),
                   "observed_new_water_ha": round(float(((state[ok] == 0) & (y == 1)).sum()) * export.PIXEL_HA, 1),
                   "scored_share_of_domain": round(float(ok.sum() / scoring.sum()), 3),
                   **M.score_all(y, w1, {k: v[ok] for k, v in scores.items()}, state[ok] == 0, thresholds)}
            per_pass.append(row)
            m = ok & sample
            pooled["y"].append(lab[m]); pooled["new"].append(state[m] == 0)
            for k, v in scores.items():
                pooled["s"].setdefault(k, []).append(v[m].astype("float32"))
            if primary and s["days"][t] in REPLAY_DATES and not any(e["site"] == name and e["target_date"] == s["days"][t] for e in index):
                sid = f"replay_{s['days'][t]}"
                ev = export.evidence(st, freq, state, idx, shape)
                doc = export.write(OUT / name / sid, grid, scores["rain_and_state"], state, ev, idx,
                                   {**common, "scenario_id": sid, "mode": "reconstruction",
                                    "mode_note": "rain between issue and target is the rain that fell (IFS archive), not a forecast",
                                    "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                                    "target_pass": s["passes"][t]["pass_id"], "target_time_utc": s["passes"][t]["begin_utc"],
                                    "lead_days": round(lead, 2), "rain": rf,
                                    "check_against_sentinel1": {k: row["methods"][k] for k in ("rain_and_state", "terrain_only", "past_wet_share")}},
                                   thresholds["rain_and_state"])
                index.append({"site": name, "scenario_id": sid, "mode": "reconstruction", "target_date": s["days"][t],
                              "dir": f"data/prediction/spatial/{name}/{sid}", "area_ha": doc["area_ha"]})
            print(name, row["date"], row["pass_id"][-3:], "rain", row["rain_between_mm"], "new-water AP",
                  {k: v["new_water_ap"] for k, v in row["methods"].items()}, flush=True)
        y = np.concatenate(pooled["y"]); new = np.concatenate(pooled["new"])
        report[name] = {"pooled_over_held_out_passes": M.score_all(
            y, np.ones(y.size, "float32"), {k: np.concatenate(v) for k, v in pooled["s"].items()}, new, thresholds),
            "pooled_note": f"a fixed random sample of {int(sample.sum())} domain pixels per pass", "passes": per_pass}
        if not primary:
            continue

        # the same storm replay, but with the rain the IFS run of the issue day forecast (a real forecast input)
        t = next(i for i, d in enumerate(s["days"]) if d == FORECAST_TARGET)
        j = F.issue_index(s["times"], t)
        issue_day, target_day = (date.fromisoformat(s["days"][k]).toordinal() for k in (j, t))
        run = _forecast_rain(name, date.fromordinal(issue_day), target_day - issue_day)
        rain_fc = dict(s["rain"])
        # the run gives no daily total for its own first day; counted as 0 mm, as pipeline.prediction.flood does
        rain_fc.update({date.fromisoformat(d).toordinal(): (0.0 if v is None else v) for d, v in zip(run["dates"], run["max_mm"])})
        rf_real, rf = F.rain_features(s["rain"], issue_day, target_day), F.rain_features(rain_fc, issue_day, target_day)
        lead = float((s["times"][t] - s["times"][j]) / np.timedelta64(1, "D"))
        scores, state = _predict_pass(s, idx, static_cols, freq, boosters, j, s["times"][t], target_day, lead, rf)
        lab = labels.to_water(np.asarray(s["stack"][t]).ravel()[idx])
        ok = scoring & (lab != labels.UNKNOWN)
        check = M.score_all(lab[ok], np.ones(int(ok.sum()), "float32"), {k: v[ok] for k, v in scores.items()}, state[ok] == 0, thresholds)
        sid = f"forecast_{FORECAST_TARGET}"
        doc = export.write(OUT / name / sid, grid, scores["rain_and_state"], state, export.evidence(st, freq, state, idx, shape), idx,
                           {**common, "scenario_id": sid, "mode": "forecast",
                            "mode_note": "rain between issue and target is what the ECMWF IFS run of the issue day (00 UTC) forecast, "
                                         "not what fell; the rain before the issue day and the water map are observations. "
                                         "The run has no daily total for its own first day, which counts as 0 mm",
                            "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                            "target_pass": s["passes"][t]["pass_id"], "target_time_utc": s["passes"][t]["begin_utc"],
                            "lead_days": round(lead, 2), "rain": rf, "ifs_run": run, "rain_that_fell": rf_real,
                            "check_against_sentinel1": {k: check["methods"][k] for k in ("rain_and_state", "terrain_only", "past_wet_share")}},
                           thresholds["rain_and_state"])
        index.append({"site": name, "scenario_id": sid, "mode": "forecast", "target_date": FORECAST_TARGET,
                      "dir": f"data/prediction/spatial/{name}/{sid}", "area_ha": doc["area_ha"]})
        report[name]["forecast_replay"] = {"scenario_id": sid, "ifs_run": run["run"], "lead_days": round(lead, 2),
                                           "forecast_rain_between_mm": rf["rain_between_mm"], "rain_that_fell_mm": rf_real["rain_between_mm"],
                                           "area_ha": doc["area_ha"], **check}
        print(name, sid, "forecast rain", rf["rain_between_mm"], "fell", rf_real["rain_between_mm"],
              "new-water AP", check["methods"]["rain_and_state"]["new_water_ap"], doc["area_ha"], flush=True)

        # rain scenarios from the latest water map
        j = len(s["passes"]) - 1
        issue_day = date.fromisoformat(s["days"][j]).toordinal()
        target_day = issue_day + SCENARIO_LEAD_DAYS
        target_time = s["times"][j] + np.timedelta64(SCENARIO_LEAD_DAYS, "D")
        base = F.rain_features(s["rain"], issue_day, issue_day)   # only the prior rain is real
        top = manifest["sites"][name]["rain_between_mm"]
        for mm in SCENARIO_MM:
            rf = {**base, "rain_between_mm": float(mm), "rain_between_max1d_mm": mm * 0.6, "days_since_rain_peak": 2.0}
            scores, state = _predict_pass(s, idx, static_cols, freq, boosters, j, target_time, target_day, float(SCENARIO_LEAD_DAYS), rf)
            sid = f"scenario_{mm:03d}mm"
            ev = export.evidence(st, freq, state, idx, shape)
            doc = export.write(OUT / name / sid, grid, scores["rain_and_state"], state, ev, idx,
                               {**common, "scenario_id": sid, "mode": "scenario",
                                "mode_note": f"hypothetical: {mm} mm at the wettest point of the site over the {SCENARIO_LEAD_DAYS} days after the "
                                             "latest water map, 60 % of it on one day, two days before the target",
                                "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                                "target_time_utc": str(target_time) + "Z", "lead_days": float(SCENARIO_LEAD_DAYS), "rain": rf,
                                "rain_seen_in_training": {**top, "inside_training_range": bool(mm <= top["max"])}},
                               thresholds["rain_and_state"])
            index.append({"site": name, "scenario_id": sid, "mode": "scenario", "rain_mm": mm,
                          "dir": f"data/prediction/spatial/{name}/{sid}", "area_ha": doc["area_ha"]})
            print(name, sid, doc["area_ha"], flush=True)
    _json({"reading": "Held-out October 2026 passes scored against the Sentinel-1 map of the same pass, on the training domain. "
                      "This is the model's own retrospective check. The independent test against EMSR935 is separate.",
           "variant": variant, "thresholds_frozen_from": "development_metrics.json", "sites": report}, vdir / "holdout_s1_metrics.json")
    if not primary:
        return
    for name in SITES:   # the terrain layer Luka's lowest-ground baseline needs, small enough to commit
        hand = np.round(F.load_static(name)["hand_m"], 1)
        export._float_tif(hand, site_grid(get_site(name)), OUT / name / "static" / "hand_m.tif", decimals=1)
    _write_index(index, lambda e: not e["scenario_id"].endswith("_prestorm"))   # keep what the nisar step wrote


def _cv_on_grid(path, grid):
    """A data/cv water map (Web Mercator) on the site grid, nearest neighbour, as 0 dry / 1 water / 255 unknown.

    Class 2 (flooded vegetation, written by three-class exports) counts as water; any other code is unknown.
    """
    out = np.full((grid.height, grid.width), 255, dtype="uint8")
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=out, src_nodata=255, dst_transform=grid.transform,
                  dst_crs=grid.crs, dst_nodata=255, resampling=Resampling.nearest)
    out[out == 2] = 1
    out[(out != 0) & (out != 1)] = 255
    return out


def nisar(args):
    """Score replays of 28 Oct 2026 against the NISAR water map of that pass, issued before and after the storm."""
    variant = getattr(args, "variant", "base")
    label_set, _, sensor = VARIANTS[variant]
    vdir, primary = _vdir(variant), variant == "base"
    dev = json.loads((vdir / "development_metrics.json").read_text(encoding="utf-8"))
    thresholds = dev["thresholds"]
    boosters = _boosters(variant)
    cv_entries = {(e["site"], e["stack"], e["date"]): e for e in manifest_mod.read(MANIFEST)
                  if e.get("model") == "cv" and e.get("layer") == "water"}
    report, index = {}, []
    for name in SITES:
        s = _site(name, label_set)
        st, grid = s["static"], s["grid"]
        idx = np.flatnonzero((st["land"] & np.isfinite(st["hand_m"])).ravel())
        static_cols = F.static_columns(st, idx)
        freq = F.wet_frequency(s["wet"].ravel()[idx], s["obs"].ravel()[idx])
        domain = F.train_domain(st).ravel()[idx]
        for (site, stack, day), entry in sorted(cv_entries.items()):
            before = cv_entries.get((name, stack, NISAR_BEFORE))
            if site != name or day != NISAR_AFTER or before is None:
                continue
            stamp = entry["source"]["granule_ur"].split("_")[-7]           # start of the acquisition, e.g. 20261028T185318
            target_time = np.datetime64(f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:11]}:{stamp[11:13]}:{stamp[13:15]}")
            target_day = date.fromisoformat(NISAR_AFTER).toordinal()
            after_map = _cv_on_grid(DATA_DIR.parent / entry["file"], grid).ravel()[idx]
            before_map = _cv_on_grid(DATA_DIR.parent / before["file"], grid).ravel()[idx]
            ok = domain & (after_map != 255) & (before_map != 255)
            y = after_map[ok]
            nisar_dry_before = before_map[ok] == 0
            w1 = np.ones(y.size, "float32")
            runs = {}
            for label, not_after in (("issued_before_storm", PRE_STORM), ("issued_after_storm", None)):
                j = F.issue_before(s["times"], target_time, not_after=not_after)
                if j is None:
                    continue
                rf = F.rain_features(s["rain"], date.fromisoformat(s["days"][j]).toordinal(), target_day)
                lead = float((target_time - s["times"][j]) / np.timedelta64(1, "D"))
                scores, state = _predict_pass(s, idx, static_cols, freq, boosters, j, target_time, target_day, lead, rf,
                                              target_nisar=sensor)   # with sensor columns: predict what NISAR will see
                runs[label] = {"issue_pass": s["passes"][j]["pass_id"], "lead_days": round(lead, 2),
                               **{k: round(v, 1) for k, v in rf.items()},
                               **M.score_all(y, w1, {k: v[ok] for k, v in scores.items()}, nisar_dry_before, thresholds)}
                if primary and label == "issued_before_storm" and stack == NISAR_EXPORT_STACK:
                    sid = f"replay_{NISAR_AFTER}_prestorm"
                    doc = export.write(OUT / name / sid, grid, scores["rain_and_state"], state,
                                       export.evidence(st, freq, state, idx, (grid.height, grid.width)), idx,
                                       {"site": name, "model": "spatial water likelihood (LightGBM)", "scenario_id": sid,
                                        "mode": "reconstruction",
                                        "mode_note": "issued from the last Sentinel-1 map before the rain of 18 and 19 Oct, for the NISAR "
                                                     "pass of 28 Oct; the rain in between is the rain that fell (IFS archive), not a forecast",
                                        "issued_from_pass": s["passes"][j]["pass_id"], "issue_time_utc": s["passes"][j]["begin_utc"],
                                        "target_time_utc": str(target_time) + "Z", "target_nisar_granule": entry["source"]["granule_ur"],
                                        "lead_days": round(lead, 2), "rain": rf,
                                        "rain_source": "Open-Meteo, ECMWF IFS 9 km, wettest lattice point of the site per day",
                                        "holdout": {"start": HOLDOUT_START, "end": HOLDOUT_END},
                                        "validation_status": "checked against the NISAR water map of the target pass, see nisar_check.json"},
                                       thresholds["rain_and_state"])
                    index.append({"site": name, "scenario_id": sid, "mode": "reconstruction", "target_date": NISAR_AFTER,
                                  "dir": f"data/prediction/spatial/{name}/{sid}", "area_ha": doc["area_ha"]})
            report.setdefault(name, {})[stack] = {
                "nisar_after": entry["file"], "nisar_before": before["file"], "target_time_utc": str(target_time) + "Z",
                "scored_ha": round(float(ok.sum()) * export.PIXEL_HA, 1),
                "nisar_water_ha": round(float(y.sum()) * export.PIXEL_HA, 1),
                "nisar_new_water_ha": round(float((y[nisar_dry_before] == 1).sum()) * export.PIXEL_HA, 1), **runs}
            for label, r in runs.items():
                print(name, stack, label, "lead", r["lead_days"], "rain", r["rain_between_mm"],
                      {k: (v["water_ap"], v["new_water_ap"]) for k, v in r["methods"].items()}, flush=True)
    _json({"reading": "The model never saw a NISAR map. Here its replays for the NISAR pass of 28 Oct 2026 are scored against the "
                      "team's NISAR water map of that pass (data/cv). 'New water' = dry in the NISAR map of 16 Oct, water on 28 Oct. "
                      "issued_before_storm starts from the last Sentinel-1 map before the rain; issued_after_storm from a map 3 to 5 "
                      "days before the target, when the flood was already visible. (water_ap, new_water_ap) = average precision.",
           "caution": "The NISAR map comes from a model trained with Sentinel-1 labels at Albufera, so Albufera is not an independent "
                      "check. Pego-Oliva was a test site of that model.",
           "variant": variant, "thresholds_frozen_from": "development_metrics.json", "sites": report}, vdir / "nisar_check.json")
    if primary:
        _write_index(index, lambda e: e["scenario_id"].endswith("_prestorm"))


def compare(_args):
    """Held-out scores of every trained variant side by side: what soil moisture and the NISAR labels add."""
    rows, table = {}, []
    for variant in VARIANTS:
        path = _vdir(variant) / "holdout_s1_metrics.json"
        if not path.exists():
            continue
        sites = json.loads(path.read_text(encoding="utf-8"))["sites"]
        man = json.loads((_vdir(variant) / "training_manifest.json").read_text(encoding="utf-8"))
        imp = json.loads((_vdir(variant) / "development_metrics.json").read_text(encoding="utf-8"))["importance_gain_share"]["rain_and_state"]
        rows[variant] = {"labels": VARIANTS[variant][0], "soil_moisture": VARIANTS[variant][1], "rounds": man["rounds"],
                         "soil_importance_gain_share": round(sum(v for k, v in imp.items() if k in F.SOIL), 4), "sites": {}}
        for name, rep_ in sites.items():
            pooled = rep_["pooled_over_held_out_passes"]["methods"]
            storm = [p for p in rep_["passes"] if p["date"] in STORM_DATES]
            rows[variant]["sites"][name] = {
                "all_held_out_passes": {k: pooled["rain_and_state"][k] for k in ("water_ap", "new_water_ap")},
                "storm_passes_mean": {k: round(float(np.mean([p["methods"]["rain_and_state"][k] for p in storm])), 4)
                                      for k in ("water_ap", "new_water_ap")},
                "terrain_only_new_water_ap": pooled["terrain_only"]["new_water_ap"],
                "past_wet_share_new_water_ap": pooled["past_wet_share"]["new_water_ap"]}
            r = rows[variant]["sites"][name]
            table.append(f"{variant:11s} {name:11s} all passes new-water AP {r['all_held_out_passes']['new_water_ap']:.4f}  "
                         f"storm passes {r['storm_passes_mean']['new_water_ap']:.4f}  (terrain only {r['terrain_only_new_water_ap']:.4f}, "
                         f"past wet share {r['past_wet_share_new_water_ap']:.4f})")
    _json({"reading": "Every variant is scored on the same held-out Sentinel-1 passes of 15 Oct to 15 Nov 2026 with the full model "
                      "(rain_and_state). storm passes = 22 and 23 Oct. Scores are average precision.",
           "variants": rows}, OUT / "comparison.json")
    print("\n".join(table))


def main():
    parser = argparse.ArgumentParser(prog="python -m pipeline.prediction.spatial")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("prepare", prepare), ("train", train), ("predict", predict), ("nisar", nisar), ("compare", compare)):
        sp = sub.add_parser(name)
        sp.set_defaults(fn=fn)
        if name in ("train", "predict", "nisar"):
            sp.add_argument("--variant", choices=list(VARIANTS), default="base")
    sub.add_parser("all").set_defaults(fn=lambda a: (prepare(a), train(a), predict(a), nisar(a)))
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
