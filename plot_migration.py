from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any


WIDTH = 1180
HEIGHT = 760
MARGIN_X = 58
MARGIN_TOP = 66
PANEL_GAP_X = 34
PANEL_GAP_Y = 50
PANEL_WIDTH = 330
PANEL_HEIGHT = 220


def load_results(path: Path) -> tuple[str, list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    title = f"Migracja: {document.get('run_group_id', path.stem)}"
    order = {"none": 0, "ring": 1, "global-best": 2}
    results = sorted(document["results"], key=lambda item: order.get(item["migration_strategy"], 99))
    return title, results


def nice_number(value: float, *, round_value: bool) -> float:
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10**exponent)
    if round_value:
        nice_fraction = 1 if fraction < 1.5 else 2 if fraction < 3 else 5 if fraction < 7 else 10
    else:
        nice_fraction = 1 if fraction <= 1 else 2 if fraction <= 2 else 5 if fraction <= 5 else 10
    return nice_fraction * (10**exponent)


def automatic_axis(values: list[float], ticks: int = 3) -> tuple[float, float]:
    data_min = min(values)
    data_max = max(values)
    if data_min == data_max:
        padding = max(abs(data_min) * 0.1, 1.0)
        data_min -= padding
        data_max += padding

    span = data_max - data_min
    padded_min = data_min - span * 0.12
    padded_max = data_max + span * 0.12

    if data_min >= 0 and padded_min < 0:
        padded_min = 0.0

    step = nice_number((padded_max - padded_min) / ticks, round_value=True)
    axis_min = math.floor(padded_min / step) * step
    axis_max = math.ceil(padded_max / step) * step
    if data_min >= 0 and axis_min < 0:
        axis_min = 0.0
    if axis_min == axis_max:
        axis_max = axis_min + step
    return axis_min, axis_max


def fmt(value: float, suffix: str = "") -> str:
    if abs(value) >= 100:
        text = f"{value:.0f}"
    elif abs(value) >= 10:
        text = f"{value:.1f}"
    else:
        text = f"{value:.2f}"
    return f"{text}{suffix}"


def panel_origin(index: int) -> tuple[int, int]:
    col = index % 3
    row = index // 3
    x = MARGIN_X + col * (PANEL_WIDTH + PANEL_GAP_X)
    y = MARGIN_TOP + row * (PANEL_HEIGHT + PANEL_GAP_Y)
    return x, y


def render_panel(
    index: int,
    title: str,
    key: str,
    results: list[dict[str, Any]],
    color: str,
    suffix: str = "",
    y_min: float | None = None,
    y_max: float | None = None,
) -> str:
    x0, y0 = panel_origin(index)
    plot_x = x0 + 54
    plot_y = y0 + 44
    plot_w = PANEL_WIDTH - 74
    plot_h = PANEL_HEIGHT - 86
    values = [float(item[key]) for item in results]
    auto_min, auto_max = automatic_axis(values)
    min_value = auto_min if y_min is None else y_min
    max_value = auto_max if y_max is None else y_max
    value_span = max_value - min_value
    if value_span <= 0:
        raise ValueError(f"Invalid axis range for {title}: {min_value}..{max_value}")
    bar_gap = 18
    bar_w = (plot_w - bar_gap * (len(results) - 1)) / len(results)

    elements = [
        f'<text x="{x0}" y="{y0 + 18}" font-size="17" font-weight="700" fill="#111827">{html.escape(title)}</text>',
        f'<line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_h}" stroke="#111827" />',
        f'<line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + plot_w}" y2="{plot_y + plot_h}" stroke="#111827" />',
    ]

    for tick in range(4):
        value = min_value + value_span * tick / 3
        y = plot_y + plot_h - ((value - min_value) / value_span) * plot_h
        elements.append(
            f'<line x1="{plot_x}" y1="{y:.2f}" x2="{plot_x + plot_w}" y2="{y:.2f}" stroke="#e5e7eb" />'
        )
        elements.append(
            f'<text x="{plot_x - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="11" fill="#4b5563">'
            f"{fmt(value, suffix)}</text>"
        )

    for pos, item in enumerate(results):
        value = float(item[key])
        clamped_value = min(max(value, min_value), max_value)
        bar_h = ((clamped_value - min_value) / value_span) * plot_h
        x = plot_x + pos * (bar_w + bar_gap)
        y = plot_y + plot_h - bar_h
        strategy = str(item["migration_strategy"])
        elements.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" '
            f'fill="{color}" opacity="0.88">'
            f"<title>{html.escape(strategy)}: {fmt(value, suffix)}</title></rect>"
        )
        elements.append(
            f'<text x="{x + bar_w / 2:.2f}" y="{y - 7:.2f}" text-anchor="middle" '
            f'font-size="12" font-weight="700" fill="{color}">{fmt(value, suffix)}</text>'
        )
        elements.append(
            f'<text x="{x + bar_w / 2:.2f}" y="{plot_y + plot_h + 24}" text-anchor="middle" '
            'font-size="12" fill="#374151">'
            f"{html.escape(strategy)}</text>"
        )

    return "\n".join(elements)


def render_svg(title: str, results: list[dict[str, Any]]) -> str:
    panels = [
        ("Najlepszy dystans", "best_distance_mean", "#2563eb", "", None, None),
        ("Poprawa dystansu vs none", "improvement_vs_none_percent", "#16a34a", "%", None, None),
        ("Czas wykonania", "mean_time_seconds", "#dc2626", "s", None, None),
        ("Czas migracji", "migration_seconds_mean", "#7c3aed", "s", None, None),
        ("Narzut migracji [stosunek]", "migration_overhead_ratio_mean", "#ea580c", "", None, None),
        ("Roznorodnosc krawedzi [0-1]", "edge_diversity_mean", "#0891b2", "", 0.0, 1.0),
    ]
    panel_elements = [
        render_panel(index, panel_title, key, results, color, suffix, y_min, y_max)
        for index, (panel_title, key, color, suffix, y_min, y_max) in enumerate(panels)
    ]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<rect width="100%" height="100%" fill="#ffffff" />
<g font-family="Arial, sans-serif">
<text x="{WIDTH / 2:.0f}" y="34" text-anchor="middle" font-size="24" font-weight="700" fill="#111827">{html.escape(title)}</text>
{"".join(panel_elements)}
</g>
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an SVG chart from evaluate-quality migration JSON output.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    title, results = load_results(args.input_json)
    output = args.output or args.input_json.with_suffix(".svg")
    output.write_text(render_svg(title, results), encoding="utf-8")
    print(f"Chart written to: {output}")


if __name__ == "__main__":
    main()
