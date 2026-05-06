#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
from enum import Enum
import html
from pathlib import Path


class Unit(Enum):
    BYTES = "Bytes"
    MILLISECONDS = "Milliseconds"


CHARTS = [
    ("install_size_bytes", "install-size.svg", "Install Size", Unit.BYTES),
    ("bob_build_time_ms", "bob-build-time.svg", "Bob Build Time", Unit.MILLISECONDS),
    ("open_time_ms", "open-time.svg", "Open Time", Unit.MILLISECONDS),
    ("memory_after_open_bytes", "memory-after-open.svg", "Memory After Open", Unit.BYTES),
    ("build_time_ms", "build-time.svg", "Build Time", Unit.MILLISECONDS),
    ("memory_added_by_build_bytes", "memory-added-by-build.svg", "Memory Added By Build", Unit.BYTES),
]
PALETTE = ["#0f766e", "#b45309", "#1d4ed8", "#be123c", "#4d7c0f", "#6d28d9"]
FAILURE_COLOR = "#dc2626"
ANNOTATION_COLOR = "#475569"
WIDTH = 960
HEIGHT = 360
PLOT_LEFT = 84
PLOT_RIGHT = 32
PLOT_TOP = 20
PLOT_BOTTOM = 64
VALUE_TICK_INTERVALS = 4
AXIS_HEADROOM = 1.05


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def metric_value(row: dict[str, str], field: str) -> float | None:
    value = (row.get(field) or "").strip()
    if not value:
        return None
    return float(value)


def point_is_failure(row: dict[str, str], field: str) -> bool:
    if row.get("status", "ok") == "ok":
        return False
    if field == "build_time_ms":
        return metric_value(row, field) is not None
    if field == "open_time_ms":
        return metric_value(row, field) is not None and metric_value(row, "build_time_ms") is None
    return False


def format_metric(value: float, unit: Unit) -> str:
    if unit == Unit.BYTES:
        suffixes = ["B", "KiB", "MiB", "GiB"]
        size = value
        for suffix in suffixes:
            if abs(size) < 1024 or suffix == suffixes[-1]:
                return f"{size:.1f} {suffix}" if suffix != "B" else f"{int(size)} B"
            size /= 1024
    if unit == Unit.MILLISECONDS:
        sign = "-" if value < 0 else ""
        duration_ms = abs(value)
        if duration_ms >= 60000:
            total_seconds = int(round(duration_ms / 1000))
            minutes, seconds = divmod(total_seconds, 60)
            return f"{sign}{minutes}m {seconds:02d}s"
        if duration_ms >= 1000:
            return f"{sign}{duration_ms / 1000:.2f} s"
        return f"{sign}{int(duration_ms)} ms"
    return f"{value:.1f}"


def nice_steps(scale: float = 1.0):
    magnitude = 1.0
    while True:
        yield from (
            multiplier * magnitude * scale
            for multiplier in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 4.5, 5.0, 6.0, 7.5, 8.0, 10.0)
        )
        magnitude *= 10.0


def nice_ceiling(value: float, scale: float = 1.0) -> float:
    if value <= 0:
        return scale
    for step in nice_steps(scale):
        if value <= step:
            return step
    raise RuntimeError("unreachable nice step generator exhausted")


def byte_rounding_scale(value: float) -> float:
    absolute = abs(value)
    if absolute >= 1024**3:
        return float(1024**3)
    if absolute >= 1024**2:
        return float(1024**2)
    if absolute >= 1024:
        return float(1024)
    return 1.0


def time_rounding_scale(value: float) -> float:
    if value >= 60000:
        return 60000.0
    if value >= 1000:
        return 1000.0
    return 1.0


def nice_tick_step(target: float, unit: Unit) -> float:
    if unit == Unit.MILLISECONDS:
        return nice_ceiling(target, time_rounding_scale(target))
    if unit == Unit.BYTES:
        scale = byte_rounding_scale(target)
        return nice_ceiling(target, scale)
    return nice_ceiling(target)


def value_tick_step(max_value: float, unit: Unit) -> float:
    target = max_value * AXIS_HEADROOM / VALUE_TICK_INTERVALS
    return nice_tick_step(target, unit)


def value_axis_bounds(values: list[float], unit: Unit) -> tuple[float, float]:
    if not values:
        return 0.0, value_tick_step(1.0, unit) * VALUE_TICK_INTERVALS

    min_observed = min(values)
    max_observed = max(values)
    if min_observed < 0.0 < max_observed:
        candidates: list[tuple[float, float, float]] = []
        for negative_tick_intervals in range(1, VALUE_TICK_INTERVALS):
            positive_tick_intervals = VALUE_TICK_INTERVALS - negative_tick_intervals
            target = max(
                abs(min_observed) * AXIS_HEADROOM / negative_tick_intervals,
                max_observed * AXIS_HEADROOM / positive_tick_intervals,
            )
            step = nice_tick_step(target, unit)
            candidates.append(
                (
                    step * VALUE_TICK_INTERVALS,
                    -step * negative_tick_intervals,
                    step * positive_tick_intervals,
                )
            )
        _range, min_value, max_value = min(candidates)
        return min_value, max_value

    min_value = (
        -value_tick_step(abs(min_observed), unit) * VALUE_TICK_INTERVALS
        if min_observed < 0.0
        else 0.0
    )
    max_value = (
        value_tick_step(max_observed, unit) * VALUE_TICK_INTERVALS
        if max_observed > 0.0
        else 0.0
    )
    if min_value == max_value:
        max_value = value_tick_step(1.0, unit) * VALUE_TICK_INTERVALS
    return min_value, max_value


def series_key(row: dict[str, str]) -> str:
    return "series"


def annotation_rows(rows: list[dict[str, str]]) -> list[tuple[dt.datetime, str]]:
    annotations: list[tuple[dt.datetime, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        comment = (row.get("comment") or "").strip()
        commit_time = (row.get("commit_time") or "").strip()
        if not comment or not commit_time:
            continue
        key = (commit_time, comment)
        if key in seen:
            continue
        seen.add(key)
        annotations.append((parse_time(commit_time), comment))
    annotations.sort(key=lambda item: item[0])
    return annotations


def shorten_annotation(value: str, limit: int = 18) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit - 1]}…"


def render_chart(rows: list[dict[str, str]], field: str, title: str, unit: Unit) -> str:
    plot_width = WIDTH - PLOT_LEFT - PLOT_RIGHT
    plot_height = HEIGHT - PLOT_TOP - PLOT_BOTTOM
    annotations = annotation_rows(rows)
    points_by_series: dict[str, list[tuple[dt.datetime, float, dict[str, str]]]] = {}
    for row in rows:
        value = metric_value(row, field)
        if value is None:
            continue
        points_by_series.setdefault(series_key(row), []).append((parse_time(row["commit_time"]), value, row))
    for points in points_by_series.values():
        points.sort(key=lambda item: item[0])

    all_points = [point for points in points_by_series.values() for point in points]
    all_times = [point[0] for point in all_points] + [timestamp for timestamp, _comment in annotations]
    if not all_times:
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {WIDTH} {HEIGHT}'>"
            f"<rect width='{WIDTH}' height='{HEIGHT}' fill='#fffdf7'/>"
            "<text x='32' y='64' font-size='16' font-family='Helvetica, Arial, sans-serif' fill='#6b7280'>No data yet.</text>"
            "</svg>"
        )

    min_time = min(all_times)
    max_time = max(all_times)
    if all_points:
        min_value, max_value = value_axis_bounds([point[1] for point in all_points], unit)
    else:
        min_value, max_value = value_axis_bounds([], unit)
    if min_time == max_time:
        max_time = min_time + dt.timedelta(days=1)

    def x_pos(timestamp: dt.datetime) -> float:
        total = (max_time - min_time).total_seconds()
        offset = (timestamp - min_time).total_seconds()
        return PLOT_LEFT + (offset / total) * plot_width

    def y_pos(value: float) -> float:
        return PLOT_TOP + plot_height - ((value - min_value) / (max_value - min_value)) * plot_height

    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {WIDTH} {HEIGHT}'>",
        f"<rect width='{WIDTH}' height='{HEIGHT}' rx='20' fill='#fffdf7'/>",
        f"<line x1='{PLOT_LEFT}' y1='{PLOT_TOP + plot_height}' x2='{PLOT_LEFT + plot_width}' y2='{PLOT_TOP + plot_height}' stroke='#cbd5e1' stroke-width='1'/>",
        f"<line x1='{PLOT_LEFT}' y1='{PLOT_TOP}' x2='{PLOT_LEFT}' y2='{PLOT_TOP + plot_height}' stroke='#cbd5e1' stroke-width='1'/>",
    ]

    zero_y = y_pos(0.0)
    parts.append(
        f"<line x1='{PLOT_LEFT}' y1='{zero_y:.2f}' x2='{PLOT_LEFT + plot_width}' y2='{zero_y:.2f}' stroke='#94a3b8' stroke-width='1.5'/>")

    for tick in range(5):
        value = min_value + ((max_value - min_value) * tick / 4)
        y = y_pos(value)
        parts.append(f"<line x1='{PLOT_LEFT}' y1='{y:.2f}' x2='{PLOT_LEFT + plot_width}' y2='{y:.2f}' stroke='#e5e7eb' stroke-width='1'/>")
        parts.append(
            f"<text x='{PLOT_LEFT - 12}' y='{y + 5:.2f}' text-anchor='end' font-size='12' font-family='Helvetica, Arial, sans-serif' fill='#6b7280'>{html.escape(format_metric(value, unit))}</text>"
        )

    dates = [min_time + (max_time - min_time) * tick / 3 for tick in range(4)]
    for timestamp in dates:
        x = x_pos(timestamp)
        label = timestamp.strftime("%Y-%m-%d")
        parts.append(f"<line x1='{x:.2f}' y1='{PLOT_TOP}' x2='{x:.2f}' y2='{PLOT_TOP + plot_height}' stroke='#f1f5f9' stroke-width='1'/>")
        parts.append(
            f"<text x='{x:.2f}' y='{PLOT_TOP + plot_height + 24}' text-anchor='middle' font-size='12' font-family='Helvetica, Arial, sans-serif' fill='#6b7280'>{label}</text>"
        )

    for timestamp, comment in annotations:
        x = x_pos(timestamp)
        label = html.escape(f"{timestamp.strftime('%Y-%m-%d')} {comment}")
        visible = html.escape(shorten_annotation(comment))
        parts.append(
            f"<line x1='{x:.2f}' y1='{PLOT_TOP}' x2='{x:.2f}' y2='{PLOT_TOP + plot_height}' "
            f"stroke='{ANNOTATION_COLOR}' stroke-width='2' stroke-dasharray='6 6' opacity='0.75'>"
            f"<title>{label}</title></line>"
        )
        parts.append(
            f"<text x='{x + 6:.2f}' y='{PLOT_TOP + 10}' transform='rotate(90 {x + 6:.2f} {PLOT_TOP + 10})' "
            f"font-size='11' font-family='Helvetica, Arial, sans-serif' fill='{ANNOTATION_COLOR}'>{visible}</text>"
        )

    show_legend = len(points_by_series) > 1
    legend_y = HEIGHT - 18
    for index, (name, points) in enumerate(sorted(points_by_series.items())):
        color = PALETTE[index % len(PALETTE)]
        coords = [f"{x_pos(timestamp):.2f},{y_pos(value):.2f}" for timestamp, value, _row in points]
        if len(coords) >= 2:
            parts.append(f"<polyline fill='none' stroke='{color}' stroke-width='3' points='{' '.join(coords)}'/>")
        for timestamp, value, row in points:
            x = x_pos(timestamp)
            y = y_pos(value)
            label_text = f"{timestamp.strftime('%Y-%m-%d')} {format_metric(value, unit)}"
            is_failure = point_is_failure(row, field)
            point_color = FAILURE_COLOR if is_failure else color
            if show_legend:
                label_text = f"{name} {label_text}"
            if is_failure and row.get("error", "").strip():
                label_text = f"{label_text} failed: {row['error']}"
            label = html.escape(label_text)
            parts.append(f"<circle cx='{x:.2f}' cy='{y:.2f}' r='4' fill='{point_color}'><title>{label}</title></circle>")
        if show_legend:
            legend_x = 32 + index * 220
            parts.append(f"<rect x='{legend_x}' y='{legend_y - 10}' width='14' height='14' rx='3' fill='{color}'/>")
            parts.append(
                f"<text x='{legend_x + 22}' y='{legend_y + 2}' font-size='12' font-family='Helvetica, Arial, sans-serif' fill='#334155'>{html.escape(name)}</text>"
            )

    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics-csv", required=True)
    parser.add_argument("--charts-dir", required=True)
    args = parser.parse_args()

    rows = read_rows(Path(args.metrics_csv))
    charts_dir = Path(args.charts_dir)
    charts_dir.mkdir(parents=True, exist_ok=True)
    for field, filename, title, unit in CHARTS:
        (charts_dir / filename).write_text(render_chart(rows, field, title, unit))
        print(f"wrote {charts_dir / filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
