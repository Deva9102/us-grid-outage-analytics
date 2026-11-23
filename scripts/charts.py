"""Draw the five findings charts into docs/images/ from the analysis results (D68).

Reads only docs/analysis_results/*.csv (written by scripts/analysis.py run), so every value in
a chart is a value of a query in sql/analysis/.

Usage:
    uv run python scripts/charts.py          # or: make charts
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS = REPO_ROOT / "docs" / "analysis_results"
OUT = REPO_ROOT / "docs" / "images"

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, MUTED = "#2a78d6", "#eb6834", "#b9b8b2"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2,
    "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlecolor": INK,
})


def rows(name: str) -> list[dict]:
    with (RESULTS / f"{name}.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def finish(fig, ax, name: str, source: str) -> None:
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.text(0.01, 0.01, f"Source: {source}", color=INK_2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print(f"  docs/images/{name}")


def top_events() -> None:
    data = rows("q1_top20_all_years")[:10][::-1]
    labels = [f"{r['county']}, {r['state_abbr']} ({r['event_start'][:7]})" for r in data]
    values = [float(r["customer_hours_lost"]) / 1e6 for r in data]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(labels, values, color=BLUE, height=0.6)
    for y, (v, r) in enumerate(zip(values, data, strict=True)):
        storm = "no NOAA storm" if r["storm_type"] == "unmatched" else r["storm_type"]
        ax.text(v + 1, y, f"{v:.1f} M  {storm}", va="center", color=INK_2, fontsize=8.5)
    ax.set_xlim(0, max(values) * 1.35)
    ax.set_xlabel("Customer-hours lost (millions, capped at county customers)")
    ax.set_title("Ten largest outage events, 2022-2025")
    finish(fig, ax, "chart_top10_events.png", "sql/analysis/q1_top_events.sql (q1_top20_all_years)")


def state_ranking() -> None:
    data = [r for r in rows("q2_state_ranks") if r["year"] == "2024" and r["national_rank"] != ""][:15][::-1]
    labels = [f"{r['national_rank']}. {r['state_name']}" for r in data]
    values = [float(r["outage_hours_per_1000"]) for r in data]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.barh(labels, values, color=BLUE, height=0.6)
    for y, v in enumerate(values):
        ax.text(v + 300, y, f"{v:,.0f}", va="center", color=INK_2, fontsize=8.5)
    ax.set_xlim(0, max(values) * 1.15)
    ax.set_xlabel("Outage hours per 1,000 customers (divide by 1,000 for hours per customer)")
    ax.set_title("States with the most outage hours per customer, 2024")
    finish(fig, ax, "chart_state_ranking_2024.png", "sql/analysis/q2_rankings.sql (q2_state_ranks)")


def duration_by_storm() -> None:
    data = [r for r in rows("q4_duration_by_storm") if r["large_median_hours"] != ""][::-1]
    labels = [f"{r['storm_group']} ({int(r['large_events']):,})" for r in data]
    med = [float(r["large_median_hours"]) for r in data]
    p90 = [float(r["large_p90_hours"]) for r in data]
    fig, ax = plt.subplots(figsize=(9, 5))
    for y, (a, b) in enumerate(zip(med, p90, strict=True)):
        ax.plot([a, b], [y, y], color=GRID, linewidth=2, zorder=1)
    ax.scatter(med, range(len(data)), color=BLUE, s=60, zorder=2, label="Median")
    ax.scatter(p90, range(len(data)), color=ORANGE, s=60, zorder=2, label="90th percentile")
    ax.set_yticks(range(len(data)), labels)
    ax.set_xlabel("Event duration in hours (events with 10,000+ customers out at the peak)")
    ax.set_title("How long large outages last, by storm type")
    ax.legend(frameon=False, loc="lower right")
    finish(fig, ax, "chart_duration_by_storm.png", "sql/analysis/q4_restoration.sql (q4_duration_by_storm)")


def yearly_trend() -> None:
    trend, panel = rows("q6_national_trend"), rows("q6_same_counties")
    years = [r["year"] for r in trend]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5), gridspec_kw={"width_ratios": [3, 2]})
    x = range(len(years))
    all_h = [float(r["customer_hours_lost"]) / 1e6 for r in trend]
    pan_h = [float(r["customer_hours_lost"]) / 1e6 for r in panel]
    ax1.bar([i - 0.2 for i in x], all_h, width=0.38, color=BLUE, label="All reporting counties")
    ax1.bar([i + 0.2 for i in x], pan_h, width=0.38, color=ORANGE,
            label=f"Same {int(panel[0]['panel_counties']):,} counties every year")
    ax1.set_xticks(list(x), years)
    ax1.set_ylabel("Customer-hours lost (millions)")
    ax1.set_title("Outage hours per year, 50 states and DC")
    ax1.legend(frameon=False, loc="upper left", fontsize=8.5)
    ax1.grid(axis="y", color=GRID, linewidth=0.8)
    ax1.set_axisbelow(True)
    counties = [int(r["reporting_counties"]) for r in trend]
    ax2.plot(years, counties, color=BLUE, marker="o", linewidth=2)
    for xi, c in zip(years, counties, strict=True):
        ax2.annotate(f"{c:,}", (xi, c), textcoords="offset points", xytext=(0, 8), ha="center",
                     color=INK_2, fontsize=8.5)
    ax2.set_ylim(0, max(counties) * 1.15)
    ax2.set_title("Counties EAGLE-I reports")
    ax2.grid(axis="y", color=GRID, linewidth=0.8)
    ax2.set_axisbelow(True)
    fig.text(0.01, 0.01, "Source: sql/analysis/q6_trend.sql (q6_national_trend, q6_same_counties)", color=INK_2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "chart_yearly_trend.png", dpi=150)
    plt.close(fig)
    print("  docs/images/chart_yearly_trend.png")


def short_name(name: str) -> str:
    for suffix in (" Corp.", " Company", " Co"):
        name = name.removesuffix(suffix)
    return name


def utility_benchmark() -> None:
    data = [r for r in rows("q5_benchmark_latest") if r["size_band"] == "very_large"]
    data.sort(key=lambda r: int(r["rank_saidi_without_med"]))
    year = data[0]["data_year"]
    values = [float(r["saidi_without_med"]) for r in data]
    cap = 400.0  # a few utilities are far above the rest; their bars are cut and labelled
    fig, ax = plt.subplots(figsize=(9, 11))
    ys = range(len(data))[::-1]
    labels = []
    for y, r, v in zip(ys, data, values, strict=True):
        hi = r["is_eversource_or_national_grid"] == "true"
        ax.barh(y, min(v, cap), color=ORANGE if hi else MUTED, height=0.7)
        if v > cap:
            ax.text(cap, y, f"  {v:,.0f} min (cut)", va="center", color=INK_2, fontsize=8)
        labels.append(f"#{r['rank_saidi_without_med']} {short_name(r['utility_name'])} ({r['state_abbr']})" if hi else "")
        if hi:
            ax.text(min(v, cap) + 4, y, f"{v:.1f}", va="center", color=INK, fontsize=8)
    ax.set_yticks(list(ys), labels, fontsize=8.5)
    ax.tick_params(axis="y", length=0)
    srt = sorted(values)
    median = (srt[(len(srt) - 1) // 2] + srt[len(srt) // 2]) / 2
    ax.axvline(median, color=INK_2, linewidth=1, linestyle="--")
    ax.text(median + 4, len(data) - 0.5, f"band median {median:.1f} min", color=INK_2, fontsize=8)
    ax.set_xlim(0, cap * 1.3)
    ax.set_xlabel("SAIDI without major event days, minutes per customer\n"
                  "(orange: Eversource and National Grid companies; 1 = most reliable)")
    ax.set_title(f"The {len(data)} very large utilities by SAIDI, {year}")
    finish(fig, ax, "chart_utility_saidi_benchmark.png", "sql/analysis/q5_utilities.sql (q5_benchmark_latest), EIA-861")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    top_events()
    state_ranking()
    duration_by_storm()
    yearly_trend()
    utility_benchmark()


if __name__ == "__main__":
    main()
