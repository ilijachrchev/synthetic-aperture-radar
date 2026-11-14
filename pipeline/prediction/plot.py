"""Standalone scientific figures; figures are derived from the exported results."""

from datetime import date, timedelta
import os
from pathlib import Path
import tempfile

import numpy as np

from .data import Series
from .models import MODEL_NAMES


def plot_results(series: Series, forecast: dict, metrics: dict, output: Path) -> None:
    # Matplotlib's default config directory may be read-only in Colab/sandboxes.
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "sar-forecast-mpl"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "axes.grid": True,
                         "grid.alpha": 0.15, "svg.fonttype": "none"})
    fig, axes = plt.subplots(3, 1, figsize=(11, 11), gridspec_kw={"height_ratios": [1, 1.2, 1]})
    issued = date.fromisoformat(forecast["forecast_origin"])
    cutoff = series.dates[-1]
    colors = {"persistence": "#64748b", "linear": "#0284c7", "trend_seasonal": "#b45309"}
    names = {"persistence": "Persistence", "linear": "Linear trend", "trend_seasonal": "Trend + annual cycle"}
    site_name = forecast["site"].replace("_", " ").title()
    fig.suptitle(f"{series.point_id} · {site_name} vertical displacement", x=0.08, y=0.975, ha="left",
                 fontsize=19, fontweight="bold")
    fig.text(0.08, 0.94, f"{forecast['source']['provider']} | {forecast['source']['type']} | "
             f"issued {issued} · observations through {cutoff}", fontsize=10, color="#475569")

    ax = axes[0]
    ax.scatter(series.dates, series.values, s=3, color="#334155", alpha=0.65, rasterized=True)
    for label, color in (("selection", "#dbeafe"), ("calibration", "#fef3c7"), ("test", "#dcfce7")):
        period = metrics["periods"][label]
        ax.axvspan(date.fromisoformat(period["start"]), date.fromisoformat(period["end"]),
                   color=color, alpha=0.55, zorder=0, label=label.title())
    ax.set_title("Observed history · missing dates remain empty", loc="left")
    ax.set_ylabel("Displacement (mm)")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper right", ncol=3, frameon=False, fontsize=9)

    ax = axes[1]
    recent = [(d, value) for d, value in zip(series.dates, series.values)
              if d >= issued - timedelta(days=180)]
    if not recent:
        recent = list(zip(series.dates[-30:], series.values[-30:]))
    ax.scatter([r[0] for r in recent], [r[1] for r in recent], s=9, color="#334155", label="Observed")
    ax.axvline(issued, linestyle="--", color="#334155", linewidth=1, label="Forecast origin")
    if cutoff < issued:
        ax.axvspan(cutoff, issued, color="#f1f5f9", zorder=0)
        ax.text(0.01, 0.97, f"Latest observation is {forecast['observation_age_days']} days before issue",
                transform=ax.transAxes, va="top", fontsize=9, color="#475569")
    for i, prediction in enumerate(forecast["predictions"]):
        target = date.fromisoformat(prediction["target_date"])
        for label, width, alpha in (("95", 2, 0.35), ("80", 6, 0.7)):
            interval = prediction["intervals"][label]
            if interval["lower_mm"] is not None:
                ax.vlines(target, interval["lower_mm"], interval["upper_mm"],
                          color="#0284c7", linewidth=width, alpha=alpha,
                          label=f"{label}% historical-error range" if i == 0 else None)
        ax.scatter([target], [prediction["value_mm"]], color="#0369a1", s=38, zorder=4,
                   label="Selected forecast" if i == 0 else None)
    ax.set_title("Next targets · model selected on development data", loc="left")
    ax.set_ylabel("Displacement (mm)")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.legend(loc="lower left", ncol=2, frameon=False, fontsize=8)

    ax = axes[2]
    horizons = forecast["requested_horizons_days"]
    x = np.arange(len(horizons))
    for i, name in enumerate(MODEL_NAMES):
        errors = [metrics["test"][str(h)][name]["mae_mm"] for h in horizons]
        ax.bar(x + (i - 1) * 0.23, errors, width=0.23, color=colors[name], label=names[name])
    ax.set_xticks(x, [f"{h} days" for h in horizons])
    ax.set_ylabel("MAE (mm)")
    period = metrics["periods"]["test"]
    ax.set_title(f"Held-out backtest · {period['start']} to {period['end']} · lower is better", loc="left")
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=9)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.18)

    fig.text(0.08, 0.035, f"Positive = upward; zero = first retained observation on {series.dates[0]}. "
             "Ranges are empirical, not guaranteed coverage.\n"
             f"Observation type: {forecast['source']['type']}. No NISAR validation performed.",
             fontsize=9, color="#475569")
    fig.subplots_adjust(left=0.09, right=0.97, top=0.89, bottom=0.10, hspace=0.50)
    fig.savefig(output / "chart.png", dpi=160)
    fig.savefig(output / "chart.svg")
    plt.close(fig)
