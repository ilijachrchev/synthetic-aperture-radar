"""Figures for the paper, drawn only from the result files (and, for the two maps, the data stacks).

    python -I docs/paper/figures.py --data "<main checkout>/data"      # from the repo root

Writes PNGs to docs/paper/figures/. Charts need only committed result files; the two maps also need
the NISAR stacks, the rice mask and the DSWx-S1 tiles in --data (not in git). Colours follow one fixed
order everywhere: NISAR = blue, Sentinel-1 / DSWx-S1 = orange, app U-Net = aqua (validated for
colour-vision deficiency with the dataviz palette checker); every series is also named in text.

The paper now uses only the two maps from this script (fig4, fig6). Figs. 2, 3, 5, 7, 8 and the Table 5
chart are Datawrapper charts made from docs/paper/figure-data/*.csv (see figure_data.py), under other
file names; the charts this script draws are kept as a backup.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))   # pipeline package (python -I drops the cwd)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

OUT = ROOT / "docs" / "paper" / "figures"
ML_BRANCH = "claude/ml-training-loop-f64c3f"

# Palette (dataviz reference instance, light mode)
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
NISAR, S1, UNET = "#2a78d6", "#eb6834", "#1baf7a"
NEUTRAL = "#d9d8d2"          # "unclear" / background class
BLUE_LIGHT = "#b7d3f6"       # sequential blue, step 150

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "semibold", "axes.titlelocation": "left",
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2, "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False,
    "text.color": INK, "savefig.dpi": 200,
})


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print("wrote", (OUT / name).relative_to(ROOT))


def hgrid(ax):
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def vgrid(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------------------------
# Fig. 2 - accuracy on 18 June: estimate, 95 % interval, and bounds for unclear points
# ---------------------------------------------------------------------------------------------
def fig_accuracy() -> None:
    v = load("data/validation/june18/result.json")["v2"]
    import importlib.util
    spec = importlib.util.spec_from_file_location("numbers_", ROOT / "docs" / "paper" / "numbers.py")
    num = importlib.util.module_from_spec(spec); spec.loader.exec_module(num)
    vals = {k: val for k, val, _ in num.rows()}
    maps = [("nisar", "NISAR threshold\n(L-band, −15 dB)", NISAR), ("s1", "DSWx-S1\n(Sentinel-1, C-band)", S1),
            ("unet", "App U-Net\n(trained on DSWx-S1)", UNET)]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), sharey=True)
    for ax, kind, title in ((axes[0], "producer", "Producer's accuracy: share of wet rice the map finds"),
                            (axes[1], "user", "User's accuracy: share of mapped water that is wet")):
        for j, (key, label, color) in enumerate(maps):
            y = len(maps) - 1 - j
            est = v[key][kind]
            lo, hi = v["ci95"][f"{key}_{kind}"]
            r0, r1 = (float(x) for x in vals[f"v2.{key}.range_{kind}"].split("–"))
            ax.plot([r0, r1], [y, y], color=color, lw=9, alpha=0.18, solid_capstyle="butt", zorder=1)
            ax.plot([lo, hi], [y, y], color=color, lw=2, solid_capstyle="round", zorder=2)
            ax.scatter([est], [y], s=48, color=color, edgecolor=SURFACE, lw=1.5, zorder=4)
            ax.annotate(f"{est:.2f}", (est, y), xytext=(0, 7), textcoords="offset points", ha="center",
                        fontsize=8.5, color=INK, fontweight="semibold")
        ax.set_xlim(-0.02, 1.04)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_title(title, fontsize=9)
        hgrid(ax)
        ax.tick_params(axis="y", length=0)
    axes[0].set_yticks(range(len(maps)), [m[1] for m in maps][::-1])
    axes[0].set_ylim(-0.6, len(maps) - 0.3)
    handles = [plt.Line2D([], [], marker="o", ls="", color=INK2, label="estimate (decided points)"),
               plt.Line2D([], [], color=INK2, lw=2, label="95 % interval (stratified bootstrap)"),
               plt.Line2D([], [], color=INK2, lw=9, alpha=0.18, label="worst to best case for unclear points")]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.55, -0.1), fontsize=8)
    save(fig, "fig2_june18_accuracy.png")


# ---------------------------------------------------------------------------------------------
# Fig. 3 - referee outcome per stratum, two referees
# ---------------------------------------------------------------------------------------------
def fig_strata() -> None:
    r = load("data/validation/june18/result.json")
    s = load("data/validation/june18/strata.json")
    names = {"A": "A  both maps water", "B": "B  NISAR only", "C": "C  Sentinel-1 only",
             "D": "D  neither (rice)", "E": "E  control cropland"}
    order = list("ABCDE")
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.5), sharey=True)
    for ax, key, title in ((axes[0], "v2", "Referee v2 (after review):\nrice-flooding index or MNDWI"),
                           (axes[1], "strict_mndwi_only", "Strict referee:\nopen water only (MNDWI > 0)")):
        for j, h in enumerate(order):
            c = r[key]["counts"][h]
            n = c["wet"] + c["dry"] + c["unclear"]
            y = len(order) - 1 - j
            left = 0.0
            for part, color, txt in (("wet", NISAR, SURFACE), ("dry", S1, SURFACE), ("unclear", NEUTRAL, INK)):
                w = c[part] / n
                ax.barh(y, w - 0.006 if w > 0.01 else w, left=left, height=0.62, color=color, linewidth=0)
                if w >= 0.09:
                    ax.text(left + 0.012, y, str(c[part]), va="center", ha="left", fontsize=7.5, color=txt)
                left += w
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.5, 1], ["0 %", "50 %", "100 %"])
        ax.set_title(title, fontsize=9)
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
    axes[0].set_yticks(range(len(order)), [f"{names[h]}  (n={s['n_points'][h]})" for h in order][::-1])
    fig.legend(handles=[Patch(color=NISAR, label="wet before and after"), Patch(color=S1, label="dry before and after"),
                        Patch(color=NEUTRAL, label="unclear (looks disagree)")],
               loc="lower center", ncol=3, bbox_to_anchor=(0.6, -0.1), fontsize=8)
    save(fig, "fig3_june18_strata.png")


# ---------------------------------------------------------------------------------------------
# Fig. 5 - Albufera rice: NISAR dark share vs DSWx-S1 flooded share, per track
# ---------------------------------------------------------------------------------------------
def fig_timeseries() -> None:
    n = load("data/prediction/nisar_check.json")
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), sharey=True)
    for ax, key, title in ((axes[0], "albufera_rice", "Track 066 D (evening, 18:53 UTC)"),
                           (axes[1], "albufera_rice_058_A_021", "Track 058 A (morning)")):
        rows = n[key]["dates"]
        d = [datetime.fromisoformat(x["date"]) for x in rows]
        nis = [x["nisar_dark_pct"]["-15"] for x in rows]
        ds = [(datetime.fromisoformat(x["date"]), x["dswx"]["flooded_pct"]) for x in rows if x.get("dswx")]
        ax.axvspan(datetime(2026, 7, 27), datetime(2026, 8, 10), color=GRID, lw=0)
        ax.text(datetime(2026, 8, 3), 49, "no NISAR\ndata", ha="center", va="top", fontsize=7, color=MUTED)
        ax.plot(d, nis, color=NISAR, lw=2, marker="o", ms=4.5, mec=SURFACE, mew=1.2, label="NISAR: rice darker than −15 dB")
        xs, ys = [], []
        for k, (a_, b_) in enumerate(ds):
            if k and (a_ - ds[k - 1][0]).days > 13:
                xs.append(a_ - timedelta(days=1)); ys.append(np.nan)
            xs.append(a_); ys.append(b_)
        ax.plot(xs, ys, color=S1, lw=2, marker="o", ms=4.5, mec=SURFACE, mew=1.2,
                label="DSWx-S1 (paired pass within 2 h): rice mapped as water")
        ax.annotate(f"{nis[0]:.0f} %", (d[0], nis[0]), xytext=(6, 0), textcoords="offset points", va="center",
                    fontsize=8, color=INK, fontweight="semibold")
        if ds and ds[0][0] == d[0]:
            ax.annotate(f"{ds[0][1]:.0f} %", ds[0], xytext=(6, 2), textcoords="offset points", va="bottom",
                        fontsize=8, color=INK, fontweight="semibold")
        ax.set_title(title, fontsize=9)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.set_ylim(0, 50)
        vgrid(ax)
    axes[0].set_ylabel("share of rice mask (%)")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.08), fontsize=8, handlelength=2.5)
    save(fig, "fig5_albufera_timeseries.png")


# ---------------------------------------------------------------------------------------------
# Fig. 7 - DANA "Adam": rain, who was looking, and how much water Sentinel-1 saw
# ---------------------------------------------------------------------------------------------
def fig_dana_timeline() -> None:
    n = load("data/prediction/nisar_check.json")["pego_oliva_dana"]
    start, end = date(2026, 10, 14), date(2026, 11, 10)
    rain = [(date.fromisoformat(r["date"]), float(r["max_mm"])) for r in
            csv.DictReader(open(ROOT / "data/prediction/flood/rain_pego_oliva.csv", encoding="utf-8"))]
    rain = [(d, v) for d, v in rain if start <= d <= end]
    passes = [r for r in csv.DictReader(open(ROOT / "data/prediction/flood/water_pego_oliva.csv", encoding="utf-8"))
              if start.isoformat() <= r["date"] <= end.isoformat()]
    s1_t = [datetime.fromisoformat(r["begin_utc"].replace("Z", "")) for r in passes]
    s1_ha = [float(r["flooded_in_emsr935_ha"]) for r in passes]
    nisar_t = [datetime.fromisoformat(n["before"] + "T18:53"), datetime.fromisoformat(n["after"] + "T18:53")]
    emsr_t = datetime(2026, 10, 20, 10, 9)

    fig, axes = plt.subplots(3, 1, figsize=(7.2, 4.4), sharex=True, gridspec_kw={"height_ratios": [1.3, 0.8, 1.3]})
    ax = axes[0]
    ax.bar([datetime.combine(d, datetime.min.time()) + timedelta(hours=12) for d, _ in rain], [v for _, v in rain],
           width=0.7, color=NISAR, alpha=0.55, linewidth=0)
    peak = max(rain, key=lambda x: x[1])
    ax.annotate(f"{peak[1]:.0f} mm on {peak[0].strftime('%d %b')}", (datetime.combine(peak[0], datetime.min.time()) + timedelta(hours=12), peak[1]),
                xytext=(8, -2), textcoords="offset points", fontsize=8, va="top", color=INK)
    ax.set_ylabel("rain per day\n(mm, IFS wettest point)")
    ax.set_title("Pego-Oliva, DANA \"Adam\" (17–19 Oct 2026)", fontsize=9)
    vgrid(ax)

    ax = axes[1]
    rows = [("Sentinel-1 passes", s1_t, S1), ("NISAR 066 D passes", nisar_t, NISAR), ("Copernicus EMSR935 image", [emsr_t], INK2)]
    for k, (label, ts, color) in enumerate(rows):
        y = len(rows) - 1 - k
        ax.scatter(ts, [y] * len(ts), marker="|", s=160, linewidths=2.2, color=color)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_yticks(range(len(rows))[::-1], [r[0] for r in rows])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)

    ax = axes[2]
    ax.plot(s1_t, s1_ha, color=S1, lw=2, marker="o", ms=4, mec=SURFACE, mew=1)
    for t in nisar_t:
        ax.axvline(t, color=NISAR, lw=1, alpha=0.6)
    i_max = int(np.argmax(s1_ha))
    ax.annotate(f"{s1_ha[i_max]:.0f} ha", (s1_t[i_max], s1_ha[i_max]), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=8, fontweight="semibold")
    ax.text(nisar_t[1] + timedelta(hours=10), max(s1_ha) * 0.12, f"NISAR: {n['nisar_new_water']['+0']['new_water_ha']:.0f} ha new water\n16→28 Oct, "
            f"{100 * n['nisar_new_water']['+0']['share_inside_outline']:.0f} % inside the outline", fontsize=7.5, color=INK2)
    ax.set_ylabel("DSWx-S1 water inside\nEMSR935 outline (ha)")
    ax.set_ylim(0, max(s1_ha) * 1.15)
    vgrid(ax)
    ax.xaxis.set_major_locator(mdates.DayLocator(bymonthday=[1, 10, 16, 20, 28]))
    ax.xaxis.set_minor_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    for a in axes:
        a.axvspan(datetime(2026, 10, 17), datetime(2026, 10, 20), color=GRID, lw=0, zorder=0)
    ax.set_xlim(datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.min.time()) + timedelta(days=1))
    save(fig, "fig7_dana_timeline.png")


# ---------------------------------------------------------------------------------------------
# Fig. 8 - land-class model, per-class F1 on test blocks (agreement with label maps)
# ---------------------------------------------------------------------------------------------
def fig_ml() -> None:
    try:
        log = subprocess.run(["git", "-C", str(ROOT), "show", f"{ML_BRANCH}:data/ml/experiments/LOG.md"],
                             capture_output=True, text=True, check=True, encoding="utf-8").stdout
    except Exception as e:
        print("skip fig8 (ML log not found):", e)
        return
    lines = log.splitlines()
    k = next(i for i, l in enumerate(lines) if l.startswith("**Per-class F1 on the test blocks"))
    table = [l for l in lines[k + 1:k + 14] if l.startswith("| ") and not l.startswith("| class") and "---" not in l]
    classes, vals = [], []
    for row in table:
        cells = [c.strip() for c in row.strip("|").split("|")]
        classes.append(cells[0].replace("_", " "))
        vals.append([float(c) if c[:1].isdigit() else np.nan for c in cells[1:4]])
    vals = np.array(vals)
    sites = [("Albufera (test)", NISAR), ("Espadà (test)", S1), ("Pego-Oliva (never seen)", UNET)]
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    h = 0.26
    for j, (site, color) in enumerate(sites):
        ys = np.arange(len(classes))[::-1] + (1 - j) * h
        ok = ~np.isnan(vals[:, j])
        ax.barh(ys[ok], vals[ok, j], height=h - 0.03, color=color, linewidth=0, label=site)
    ax.set_yticks(np.arange(len(classes))[::-1], classes)
    ax.set_xlim(0, 1)
    ax.set_xlabel("F1 (agreement with the label maps)")
    ax.tick_params(axis="y", length=0)
    hgrid(ax)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=8)
    save(fig, "fig8_landclass_f1.png")


# ---------------------------------------------------------------------------------------------
# Fig. 4 and Fig. 6 - maps (need the stacks in --data)
# ---------------------------------------------------------------------------------------------
def _extent(transform, shape):
    x0, y0 = transform.c, transform.f
    return [x0 / 1000, (x0 + transform.a * shape[1]) / 1000, (y0 + transform.e * shape[0]) / 1000, y0 / 1000]


def _crop(mask, pad=10):
    rows, cols = np.where(mask)
    return slice(max(rows.min() - pad, 0), rows.max() + pad), slice(max(cols.min() - pad, 0), cols.max() + pad)


def _km_axes(ax):
    ax.set_xlabel("UTM 30N easting (km)", fontsize=8)
    ax.set_ylabel("northing (km)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_aspect("equal")


def fig_map_june18(data: Path) -> None:
    import pipeline.validation.june18 as j
    strata, _ = j.build_strata(data)
    rice, _, transform, _, shape = j._grid(data)
    rs, cs = _crop(rice)
    st = strata[rs, cs]
    code = np.zeros(st.shape, dtype=int)
    for v, h in ((1, "D"), (2, "B"), (3, "C"), (4, "A")):
        code[st == h] = v
    ext = _extent(transform * transform.translation(cs.start, rs.start), st.shape)
    cmap = ListedColormap([SURFACE, NEUTRAL, NISAR, S1, INK2])
    pts = list(csv.DictReader(open(ROOT / "data/validation/june18/reference.csv", encoding="utf-8")))
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.2), sharey=True)
    ax = axes[0]
    ax.imshow(code, cmap=cmap, vmin=-0.5, vmax=4.5, extent=ext, interpolation="nearest")
    ax.set_title("Water on 18 June 2026 inside the rice", fontsize=9)
    ax.legend(handles=[Patch(color=NISAR, label="NISAR only (B)"), Patch(color=INK2, label="both maps (A)"),
                       Patch(color=S1, label="Sentinel-1 only (C)"), Patch(color=NEUTRAL, label="neither (D)")],
              loc="lower left", fontsize=7.5, framealpha=0.9, frameon=True, edgecolor=GRID)
    _km_axes(ax)
    ax = axes[1]
    ax.imshow(np.where(rice[rs, cs], 1, 0), cmap=ListedColormap([SURFACE, "#efeee9"]), extent=ext, interpolation="nearest")
    for lab, color, z in (("unclear", MUTED, 2), ("dry", S1, 3), ("wet", NISAR, 4)):
        sel = [p for p in pts if p["label"] == lab]
        ax.scatter([float(p["x_utm30n"]) / 1000 for p in sel], [float(p["y_utm30n"]) / 1000 for p in sel], s=9,
                   color=color, edgecolor=SURFACE, lw=0.4, zorder=z, label=f"{lab} ({len(sel)})")
    ax.set_title(f"Optical referee at the {len(pts)} sample points (rule v2)", fontsize=9)
    ax.legend(loc="lower left", fontsize=7.5, framealpha=0.9, frameon=True, edgecolor=GRID)
    _km_axes(ax)
    ax.set_ylabel("")
    save(fig, "fig4_june18_map.png")


def fig_map_dana(data: Path) -> None:
    import geopandas as gpd
    import pipeline.prediction.nisar_check as nc
    from pipeline.cv.baseline import water_mask
    from pipeline.cv.data import grid_of, open_stack, rasterize_on
    from pipeline.cv.evaluate import permanent_water
    n = load("data/prediction/nisar_check.json")["pego_oliva_dana"]
    ds = open_stack(data / "stack" / "pego_oliva_066_D_069.nc")
    days = [str(t)[:10] for t in ds["time"].values]
    hb, okb, tb = nc.scene_db(ds, days.index(n["before"]))
    ha, oka, ta = nc.scene_db(ds, days.index(n["after"]))
    labels = ROOT / "data" / "labels"
    aoi = rasterize_on(ds, gpd.read_file(labels / "pego_oliva_emsr935_aoi.geojson")).astype(bool)
    flood = gpd.read_file(labels / "pego_oliva_emsr935_flood.geojson")
    outline = rasterize_on(ds, flood[flood["class"] == "flooded_area"]).astype(bool)
    trace = rasterize_on(ds, flood[flood["class"] == "flood_trace"]).astype(bool)
    perm = permanent_water(ds, "pego_oliva")
    region = aoi & ~perm & ~trace & okb & oka
    new = water_mask(ha, oka, ta) & ~water_mask(hb, okb, tb) & region
    _, transform, shape = grid_of(ds)
    aoi1 = rasterize_on(ds, flood[(flood["class"] == "flooded_area") & (flood["aoi"] == "AOI01")]).astype(bool)
    rs, cs = _crop(aoi1, pad=60)
    code = np.zeros(shape, dtype=int)
    code[aoi] = 1
    code[perm & aoi] = 2
    code[outline & region] = 3
    code[new & ~outline] = 4
    code[new & outline] = 5
    code = code[rs, cs]
    ext = _extent(transform * transform.translation(cs.start, rs.start), code.shape)
    cmap = ListedColormap([SURFACE, "#efeee9", NEUTRAL, BLUE_LIGHT, S1, NISAR])
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    ax.imshow(code, cmap=cmap, vmin=-0.5, vmax=5.5, extent=ext, interpolation="nearest")
    ax.contour(np.flipud(outline[rs, cs].astype(float)), levels=[0.5], colors=[INK2], linewidths=0.6,
               extent=ext, origin="lower")
    z = n["nisar_new_water"]["+0"]
    ax.set_title(f"New NISAR water 16 → 28 Oct 2026: {z['new_water_ha']:.0f} ha, "
                 f"{100 * z['share_inside_outline']:.0f} % inside EMSR935", fontsize=9)
    ax.legend(handles=[Patch(color=NISAR, label="new NISAR water inside the outline"),
                       Patch(color=S1, label="new NISAR water outside the outline"),
                       Patch(color=BLUE_LIGHT, label="EMSR935 flood (20 Oct), not seen as new by NISAR"),
                       Patch(color=NEUTRAL, label="permanent water (left out)")],
              loc="lower left", fontsize=7, framealpha=0.92, frameon=True, edgecolor=GRID)
    _km_axes(ax)
    save(fig, "fig6_dana_map.png")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="folder with stack/, raw/, prediction/ (not in git)")
    ap.add_argument("--no-maps", action="store_true")
    a = ap.parse_args(argv)
    fig_accuracy()
    fig_strata()
    fig_timeseries()
    fig_dana_timeline()
    fig_ml()
    if not a.no_maps:
        fig_map_june18(a.data)
        fig_map_dana(a.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
