#!/usr/bin/env python3
"""Plots TTFT, decode speed and wall duration over time for each prompt from
llm_speedtest_results.csv.

Writes scatter plots above each other to llm_speedtest_plot.png next to this script, one each for
TTFT, decode speed and, unless --no-wall-duration is given, the wall-clock duration measured by
llm_speedtest.py. Each prompt has its own color and marker shape. All y-axes start at 0 and extend
upward far enough that all markers stay below the legend in the top right. The time axis spans at
least MIN_TIME_SPAN from the first measurement. The background is light grey, except for US
office hours, which are white. This script takes US office hours as weekdays from 9:00 US Eastern
time to 17:00 US Pacific time.
"""

import argparse
import csv
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "llm_speedtest_results.csv"
PLOT_FILE = BASE_DIR / "llm_speedtest_plot.png"
OFFICE_START = (ZoneInfo("America/New_York"), time(9), "US/NY")
OFFICE_END = (ZoneInfo("America/Los_Angeles"), time(17), "US/LA")
BACKGROUND_COLOR = "#f3f3f3"
OFFICE_COLOR = "#ffffff"
OFFICE_LABEL = (f"US office hours: Mon-Fri {OFFICE_START[1]:%H:%M} {OFFICE_START[2]}"
                f" to {OFFICE_END[1]:%H:%M} {OFFICE_END[2]}")
MIN_TIME_SPAN = timedelta(days=3)
TIME_PADDING = timedelta(minutes=30)
MARKER_AREA = 50
LEGEND_GAP_PT = 6
PROMPT_STYLES = [("#2a78d6", "o"), ("#eb6834", "^"), ("#1baf7a", "s"), ("#8a5bd6", "D")]

METRICS = [
    ("ttft_s", "TTFT [s]"),
    ("decode_tok_s", "speed [tok/s]"),
]
WALL_DURATION_METRIC = ("wall_duration_s", "wall duration [s]")


def load_rows(model):
    """Returns the CSV rows, only those of the given model ID if model is set."""
    with LOG_FILE.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if not model or r["model"] == model]


def metric_max(rows, key):
    """Returns the largest value of the metric in the rows, or 1 if no row has a value for it."""
    return max((float(r[key]) for r in rows if r[key]), default=1)


def us_office_spans(start, end):
    """Returns the (start, end) pairs of US office hours as naive UTC datetimes that overlap the
    given naive UTC range."""
    spans = []
    day = start.date() - timedelta(days=1)
    while day <= end.date() + timedelta(days=1):
        if day.weekday() < 5:
            span = tuple(datetime.combine(day, clock, tz).astimezone(timezone.utc).replace(tzinfo=None)
                         for tz, clock, _ in (OFFICE_START, OFFICE_END))
            if span[1] > start and span[0] < end:
                spans.append(span)
        day += timedelta(days=1)
    return spans


def mark_us_office_hours(ax):
    """Paints the axes background grey and US office hours within its current x range white."""
    x_min, x_max = (mdates.num2date(x).replace(tzinfo=None) for x in ax.get_xlim())
    ax.set_facecolor(BACKGROUND_COLOR)
    label = OFFICE_LABEL
    for office_start, office_end in us_office_spans(x_min, x_max):
        ax.axvspan(max(office_start, x_min), min(office_end, x_max), color=OFFICE_COLOR,
                   linewidth=0, zorder=0, label=label)
        label = None
    ax.set_xlim(x_min, x_max)


def fit_ylim_below_legend(ax, data_max):
    """Sets the upper y limit so that markers up to data_max end LEGEND_GAP_PT below the legend.

    Requires a drawn figure with the final layout, because it measures the legend in pixels."""
    pt_to_px = ax.figure.dpi / 72
    axes_box = ax.get_window_extent()
    legend_box = ax.get_legend().get_window_extent()
    marker_radius_pt = MARKER_AREA ** 0.5 / 2
    usable_px = legend_box.y0 - axes_box.y0 - (marker_radius_pt + LEGEND_GAP_PT) * pt_to_px
    ax.set_ylim(bottom=0, top=data_max * axes_box.height / usable_px)


def short_model_name(model_id):
    """Returns the family and version of a Claude model ID, e.g. "Opus 5.5" for "claude-opus-5-5".
    Other IDs are returned unchanged."""
    match = re.fullmatch(r"claude-([a-z]+)-(\d+)-(\d+)(-\d{8})?", model_id)
    if not match:
        return model_id
    family, major, minor, _ = match.groups()
    return f"{family.capitalize()} {major}.{minor}"



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="plot only this model ID, e.g. claude-opus-5-5")
    parser.add_argument("--wall-duration", action=argparse.BooleanOptionalAction, default=True,
                        help="plot the wall duration measured by llm_speedtest.py (default: on)")
    args = parser.parse_args()

    rows = load_rows(args.model)
    if not rows:
        raise SystemExit(f"no measurements for model {args.model} in {LOG_FILE}")
    series = list(dict.fromkeys((r["model"], r["prompt_name"]) for r in rows))
    times = [datetime.fromisoformat(r["timestamp_utc"]) for r in rows]
    x_min = min(times) - TIME_PADDING
    x_max = max(max(times) + TIME_PADDING, x_min + MIN_TIME_SPAN)
    metrics = METRICS + ([WALL_DURATION_METRIC] if args.wall_duration else [])
    fig, axes = plt.subplots(len(metrics), 1, figsize=(11, 4 * len(metrics)), sharex=True)
    axes[0].set_xlim(x_min, x_max)
    for ax, (key, label) in zip(axes, metrics):
        for (model_id, prompt_name), (color, marker) in zip(series, PROMPT_STYLES):
            series_rows = [r for r in rows
                           if (r["model"], r["prompt_name"]) == (model_id, prompt_name) and r[key]]
            ax.scatter([datetime.fromisoformat(r["timestamp_utc"]) for r in series_rows],
                       [float(r[key]) for r in series_rows], s=MARKER_AREA, color=color, marker=marker,
                       edgecolors="white", linewidths=1, zorder=3,
                       label=f"{short_model_name(model_id)}, prompt: {prompt_name}")
        mark_us_office_hours(ax)
        ax.set_ylim(bottom=0, top=metric_max(rows, key))
        ax.set_ylabel(label)
        ax.set_xlabel("time (UTC)")
        ax.tick_params(axis="x", labelbottom=True, rotation=30)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
        ax.grid(color="#e5e5e5", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        handles, labels = ax.get_legend_handles_labels()
        handles = [Patch(facecolor=OFFICE_COLOR, edgecolor="#c8c8c8") if lbl == OFFICE_LABEL
                   else h for h, lbl in zip(handles, labels)]
        ax.legend(handles, labels, loc="upper right", frameon=True, facecolor="white", framealpha=0.75,
                  edgecolor="#c8c8c8")
    fig.tight_layout()
    fig.canvas.draw()
    for ax, (key, _) in zip(axes, metrics):
        fit_ylim_below_legend(ax, metric_max(rows, key))
    fig.savefig(PLOT_FILE, dpi=120)


if __name__ == "__main__":
    main()
