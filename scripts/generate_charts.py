#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import html
from pathlib import Path


CHARTS = [
    ("install_size_bytes", "install-size.svg", "Install Size", "Bytes"),
    ("open_time_ms", "open-time.svg", "Open Time", "Milliseconds"),
    ("memory_after_open_bytes", "memory-after-open.svg", "Memory After Open", "Bytes"),
    ("build_time_ms", "build-time.svg", "Build Time", "Milliseconds"),
    ("memory_added_by_build_bytes", "memory-added-by-build.svg", "Memory Added By Build", "Bytes"),
]
PALETTE = ["#0f766e", "#b45309", "#1d4ed8", "#be123c", "#4d7c0f", "#6d28d9"]
FAILURE_COLOR = "#dc2626"
WIDTH = 960
HEIGHT = 360
PLOT_LEFT = 84
PLOT_RIGHT = 32
PLOT_TOP = 20
PLOT_BOTTOM = 64


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def metric_value(row: dict[str, str], field: str) -> float | None:
    value = row.get(field, "").strip()
    if not value:
        return None
    return float(value)


def format_metric(value: float, unit: str) -> str:
    if unit == "Bytes":
        suffixes = ["B", "KiB", "MiB", "GiB"]
        size = value
        for suffix in suffixes:
            if abs(size) < 1024 or suffix == suffixes[-1]:
                return f"{size:.1f} {suffix}" if suffix != "B" else f"{int(size)} B"
            size /= 1024
    if unit == "Milliseconds":
        if value >= 1000:
            return f"{value / 1000:.2f} s"
        return f"{int(value)} ms"
    return f"{value:.1f}"


def series_key(row: dict[str, str]) -> str:
    return "series"


def failure_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("status", "ok") != "ok" and row.get("commit_time", "").strip()]


def render_chart(rows: list[dict[str, str]], field: str, title: str, unit: str) -> str:
    plot_width = WIDTH - PLOT_LEFT - PLOT_RIGHT
    plot_height = HEIGHT - PLOT_TOP - PLOT_BOTTOM
    points_by_series: dict[str, list[tuple[dt.datetime, float]]] = {}
    failures = failure_rows(rows)
    for row in rows:
        value = metric_value(row, field)
        if value is None:
            continue
        points_by_series.setdefault(series_key(row), []).append((parse_time(row["commit_time"]), value))
    for points in points_by_series.values():
        points.sort(key=lambda item: item[0])

    all_points = [point for points in points_by_series.values() for point in points]
    failure_times = [parse_time(row["commit_time"]) for row in failures]
    all_times = [point[0] for point in all_points] + failure_times
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
        min_value = min(point[1] for point in all_points)
        max_value = max(point[1] for point in all_points)
        min_value = min(0.0, min_value)
    else:
        min_value = 0.0
        max_value = 1.0
    if min_time == max_time:
        max_time = min_time + dt.timedelta(days=1)
    if min_value == max_value:
        padding = max(1.0, abs(min_value) * 0.05)
        min_value -= padding
        max_value += padding
    value_padding = (max_value - min_value) * 0.1
    min_value -= value_padding
    max_value += value_padding

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

    show_legend = len(points_by_series) > 1
    legend_y = HEIGHT - 18
    for index, (name, points) in enumerate(sorted(points_by_series.items())):
        color = PALETTE[index % len(PALETTE)]
        coords = [f"{x_pos(timestamp):.2f},{y_pos(value):.2f}" for timestamp, value in points]
        if len(coords) >= 2:
            parts.append(f"<polyline fill='none' stroke='{color}' stroke-width='3' points='{' '.join(coords)}'/>")
        for timestamp, value in points:
            x = x_pos(timestamp)
            y = y_pos(value)
            label_text = f"{timestamp.strftime('%Y-%m-%d')} {format_metric(value, unit)}"
            if show_legend:
                label_text = f"{name} {label_text}"
            label = html.escape(label_text)
            parts.append(f"<circle cx='{x:.2f}' cy='{y:.2f}' r='4' fill='{color}'><title>{label}</title></circle>")
        if show_legend:
            legend_x = 32 + index * 220
            parts.append(f"<rect x='{legend_x}' y='{legend_y - 10}' width='14' height='14' rx='3' fill='{color}'/>")
            parts.append(
                f"<text x='{legend_x + 22}' y='{legend_y + 2}' font-size='12' font-family='Helvetica, Arial, sans-serif' fill='#334155'>{html.escape(name)}</text>"
            )

    failure_y = PLOT_TOP + 14
    for row in failures:
        timestamp = parse_time(row["commit_time"])
        x = x_pos(timestamp)
        label = html.escape(f"{timestamp.strftime('%Y-%m-%d')} failed: {row.get('error', 'benchmark failed')}")
        parts.append(f"<line x1='{x:.2f}' y1='{PLOT_TOP}' x2='{x:.2f}' y2='{PLOT_TOP + plot_height}' stroke='{FAILURE_COLOR}' stroke-width='1' stroke-dasharray='4 4' opacity='0.6'/>")
        parts.append(f"<circle cx='{x:.2f}' cy='{failure_y:.2f}' r='6' fill='{FAILURE_COLOR}'><title>{label}</title></circle>")

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
