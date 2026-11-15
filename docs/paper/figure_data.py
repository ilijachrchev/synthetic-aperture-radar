"""Chart data as small CSV files, to paste into an online chart tool (e.g. Datawrapper).

    python -I docs/paper/figure_data.py          # from the repo root; writes docs/paper/figure-data/*.csv

Every value is read from the result files (same sources as figures.py and numbers.py); nothing typed by
hand. The two maps (Figs. 4 and 6) are not here: they need the radar stacks, see figures.py.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "paper" / "figure-data"


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def write(name, header, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print("wrote", (OUT / name).relative_to(ROOT))


def main():
    spec = importlib.util.spec_from_file_location("numbers_", ROOT / "docs" / "paper" / "numbers.py")
    num = importlib.util.module_from_spec(spec); spec.loader.exec_module(num)
    vals = {k: v for k, v, _ in num.rows()}

    # Fig. 2: accuracy on 18 June (referee v2), one file per measure
    v = load("data/validation/june18/result.json")["v2"]
    names = {"nisar": "NISAR threshold (L-band, -15 dB)", "s1": "DSWx-S1 (Sentinel-1)", "unet": "App U-Net (trained on DSWx-S1)"}
    for kind, fname in (("producer", "fig2a_producers_accuracy.csv"), ("user", "fig2b_users_accuracy.csv")):
        rows = []
        for k, label in names.items():
            lo, hi = v["ci95"][f"{k}_{kind}"]
            w0, w1 = vals[f"v2.{k}.range_{kind}"].split("–")
            rows.append([label, round(v[k][kind], 2), round(lo, 2), round(hi, 2), w0, w1])
        write(fname, ["Map", "Estimate", "95% low", "95% high", "Worst case", "Best case"], rows)

    # Fig. 3: referee outcome per stratum (counts), two referees
    r = load("data/validation/june18/result.json")
    strat = {"A": "A both maps water", "B": "B NISAR only", "C": "C Sentinel-1 only", "D": "D neither (rice)", "E": "E control cropland"}
    for key, fname in (("v2", "fig3a_strata_referee_v2.csv"), ("strict_mndwi_only", "fig3b_strata_strict.csv")):
        write(fname, ["Stratum", "Wet", "Dry", "Unclear"],
              [[strat[h], c["wet"], c["dry"], c["unclear"]] for h, c in r[key]["counts"].items()])

    # Fig. 5: Albufera rice, NISAR dark share vs DSWx-S1, per track
    n = load("data/prediction/nisar_check.json")
    for key, fname in (("albufera_rice", "fig5a_albufera_track066D.csv"), ("albufera_rice_058_A_021", "fig5b_albufera_track058A.csv")):
        rows = [[d["date"], d["nisar_dark_pct"]["-15"], d["dswx"]["flooded_pct"] if d.get("dswx") else ""] for d in n[key]["dates"]]
        write(fname, ["Date", "NISAR darker than -15 dB (%)", "DSWx-S1 water (%)"], rows)

    # Fig. 7: DANA timeline (rain per day, DSWx-S1 water per pass, pass dates)
    start, end = "2026-10-14", "2026-11-10"
    rain = [row for row in csv.DictReader(open(ROOT / "data/prediction/flood/rain_pego_oliva.csv", encoding="utf-8"))
            if start <= row["date"] <= end]
    write("fig7a_dana_rain_per_day.csv", ["Date", "Rain (mm, wettest IFS point)"], [[x["date"], x["max_mm"]] for x in rain])
    passes = [row for row in csv.DictReader(open(ROOT / "data/prediction/flood/water_pego_oliva.csv", encoding="utf-8"))
              if start <= row["date"] <= end]
    write("fig7b_dana_sentinel1_water.csv", ["Pass time (UTC)", "DSWx-S1 water inside EMSR935 outline (ha)"],
          [[x["begin_utc"][:16].replace("T", " "), x["flooded_in_emsr935_ha"]] for x in passes])
    pd = n["pego_oliva_dana"]
    write("fig7c_dana_who_was_looking.csv", ["Date", "What"],
          [[x["begin_utc"][:10], "Sentinel-1 pass"] for x in passes]
          + [[pd["before"], "NISAR 066 D pass"], [pd["after"], "NISAR 066 D pass"], ["2026-10-20", "Copernicus EMSR935 image"]])

    # Fig. 8: land-class model, per-class F1 on test blocks
    try:
        log = subprocess.run(["git", "-C", str(ROOT), "show", "claude/ml-training-loop-f64c3f:data/ml/experiments/LOG.md"],
                             capture_output=True, text=True, check=True, encoding="utf-8").stdout.splitlines()
        k = next(i for i, l in enumerate(log) if l.startswith("**Per-class F1 on the test blocks"))
        rows = []
        for l in log[k + 1:k + 14]:
            if l.startswith("| ") and not l.startswith("| class") and "---" not in l:
                c = [x.strip() for x in l.strip("|").split("|")]
                rows.append([c[0].replace("_", " ")] + [x if x[:1].isdigit() else "" for x in c[1:4]])
        write("fig8_landclass_f1.csv", ["Class", "Albufera (test)", "Espada (test)", "Pego-Oliva (never seen)"], rows)
    except Exception as e:
        print("skip fig8:", e)

    # Table 6: independent EMSR935 test of the flood-extent model
    te = load("data/validation/emsr935/result.json")["sets"]["all_pixels"]
    sc = te["references"]["flooded_area"]["scores"]
    names6 = {"model": "Model (rain that fell)", "model_forecast_rain": "Model (forecast rain)",
              "low_hand_same_area": "Low terrain, same area", "jrc_past_water": "Past water (JRC)",
              "nisar_16oct_persistence": "NISAR 16 Oct, -15 dB", "nisar_16oct_persistence_otsu": "NISAR 16 Oct, Otsu",
              "hand_zero_all": "All land with HAND = 0"}
    write("table6_emsr935_test.csv", ["Method", "F1", "Precision", "Recall", "Mapped area (ha)"],
          [[label, sc[k]["f1"], sc[k]["precision"], sc[k]["recall"], sc[k]["predicted_ha"]] for k, label in names6.items()])
    ap_ = te["average_precision_flooded_area"]
    write("table6_emsr935_ranking.csv", ["Method", "Average precision"],
          [["Model", ap_["model"]], ["NISAR 16 Oct darkness", ap_["nisar_16oct_darkness"]], ["Low terrain (HAND)", ap_["low_hand"]],
           ["Past water (JRC)", ap_["jrc_occurrence"]], ["Random guess (base rate)", ap_["base_rate"]]])

    # Table 5 / optional chart: threshold sweep
    sw = load("data/validation/june18/threshold_sweep.json")["by_threshold"]
    write("table5_threshold_sweep.csv",
          ["Threshold (dB)", "Random map of same size", "Producer's accuracy (v1)", "User's accuracy (v1)", "User's accuracy (strict)"],
          [[t, row["mapped_share_of_rice_points_weighted"], row["v1"]["producer"], row["v1"]["user"], row["strict"]["user"]]
           for t, row in sw.items()])


if __name__ == "__main__":
    main()
