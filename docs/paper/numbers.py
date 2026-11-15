"""Every number the paper quotes, read from the result files (never typed by hand).

    python -I docs/paper/numbers.py            # from the repo root; writes docs/paper/numbers.md

Each row: key, value, source file and field. The paper cites these keys; `check` mode
(python -I docs/paper/numbers.py check) fails if a value printed here is missing from paper.md.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "docs" / "paper" / "paper.md"
OUT = ROOT / "docs" / "paper" / "numbers.md"
ML_BRANCH = "claude/ml-training-loop-f64c3f"


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def pct(x: float, nd: int = 0) -> str:
    return f"{100 * x:.{nd}f} %"


def rows() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []

    def add(key, value, src):
        out.append((key, str(value), src))

    # --- 18 June validation -------------------------------------------------
    r = load("data/validation/june18/result.json")
    s = load("data/validation/june18/strata.json")
    src_r, src_s = "data/validation/june18/result.json", "data/validation/june18/strata.json"
    n_total = sum(s["n_points"].values())
    add("june.n_points", n_total, f"{src_s} n_points (sum)")
    for h, n in s["n_points"].items():
        add(f"june.n_{h}", n, f"{src_s} n_points.{h}")
    for h, ha in s["stratum_ha"].items():
        add(f"june.ha_{h}", f"{ha:,.1f}", f"{src_s} stratum_ha.{h}")
    add("june.rice_ha", f"{s['rice_ha_scored']:,.1f}", f"{src_s} rice_ha_scored")
    add("june.nisar_ha", f"{s['nisar_water_ha']:,.1f}", f"{src_s} nisar_water_ha")
    add("june.s1_ha", f"{s['s1_water_ha']:,.1f}", f"{src_s} s1_water_ha")
    add("june.unet_ha_all", r["unet_check"]["rice_ha_all_pixels"], f"{src_r} unet_check.rice_ha_all_pixels")
    add("june.threshold_db", s["design"]["nisar_threshold_db"], f"{src_s} design.nisar_threshold_db")
    add("june.grid_m", s["design"]["grid_step_m"], f"{src_s} design.grid_step_m")
    add("june.seed", s["design"]["seed"], f"{src_s} design.seed")
    add("june.nisar_time", s["nisar_time"], f"{src_s} nisar_time")
    add("june.nisar_utc", s["nisar_time"][11:16], f"{src_s} nisar_time (hh:mm UTC)")
    add("rule.min_share", r["rule"]["min_share_pass"], f"{src_r} rule.min_share_pass")
    add("rule.min_ci_low", r["rule"]["min_ci_low"], f"{src_r} rule.min_ci_low")

    for variant in ("v2", "strict_mndwi_only", "v1_8_and_23_jun"):
        v = r[variant]
        tag = {"v2": "v2", "strict_mndwi_only": "strict", "v1_8_and_23_jun": "v1"}[variant]
        for h, c in v["counts"].items():
            add(f"{tag}.counts_{h}", f"{c['wet']} wet / {c['dry']} dry / {c['unclear']} unclear",
                f"{src_r} {variant}.counts.{h}")
        add(f"{tag}.b_wet_share", f"{v['b_wet_share']:.2f}", f"{src_r} {variant}.b_wet_share")
        add(f"{tag}.control_E", pct(v["control_E_wet_share"], 1), f"{src_r} {variant}.control_E_wet_share")
        for m in ("nisar", "s1", "unet"):
            add(f"{tag}.{m}.user", f"{v[m]['user']:.2f}", f"{src_r} {variant}.{m}.user")
            add(f"{tag}.{m}.producer", f"{v[m]['producer']:.2f}", f"{src_r} {variant}.{m}.producer")
            lo = v[m]["bounds_unclear_all_dry"]
            hi = v[m]["bounds_unclear_all_wet"]
            add(f"{tag}.{m}.bounds_user", f"{lo['user']:.2f} / {hi['user']:.2f}",
                f"{src_r} {variant}.{m}.bounds_unclear_all_dry/wet.user")
            add(f"{tag}.{m}.bounds_producer", f"{lo['producer']:.2f} / {hi['producer']:.2f}",
                f"{src_r} {variant}.{m}.bounds_unclear_all_dry/wet.producer")
        for k, (lo, hi) in v.get("ci95", {}).items():
            add(f"{tag}.ci95.{k}", f"{lo:.2f} to {hi:.2f}", f"{src_r} {variant}.ci95.{k}")
        add(f"{tag}.verdict", v.get("verdict", "-"), f"{src_r} {variant}.verdict")

    # Stratified estimate of wet rice area under rule v2 (decided points only, as the paper says)
    ref = list(csv.DictReader(open(ROOT / "data/validation/june18/reference.csv", encoding="utf-8")))
    est = 0.0
    for h in "ABCD":
        lab = [p["label"] for p in ref if p["stratum"] == h]
        wet, dry = lab.count("wet"), lab.count("dry")
        est += s["stratum_ha"][h] * wet / (wet + dry)
    add("v2.wet_rice_ha_est", f"{est:,.0f}",
        "derived: sum over strata A-D of stratum_ha x wet/(wet+dry), reference.csv label")
    add("v2.wet_rice_share_est", pct(est / s["rice_ha_scored"]), "derived: v2.wet_rice_ha_est / rice_ha_scored")

    # True worst/best case for unclear points (each unclear point set wet or dry to push the score
    # down or up), the stratified estimator over all points of strata A-D.
    W = s["weights"]
    for lab_key, tag in (("label_v1", "v1"), ("label", "v2")):
        for m in ("nisar", "s1", "unet"):
            res = {}
            for kind in ("producer", "user"):
                for side in ("lo", "hi"):
                    num = den = 0.0
                    for h in "ABCD":
                        pts_h = [p for p in ref if p["stratum"] == h]
                        a = mm = ww = 0
                        for p in pts_h:
                            mapped = p[m] == "1"
                            lab = p[lab_key]
                            if lab == "unclear":
                                if kind == "producer":
                                    wet = (mapped if side == "hi" else not mapped)
                                else:
                                    wet = (side == "hi")
                            else:
                                wet = lab == "wet"
                            a += mapped and wet
                            mm += mapped
                            ww += wet
                        n_h = len(pts_h)
                        num += W[h] * a / n_h
                        den += W[h] * (ww if kind == "producer" else mm) / n_h
                    res[(kind, side)] = num / den if den else float("nan")
            for kind in ("producer", "user"):
                add(f"{tag}.{m}.range_{kind}", f"{res[(kind, 'lo')]:.2f} to {res[(kind, 'hi')]:.2f}",
                    f"derived from reference.csv {lab_key}: unclear points set to the worst / best case")
    # Base rates: how wet the rice was anyway, and what a random map of NISAR's size would score
    for lab_key, tag in (("label_v1", "v1"), ("label", "v2")):
        lab = [p[lab_key] for p in ref if p["stratum"] == "D"]
        add(f"{tag}.d_wet_share", f"{lab.count('wet') / (lab.count('wet') + lab.count('dry')):.2f}",
            f"derived: stratum D wet / decided, reference.csv {lab_key}")
    unc = [p for p in ref if p["stratum"] == "B" and p["label"] == "unclear"]

    def _after(p):
        return p["wet_2026-06-22"] if p["wet_2026-06-22"] in ("0", "1") else p["wet_2026-06-23"]
    add("v2.b_unclear_wet_then_dry", f"{sum(p['wet_2026-06-08'] == '1' and _after(p) == '0' for p in unc)} of {len(unc)}",
        "derived: reference.csv, stratum B unclear points wet on 8 Jun and dry on the first clear look after")
    add("v1.b_decided", sum(p["label_v1"] in ("wet", "dry") for p in ref if p["stratum"] == "B"),
        "derived: reference.csv label_v1, stratum B decided points")
    add("june.nisar_area_share", f"{s['nisar_water_ha'] / s['rice_ha_scored']:.2f}",
        "derived: nisar_water_ha / rice_ha_scored (producer's accuracy of a random map of the same size)")

    # Rule v1 as first run and posted (commit 54fdc99), before rule v2 existed
    try:
        v1c = json.loads(subprocess.run(["git", "-C", str(ROOT), "show", "54fdc99:data/validation/june18/result.json"],
                                        capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        src1 = "git 54fdc99:data/validation/june18/result.json"
        for k in ("b_user", "nisar_producer", "nisar_user", "s1_producer"):
            lo, hi = v1c["ci95"][k]
            add(f"v1.ci95.{k}", f"{lo:.2f} to {hi:.2f}", f"{src1} ci95.{k}")
        add("v1.wet_share", f"{v1c['estimates']['wet_share']:.2f}", f"{src1} estimates.wet_share")
        ha, (lo, hi) = v1c["wet_rice_ha"]
        add("v1.wet_rice_ha", f"{ha:,}", f"{src1} wet_rice_ha")
        add("v1.wet_rice_ha_ci", f"{lo:,} to {hi:,}", f"{src1} wet_rice_ha interval")
    except Exception as e:
        add("v1.unavailable", f"commit 54fdc99 not found ({type(e).__name__})", "-")

    # Threshold sweep on the fixed sample points (pipeline/validation/june18_sweep.py)
    sw = load("data/validation/june18/threshold_sweep.json")
    src_sw = "data/validation/june18/threshold_sweep.json"
    add("sweep.check", sw["check_agreement_at_-15"], f"{src_sw} check_agreement_at_-15")
    for t, row in sw["by_threshold"].items():
        k = t.lstrip("-")
        add(f"sweep.{k}.mapped", f"{row['mapped_share_of_rice_points_weighted']:.2f}", f"{src_sw} by_threshold.{t}.mapped_share")
        for lab in ("v1", "strict"):
            r_ = row[lab]
            add(f"sweep.{k}.{lab}.producer", f"{r_['producer']:.2f} ({r_['producer_ci95'][0]:.2f} to {r_['producer_ci95'][1]:.2f})",
                f"{src_sw} by_threshold.{t}.{lab}.producer")
            add(f"sweep.{k}.{lab}.user", f"{r_['user']:.2f} ({r_['user_ci95'][0]:.2f} to {r_['user_ci95'][1]:.2f})",
                f"{src_sw} by_threshold.{t}.{lab}.user")
    # Tipping point: unclear B points that would have to be wet for the rule to hold on all 150
    import math
    for tag, cnt in (("v1", r["v1_8_and_23_jun"]["counts"]["B"]), ("v2", r["v2"]["counts"]["B"])):
        n_b = cnt["wet"] + cnt["dry"] + cnt["unclear"]
        need = max(0, math.ceil(r["rule"]["min_share_pass"] * n_b - cnt["wet"]))
        add(f"{tag}.b_tipping", f"{need} of {cnt['unclear']}", f"derived from {src_r} counts.B and rule.min_share_pass")
    jul = [d for d in load("data/prediction/nisar_check.json")["albufera_rice"]["dates"] if d["date"] == "2026-07-24"][0]
    add("alb.066.jul24_dark", f"{jul['nisar_dark_pct']['-15']} %", "data/prediction/nisar_check.json albufera_rice.dates[2026-07-24].nisar_dark_pct.-15")

    # DANA, every method on the same pixels (Ilija's CV benchmark, docs/CV_BENCHMARK.md on main, #32)
    try:
        md = subprocess.run(["git", "-C", str(ROOT), "show", "origin/main:docs/CV_BENCHMARK.md"],
                            capture_output=True, text=True, check=True, encoding="utf-8").stdout
        sec = md[md.index("### The DANA flood"):]
        for name, key in (("v1, threshold 0.3", "unet_v1"), ("Sentinel-1 map", "s1"), ("NISAR -15 dB threshold", "thr15"),
                          ("NISAR Otsu", "otsu")):
            line = next(l for l in sec.splitlines() if l.startswith(f"| {name} |"))
            c = [x.strip().strip("*") for x in line.strip("|").split("|")]
            add(f"bench.dana.{key}", f"IoU {c[1]}, precision {c[2]}, recall {c[3]}",
                "origin/main:docs/CV_BENCHMARK.md §10, DANA table")
    except Exception as e:
        add("bench.unavailable", f"CV_BENCHMARK.md not found ({type(e).__name__})", "-")

    # Rain-driven floods in the NISAR period before the DANA (training labels)
    ev = list(csv.DictReader(open(ROOT / "data/prediction/flood/events.csv", encoding="utf-8")))
    pre = [e for e in ev if "2026-06-17" <= e["date"] < "2026-10-15"]
    add("alert.nisar_period_new_floods", sum(e["new_flood"] == "1" for e in pre),
        "data/prediction/flood/events.csv new_flood, both sites, 17 Jun - 14 Oct 2026")
    big = max(pre, key=lambda e: float(e["rain_3d_max_mm"]))
    add("alert.nisar_period_max_rain", f"{float(big['rain_3d_max_mm']):.0f} mm ({big['site']}, {big['date']})",
        "data/prediction/flood/events.csv rain_3d_max_mm, 17 Jun - 14 Oct 2026")
    # Earlier IFS runs (raised on #29): pipeline/prediction/flood/early_runs.py
    er = json.loads((ROOT / "data/prediction/flood/early_runs_pego_oliva.json").read_text(encoding="utf-8"))
    r13 = next(r for r in er["runs"] if r["run"] == "2026-10-13")
    m13 = dict(zip(r13["dates"], r13["max_mm"]))
    add("alert.run13_daily_18_19", f"{m13['2026-10-18']} / {m13['2026-10-19']} mm",
        "data/prediction/flood/early_runs_pego_oliva.json runs[2026-10-13].max_mm, 18 and 19 Oct")
    r14 = next(r for r in er["runs"] if r["run"] == "2026-10-14")
    m14 = dict(zip(r14["dates"], r14["max_mm"]))
    add("alert.run14_daily_18_19", f"{m14['2026-10-18']} / {m14['2026-10-19']} mm",
        "data/prediction/flood/early_runs_pego_oliva.json runs[2026-10-14].max_mm, 18 and 19 Oct")
    rain = {r_["date"]: float(r_["max_mm"]) for r_ in csv.DictReader(
        (ROOT / "data/prediction/flood/rain_pego_oliva.csv").open(encoding="utf-8"))}
    add("rain.fell_18_19", f"{rain['2026-10-18']} / {rain['2026-10-19']} mm",
        "data/prediction/flood/rain_pego_oliva.csv max_mm, 18 and 19 Oct")
    add("rain.fell_17_21", f"{sum(rain[f'2026-10-{d}'] for d in range(17, 22)):.0f} mm",
        "data/prediction/flood/rain_pego_oliva.csv max_mm summed 17 to 21 Oct")
    # NISAR dark rice on 4 Oct vs 22 Sep, both tracks (unverified hint of a rain flood, #29)
    nc = json.loads((ROOT / "data/prediction/nisar_check.json").read_text(encoding="utf-8"))
    hint = []
    for k in ("albufera_rice_058_A_021", "albufera_rice"):
        dd = {x["date"]: x["nisar_dark_pct"]["-15"] for x in nc[k]["dates"]}
        hint.append(round((dd["2026-10-04"] - dd["2026-09-22"]) / 100 * nc[k]["rice_mask_ha"]))
    add("alb.oct4_extra_dark_ha", f"{hint[0]} to {hint[1]} ha",
        "derived: nisar_check.json (dark % on 2026-10-04 minus 2026-09-22) x rice_mask_ha, tracks 058 A and 066 D")
    th = n_th = None
    pg = load("data/prediction/nisar_check.json")["pego_oliva_dana"]["thresholds_db"]
    add("pego.otsu_db", f"{pg['before']} / {pg['after']}", "data/prediction/nisar_check.json pego_oliva_dana.thresholds_db")
    jd = [d for d in load("data/prediction/nisar_check.json")["albufera_rice"]["dates"] if d["date"] == "2026-06-18"][0]
    add("alb.066.jun18_dark_14_16", f"{jd['nisar_dark_pct']['-14']} / {jd['nisar_dark_pct']['-16']} %",
        "data/prediction/nisar_check.json albufera_rice.dates[2026-06-18].nisar_dark_pct.-14/-16")
    add("alb.066.jun18_median", f"{jd['median_hh_db']['rice']} dB", "data/prediction/nisar_check.json albufera_rice.dates[2026-06-18].median_hh_db.rice")

    sanity = r["optical_sanity"]
    for d, o in sanity.items():
        add(f"optical.ndvi_{d}", f"{o['median_ndvi']:.2f}", f"{src_r} optical_sanity.{d}.median_ndvi")

    # --- NISAR check: Albufera time series and Pego-Oliva DANA ---------------
    n = load("data/prediction/nisar_check.json")
    src_n = "data/prediction/nisar_check.json"
    a = n["albufera_rice"]
    add("alb.rice_mask_ha", f"{a['rice_mask_ha']:,.1f}", f"{src_n} albufera_rice.rice_mask_ha")
    jun = [d for d in a["dates"] if d["date"] == "2026-06-18"][0]
    add("alb.066.jun18_dark", f"{jun['nisar_dark_pct']['-15']} %", f"{src_n} albufera_rice.dates[2026-06-18].nisar_dark_pct.-15")
    add("alb.066.jun18_dswx", f"{jun['dswx']['flooded_pct']} %", f"{src_n} albufera_rice.dates[2026-06-18].dswx.flooded_pct")
    b = n["albufera_rice_058_A_021"]
    jun_b = [d for d in b["dates"] if d["date"] == "2026-06-18"][0]
    add("alb.058.jun18_dark", f"{jun_b['nisar_dark_pct']['-15']} %", f"{src_n} albufera_rice_058_A_021.dates[2026-06-18].nisar_dark_pct.-15")
    for key, blk in (("066", a), ("058", b)):
        au = blk["autumn"]
        add(f"alb.{key}.autumn_nisar", " → ".join(f"{x}" for x in au["nisar_dark_pct_-15"]) + " %",
            f"{src_n} {'albufera_rice' if key == '066' else 'albufera_rice_058_A_021'}.autumn.nisar_dark_pct_-15")
        add(f"alb.{key}.autumn_dswx", " → ".join(f"{x}" for x in au["dswx_flooded_pct"]) + " %",
            f"{src_n} {'albufera_rice' if key == '066' else 'albufera_rice_058_A_021'}.autumn.dswx_flooded_pct")
    add("alb.058.r15", b["pearson_r_paired_dates"]["-15"], f"{src_n} albufera_rice_058_A_021.pearson_r_paired_dates.-15")
    add("alb.058.paired", b["paired_dates"], f"{src_n} albufera_rice_058_A_021.paired_dates")

    p = n["pego_oliva_dana"]
    z = p["nisar_new_water"]["+0"]
    add("pego.before", p["before"], f"{src_n} pego_oliva_dana.before")
    add("pego.after", p["after"], f"{src_n} pego_oliva_dana.after")
    add("pego.new_ha", f"{z['new_water_ha']:.0f}", f"{src_n} pego_oliva_dana.nisar_new_water.+0.new_water_ha")
    add("pego.inside_share", pct(z["share_inside_outline"]), f"{src_n} pego_oliva_dana.nisar_new_water.+0.share_inside_outline")
    lo, hi = p["nisar_new_water"]["+1"]["share_inside_outline"], p["nisar_new_water"]["-1"]["share_inside_outline"]
    add("pego.inside_range", f"{100 * lo:.0f} to {100 * hi:.0f} %", f"{src_n} pego_oliva_dana.nisar_new_water.±1.share_inside_outline")
    add("pego.outline_ha", f"{p['outline_ha_scored']:.0f}", f"{src_n} pego_oliva_dana.outline_ha_scored")
    d = p["dswx_in_emsr935_outline_ha"]
    add("pego.dswx_before", f"{d['before']['value']:.0f}", f"{src_n} pego_oliva_dana.dswx_in_emsr935_outline_ha.before.value")
    add("pego.dswx_after", f"{d['after']['value']:.0f}", f"{src_n} pego_oliva_dana.dswx_in_emsr935_outline_ha.after.value")

    # Sentinel-1 passes over Pego-Oliva between the two NISAR dates and the data cut-off
    w = list(csv.DictReader(open(ROOT / "data/prediction/flood/water_pego_oliva.csv", encoding="utf-8")))
    win = [x for x in w if "2026-10-16" <= x["date"] <= "2026-11-10"]
    add("pego.s1_passes", len(win), "data/prediction/flood/water_pego_oliva.csv rows dated 2026-10-16..2026-11-10")
    add("pego.s1_first", win[0]["date"], "data/prediction/flood/water_pego_oliva.csv")
    add("pego.s1_last", win[-1]["date"], "data/prediction/flood/water_pego_oliva.csv")

    # --- Rain-threshold flood alert ------------------------------------------
    f = load("data/prediction/flood/forecast.json")
    fm = load("data/prediction/flood/metrics.json")
    src_f, src_fm = "data/prediction/flood/forecast.json", "data/prediction/flood/metrics.json"
    add("alert.threshold_mm", f"{f['threshold_mm_3d']:.0f}", f"{src_f} threshold_mm_3d")
    add("alert.fitted_mm", f"{f['threshold_fitted_mm_3d']:.0f}", f"{src_f} threshold_fitted_mm_3d")
    t = fm["scores"]["test"]
    add("alert.test", f"{t['hits']} of {t['events']} hits, {t['false_alarms']} false alarms, n = {t['n']} passes",
        f"{src_fm} scores.test")
    tr = fm["scores"]["train"]
    add("alert.train", f"{tr['events']} events, {tr['hits']} hits, {tr['false_alarms']} false alarms, n = {tr['n']}",
        f"{src_fm} scores.train")
    add("alert.train_brier_skill", tr["brier_skill"], f"{src_fm} scores.train.brier_skill")
    ft = fm["scores"]["fitted_threshold"]
    add("alert.fitted_train_fa", ft["train"]["false_alarms"], f"{src_fm} scores.fitted_threshold.train.false_alarms")
    for run in f["dana_replay_pego_oliva"]:
        add(f"alert.replay_{run['run']}", f"{run['rule_3d_mm']} mm, {run['alert']}",
            f"{src_f} dana_replay_pego_oliva[{run['run']}]")
    run15 = f["dana_replay_pego_oliva"][0]
    rr = {r_["run"]: r_ for r_ in f["dana_replay_pego_oliva"]}
    add("alert.run16_daily_18_19", f"{rr['2026-10-16']['daily_max_mm'][2]} / {rr['2026-10-16']['daily_max_mm'][3]} mm",
        f"{src_f} dana_replay_pego_oliva[2026-10-16].daily_max_mm[2:4]")
    add("alert.run17_daily_18_19", f"{rr['2026-10-17']['daily_max_mm'][1]} / {rr['2026-10-17']['daily_max_mm'][2]} mm",
        f"{src_f} dana_replay_pego_oliva[2026-10-17].daily_max_mm[1:3]")
    add("alert.run17_5d", f"{sum(rr['2026-10-17']['daily_max_mm']):.0f} mm",
        f"{src_f} dana_replay_pego_oliva[2026-10-17].daily_max_mm summed (17 to 21 Oct)")
    add("alert.run15_daily_18_19", f"{run15['daily_max_mm'][3]} / {run15['daily_max_mm'][4]} mm",
        f"{src_f} dana_replay_pego_oliva[2026-10-15].daily_max_mm[3:5]")

    # --- Independent EMSR935 test of the flood-extent model (Section 4.5 / 5.6) ---
    src_t = "data/validation/emsr935/result.json"
    T = json.loads((ROOT / src_t).read_text(encoding="utf-8"))
    A = T["sets"]["all_pixels"]; S0 = A["references"]["flooded_area"]["scores"]
    f2 = lambda x: f"{x:.2f}"
    def sc(k):
        s = S0[k]; return f"{f2(s['f1'])} (precision {f2(s['precision'])}, recall {f2(s['recall'])})"
    add("test.commit", T["model"]["commit"][:7], f"{src_t} model.commit (PR #33)")
    add("test.threshold", f"{T['model']['threshold_water_frozen']:.3f}", f"{src_t} model.threshold_water_frozen")
    add("test.area_ha", f"{A['area_ha']:,.0f} ha", f"{src_t} sets.all_pixels.area_ha")
    add("test.observed_ha", f"{S0['model']['observed_ha']:.0f} ha", f"{src_t} flooded_area observed_ha")
    add("test.model_ha", f"{S0['model']['predicted_ha']:.0f} ha", f"{src_t} model predicted_ha")
    add("test.model_fc_ha", f"{S0['model_forecast_rain']['predicted_ha']:.0f} ha", f"{src_t} model_forecast_rain predicted_ha")
    add("test.hand0_share", pct(A["hand_zero_share"], 1), f"{src_t} sets.all_pixels.hand_zero_share")
    for k in ("model", "model_forecast_rain", "low_hand_same_area", "jrc_past_water", "nisar_16oct_persistence",
              "nisar_16oct_persistence_otsu", "hand_zero_all"):
        add(f"test.{k}", sc(k), f"{src_t} sets.all_pixels.references.flooded_area.scores.{k}")
    add("test.hand0_ha", f"{S0['hand_zero_all']['predicted_ha']:,.0f} ha", f"{src_t} hand_zero_all predicted_ha")
    lo, mean, hi = A["low_hand_f1_over_50_tie_draws_flooded_area"]
    add("test.low_hand_draws", f"{lo:.3f} to {hi:.3f}", f"{src_t} low_hand_f1_over_50_tie_draws_flooded_area (min, max)")
    ci = A["references"]["flooded_area"]["f1_model_minus_baseline_ci95"]
    for k, short in (("low_hand_same_area", "hand"), ("jrc_past_water", "jrc"), ("nisar_16oct_persistence", "nisar")):
        add(f"test.diff_ci.{short}", f"{ci[k][0]:.2f} to {ci[k][1]:.2f}", f"{src_t} f1_model_minus_baseline_ci95.{k}")
    add("test.rule", "passed" if A["references"]["flooded_area"]["model_beats_all_three"] else "not passed",
        f"{src_t} references.flooded_area.model_beats_all_three")
    St = A["references"]["flooded_area_plus_trace"]["scores"]
    add("test.trace.model", f"{St['model']['f1']:.2f}", f"{src_t} flooded_area_plus_trace model f1")
    L = T["sets"]["model_learning_domain"]["references"]["flooded_area"]["scores"]
    add("test.domain.model", f"{L['model']['f1']:.2f}", f"{src_t} model_learning_domain model f1")
    ap_ = A["average_precision_flooded_area"]
    add("test.ap", f"model {ap_['model']:.2f}, NISAR 16 Oct darkness {ap_['nisar_16oct_darkness']:.2f}, low HAND {ap_['low_hand']:.2f}, "
        f"JRC {ap_['jrc_occurrence']:.2f}, base rate {ap_['base_rate']:.2f}", f"{src_t} average_precision_flooded_area")
    try:
        cmp_ = json.loads(subprocess.run(["git", "-C", str(ROOT), "show", f"{T['model']['commit']}:data/prediction/spatial/comparison.json"],
                                         capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        pv = cmp_["variants"]
        add("model.storm_new_ap", f"{pv['base']['sites']['pego_oliva']['storm_passes_mean']['new_water_ap']:.2f} (base) vs "
            f"{pv['nisar']['sites']['pego_oliva']['storm_passes_mean']['new_water_ap']:.2f} (NISAR labels)",
            "PR #33 data/prediction/spatial/comparison.json pego_oliva storm_passes_mean.new_water_ap")
        add("model.storm_new_ap_albufera", f"{pv['base']['sites']['albufera']['storm_passes_mean']['new_water_ap']:.2f} (base) vs "
            f"{pv['nisar']['sites']['albufera']['storm_passes_mean']['new_water_ap']:.2f} (NISAR labels)",
            "PR #33 data/prediction/spatial/comparison.json albufera storm_passes_mean.new_water_ap")
        add("model.soil_gain_share", pct(pv['soil']['soil_importance_gain_share'], 2),
            "PR #33 data/prediction/spatial/comparison.json variants.soil.soil_importance_gain_share")
        hm = json.loads(subprocess.run(["git", "-C", str(ROOT), "show", f"{T['model']['commit']}:data/prediction/spatial/holdout_s1_metrics.json"],
                                       capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        pg = hm["sites"]["pego_oliva"]["pooled_over_held_out_passes"]["methods"]
        add("model.holdout_pego", f"water AP {pg['rain_and_state']['water_ap']:.2f} vs {pg['terrain_only']['water_ap']:.2f} terrain only",
            "PR #33 data/prediction/spatial/holdout_s1_metrics.json pego_oliva pooled")
    except Exception as e:
        add("model.unavailable", f"PR #33 commit not fetched ({type(e).__name__})", "-")

    # --- The same EMSR935 test on three later frozen versions (#47, PR #46) ---
    fr = {}
    for v in ("chosen", "nisar_labels", "fit_albufera_oct"):
        src_v = f"data/validation/emsr935/result_{v}.json"
        Tv = json.loads((ROOT / src_v).read_text(encoding="utf-8"))
        Av = Tv["sets"]["all_pixels"]; Fv = Av["references"]["flooded_area"]; Sv = Fv["scores"]
        fr[v] = (Sv["model"]["f1"], Av["average_precision_flooded_area"]["model"])
        add(f"frozen.{v}.f1", f"{Sv['model']['f1']:.3f}", f"{src_v} flooded_area model f1")
        add(f"frozen.{v}.p_r", f"{Sv['model']['precision']:.2f} / {Sv['model']['recall']:.2f}", f"{src_v} model precision / recall")
        add(f"frozen.{v}.f1_fc", f"{Sv['model_forecast_rain']['f1']:.3f}", f"{src_v} model_forecast_rain f1")
        add(f"frozen.{v}.ha", f"{Sv['model']['predicted_ha']:.0f}", f"{src_v} model predicted_ha")
        add(f"frozen.{v}.ap", f"{Av['average_precision_flooded_area']['model']:.3f}", f"{src_v} average_precision_flooded_area.model")
        add(f"frozen.{v}.rule", "passed" if Fv["model_beats_all_three"] else "not passed", f"{src_v} model_beats_all_three")
        ci = Fv["f1_model_minus_baseline_ci95"]
        add(f"frozen.{v}.ci_jrc_nisar", f"{ci['jrc_past_water'][0]:.2f} to {ci['jrc_past_water'][1]:.2f}; "
            f"{ci['nisar_16oct_persistence'][0]:.2f} to {ci['nisar_16oct_persistence'][1]:.2f}", f"{src_v} f1_model_minus_baseline_ci95")
        add(f"frozen.{v}.sha", Tv["model"]["model_sha256_16"], f"{src_v} model.model_sha256_16")
    f1s = sorted(x[0] for x in fr.values()); aps = sorted(x[1] for x in fr.values())
    add("frozen.f1_range", f"{f1s[0]:.3f} to {f1s[-1]:.3f}", "data/validation/emsr935/result_{chosen,nisar_labels,fit_albufera_oct}.json model f1")
    add("frozen.ap_range", f"{aps[0]:.3f} to {aps[-1]:.3f}", "data/validation/emsr935/result_{...}.json average precision")
    add("test.ap_model3", f"{T['sets']['all_pixels']['average_precision_flooded_area']['model']:.3f}", f"{src_t} average_precision_flooded_area.model")
    add("test.model3", f"{S0['model']['f1']:.3f}", f"{src_t} flooded_area model f1")

    # --- Official flood zones against the 2026 flood (pipeline.zones, I. Chrchev) ---
    try:
        zf = ROOT / "data/zones/zones_vs_floods.json"
        zt = zf.read_text(encoding="utf-8") if zf.exists() else subprocess.run(
            ["git", "-C", str(ROOT), "show", "origin/main:data/zones/zones_vs_floods.json"],
            capture_output=True, text=True, check=True, encoding="utf-8").stdout
        zt = json.loads(zt)["events"]["dana_adam_2026_pego_oliva"]["total"]
        add("zones.pego_flooded_ha", f"{zt['flooded_ha']:,.1f} ha", "data/zones/zones_vs_floods.json dana_adam_2026_pego_oliva.total.flooded_ha")
        add("zones.pego_freq_occ", f"{zt['frequent_or_occasional_pct']} %", "data/zones/zones_vs_floods.json ...total.frequent_or_occasional_pct")
        add("zones.pego_outside", f"{zt['outside_every_zone_pct']} %", "data/zones/zones_vs_floods.json ...total.outside_every_zone_pct")
    except Exception as e:
        add("zones.unavailable", f"zones file not found ({type(e).__name__})", "-")

    # --- Land-class ML model (local branch, may be absent) -------------------
    try:
        log = subprocess.run(["git", "-C", str(ROOT), "show", f"{ML_BRANCH}:data/ml/experiments/LOG.md"],
                             capture_output=True, text=True, check=True, encoding="utf-8").stdout
        line = {k: next(l for l in log.splitlines() if l.startswith(f"| {k}")) for k in
                ("Albufera acc", "Espadà acc", "Pego-Oliva benchmark")}
        for k, l in line.items():
            add(f"ml.{k.split()[0].lower()}", l.split("|")[-2].strip().replace("*", ""),
                f"{ML_BRANCH}:data/ml/experiments/LOG.md, FINAL v2d table")
    except Exception as e:  # branch not here
        add("ml.unavailable", f"branch {ML_BRANCH} not found ({type(e).__name__})", "-")
    return out


def main() -> int:
    rs = rows()
    lines = ["# Numbers used in the paper", "",
             "Generated by `python -I docs/paper/numbers.py` from the result files. Do not edit by hand.", "",
             "| key | value | source |", "|---|---|---|"]
    lines += [f"| `{k}` | {v} | {s} |" for k, v, s in rs]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(rs)} values)")
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        import re
        text = PAPER.read_text(encoding="utf-8")
        values = {k: v for k, v, _ in rs}
        tags = list(re.finditer(r"<!--#([^>]+?)-->", text))
        bad = []
        for m in tags:
            key = m.group(1)
            if key == "key":  # the example tag in the paper header
                continue
            if key not in values:
                bad.append((key, "unknown key"))
                continue
            before = re.sub(r"<!--#[^>]+?-->", "", text[max(0, m.start() - 220):m.start()])
            for tok in re.findall(r"\d[\d,.]*", values[key]):
                tok = tok.rstrip(".,")
                if tok not in before:
                    bad.append((key, f"value {values[key]!r}: {tok!r} not in the text just before the tag"))
                    break
        print(f"paper has {len(tags)} number tags ({len({m.group(1) for m in tags})} keys); {len(bad)} problems")
        for k, why in bad:
            print(f"  BAD {k}: {why}")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
