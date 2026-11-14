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
            add(f"{tag}.ci95.{k}", f"{lo:.2f}–{hi:.2f}", f"{src_r} {variant}.ci95.{k}")
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
    add("pego.inside_range", f"{100 * lo:.0f}–{100 * hi:.0f} %", f"{src_n} pego_oliva_dana.nisar_new_water.±1.share_inside_outline")
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
    add("alert.run15_daily_18_19", f"{run15['daily_max_mm'][3]} / {run15['daily_max_mm'][4]} mm",
        f"{src_f} dana_replay_pego_oliva[2026-10-15].daily_max_mm[3:5]")

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
