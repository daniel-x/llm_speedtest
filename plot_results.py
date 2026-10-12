#!/usr/bin/env python3
"""Plots TTFT, output rates and duration over time for each prompt from llm_speedtest_results.csv.

Computes the output rates from the CSV columns, see add_output_rates. Writes scatter plots above
each other to llm_speedtest_plot.webp next to this script, one each for TTFT reported by Claude
Code, output rate timed by Claude Code, output rate timed by llm_speedtest.py and duration timed by
llm_speedtest.py. Each prompt has its own color and marker shape. All y-axes are logarithmic, start
at the power of 10 at or below the smallest value and extend upward far enough that all markers
stay below the legend in the top right. The time axis spans at least MIN_TIME_SPAN from the first
measurement. The background is light grey, except for US office hours, which are white. This script
takes US office hours as weekdays from 9:00 US Eastern time to 17:00 US Pacific time.
"""

import argparse
import csv
import fnmatch
import math
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Patch

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "llm_speedtest_results.csv"
PLOT_FILE = BASE_DIR / "llm_speedtest_plot.webp"
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
MAX_DECADES_FOR_125_TICKS = 3
LAYOUT_PASSES = 2
PROMPT_STYLES = [("#2a78d6", "o"), ("#eb6834", "P"), ("#1baf7a", "s"), ("#8a5bd6", "D")]

METRICS = [
    ("claude_code_ttft_s", "TTFT, reported by Claude Code [s]"),
    ("claude_code_api_tok_s", "output rate, timed by Claude Code [tok/s]"),
    ("llm_speedtest_tok_s",
     "output rate, timed by llm_speedtest [tok/s]\n(outside process that starts Claude Code)"),
    ("llm_speedtest_duration_s",
     "duration, timed by llm_speedtest [s]\n(outside process that starts Claude Code)"),
]


def load_rows(model_pattern):
    """Returns the CSV rows whose model ID matches the shell-style wildcard pattern, or all rows if
    the pattern is "all"."""
    with LOG_FILE.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f)
                if model_pattern == "all" or fnmatch.fnmatchcase(r["model"], model_pattern)]


def number(text):
    """Returns the CSV value as float, or None if it is empty."""
    return float(text) if text else None


def ratio(numerator, denominator):
    """Returns numerator / denominator, or None if a value is None or the denominator is not
    positive."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def add_output_rates(rows):
    """Adds the output rates in tokens per second to each row:
    claude_code_api_tok_s = output_token_count / claude_code_api_duration_s,
    llm_speedtest_tok_s = output_token_count / llm_speedtest_duration_s."""
    for r in rows:
        output_token_count = number(r["output_token_count"])
        r["claude_code_api_tok_s"] = ratio(output_token_count,
                                           number(r["claude_code_api_duration_s"]))
        r["llm_speedtest_tok_s"] = ratio(output_token_count,
                                         number(r["llm_speedtest_duration_s"]))


def has_positive_value(row, key):
    """Returns whether the row has a value above 0 for the metric, which a log axis can show."""
    return bool(row[key]) and float(row[key]) > 0


def metric_range(rows, key):
    """Returns the smallest and largest positive value of the metric in the rows, or (1, 10) if no
    row has a positive value for it."""
    values = [float(r[key]) for r in rows if has_positive_value(r, key)]
    return (min(values), max(values)) if values else (1, 10)


def setup_log_y_axis(ax, data_min):
    """Makes the y-axis logarithmic and puts its lower limit at the power of 10 at or below
    data_min."""
    ax.set_yscale("log")
    ax.set_ylim(bottom=10 ** math.floor(math.log10(data_min)))


def set_log_y_ticks(ax):
    """Labels the logarithmic y-axis with plain numbers, at 1, 2 and 5 times each power of 10 if the
    axis spans at most MAX_DECADES_FOR_125_TICKS decades, else only at powers of 10."""
    bottom, top = ax.get_ylim()
    subs = (1, 2, 5) if math.log10(top / bottom) <= MAX_DECADES_FOR_125_TICKS else (1,)
    ax.yaxis.set_major_locator(mticker.LogLocator(subs=subs))
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda y, _: f"{y:,.0f}" if y >= 1 else f"{y:g}"))
    ax.yaxis.set_minor_locator(mticker.LogLocator(subs=range(1, 10)))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())


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
    """Sets the upper limit of the logarithmic y-axis so that markers up to data_max end
    LEGEND_GAP_PT below the legend, keeping the lower limit.

    Requires a drawn figure with the final layout, because it measures the legend in pixels."""
    pt_to_px = ax.figure.dpi / 72
    axes_box = ax.get_window_extent()
    legend_box = ax.get_legend().get_window_extent()
    marker_radius_pt = MARKER_AREA ** 0.5 / 2
    usable_px = legend_box.y0 - axes_box.y0 - (marker_radius_pt + LEGEND_GAP_PT) * pt_to_px
    log_bottom = math.log10(ax.get_ylim()[0])
    log_top = log_bottom + (math.log10(data_max) - log_bottom) * axes_box.height / usable_px
    ax.set_ylim(top=10 ** log_top)


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
    parser.add_argument("--model", default="claude-opus-*",
                        help="plot only model IDs matching this pattern, wildcards allowed, e.g. "
                             "claude-opus-5-5 or claude-sonnet-*; \"all\" plots all models "
                             "(default: %(default)s)")
    args = parser.parse_args()

    rows = load_rows(args.model)
    if not rows:
        raise SystemExit(f"no measurements for model {args.model} in {LOG_FILE}")
    add_output_rates(rows)
    series = list(dict.fromkeys((r["model"], r["prompt_name"]) for r in rows))
    times = [datetime.fromisoformat(r["timestamp_utc"]) for r in rows]
    x_min = min(times) - TIME_PADDING
    x_max = max(max(times) + TIME_PADDING, x_min + MIN_TIME_SPAN)
    fig, axes = plt.subplots(len(METRICS), 1, figsize=(11, 4 * len(METRICS)), sharex=True)
    axes[0].set_xlim(x_min, x_max)
    for ax, (key, label) in zip(axes, METRICS):
        for (model_id, prompt_name), (color, marker) in zip(series, PROMPT_STYLES):
            series_rows = [r for r in rows
                           if (r["model"], r["prompt_name"]) == (model_id, prompt_name)
                           and has_positive_value(r, key)]
            ax.scatter([datetime.fromisoformat(r["timestamp_utc"]) for r in series_rows],
                       [float(r[key]) for r in series_rows], s=MARKER_AREA, color=color, marker=marker,
                       edgecolors="white", linewidths=1, zorder=3,
                       label=f"{short_model_name(model_id)}, prompt: {prompt_name}")
        mark_us_office_hours(ax)
        data_min, data_max = metric_range(rows, key)
        setup_log_y_axis(ax, data_min)
        ax.set_ylim(top=data_max)
        ax.set_ylabel(label)
        ax.set_xlabel("time (UTC)")
        ax.tick_params(axis="x", labelbottom=True, rotation=30)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
        ax.grid(which="major", color="#e5e5e5", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        handles, labels = ax.get_legend_handles_labels()
        handles = [Patch(facecolor=OFFICE_COLOR, edgecolor="#c8c8c8") if lbl == OFFICE_LABEL
                   else h for h, lbl in zip(handles, labels)]
        ax.legend(handles, labels, loc="upper right", frameon=True, facecolor="white", framealpha=0.75,
                  edgecolor="#c8c8c8")
    for _ in range(LAYOUT_PASSES):
        fig.tight_layout()
        fig.canvas.draw()
        for ax, (key, _) in zip(axes, METRICS):
            fit_ylim_below_legend(ax, metric_range(rows, key)[1])
            set_log_y_ticks(ax)
    fig.savefig(PLOT_FILE, dpi=120, pil_kwargs={"lossless": True, "quality": 100})


if __name__ == "__main__":
    main()
