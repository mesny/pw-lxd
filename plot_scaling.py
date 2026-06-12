from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


WIDTH = 980
HEIGHT = 640
MARGIN_LEFT = 74
MARGIN_RIGHT = 54
MARGIN_TOP = 54
MARGIN_BOTTOM = 78
PLOT_WIDTH = WIDTH - MARGIN_LEFT - MARGIN_RIGHT
PLOT_HEIGHT = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM


def load_results(path: Path) -> tuple[str, list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    title = f"Skalowanie: {document.get('run_group_id', path.stem)}"
    results = sorted(document["results"], key=lambda item: item["np"])
    return title, results


def load_total_time(path: Path) -> float:
    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)
    return float(report["metrics"]["performance_measures"]["total_time_seconds_T_p"])


def add_sequential_baseline(results: list[dict[str, Any]], sequential_path: Path) -> list[dict[str, Any]]:
    sequential_time = load_total_time(sequential_path)
    rows = [
        {
            **item,
            "speedup_vs_sequential_S_1": sequential_time / float(item["mean_time_seconds_T_p"]),
            "efficiency_vs_sequential_E_1": (
                sequential_time / float(item["mean_time_seconds_T_p"]) / float(item["np"])
            ),
        }
        for item in results
    ]
    rows.append({
            "np": 1,
            "runs": 1,
            "mean_time_seconds_T_p": sequential_time,
            "speedup_vs_sequential_S_1": 1.0,
            "efficiency_vs_sequential_E_1": 1.0,
            "best_distance_min": None,
            "best_distance_mean": None,
            "edge_diversity_mean": None,
        }
    )
    return sorted(rows, key=lambda item: item["np"])


def nice_upper(value: float) -> float:
    if value <= 1:
        return 1.0
    if value <= 5:
        return float(int(value + 0.999999))
    step = 5
    return float(((int(value) + step - 1) // step) * step)


def points(results: list[dict[str, Any]], key: str, y_max: float) -> list[tuple[float, float]]:
    min_np = min(item["np"] for item in results)
    max_np = max(item["np"] for item in results)
    span = max(max_np - min_np, 1)
    output = []
    for item in results:
        x = MARGIN_LEFT + ((item["np"] - min_np) / span) * PLOT_WIDTH
        y = MARGIN_TOP + (1 - (float(item[key]) / y_max)) * PLOT_HEIGHT
        output.append((x, y))
    return output


def polyline(point_list: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in point_list)


def y_grid(y_max: float, ticks: int = 5) -> str:
    elements = []
    for i in range(ticks + 1):
        value = y_max * i / ticks
        y = MARGIN_TOP + (1 - i / ticks) * PLOT_HEIGHT
        elements.append(
            f'<line x1="{MARGIN_LEFT}" y1="{y:.2f}" x2="{WIDTH - MARGIN_RIGHT}" y2="{y:.2f}" '
            'stroke="#e5e7eb" />'
        )
        elements.append(
            f'<text x="{MARGIN_LEFT - 12}" y="{y + 4:.2f}" text-anchor="end" '
            'font-size="12" fill="#4b5563">'
            f"{value:.1f}</text>"
        )
    return "\n".join(elements)


def label_text(value: float) -> str:
    return f"{value:.2f}"


def value_label(x: float, y: float, text: str, color: str, dx: int, dy: int) -> str:
    label_width = max(34, len(text) * 7 + 10)
    label_height = 18
    label_x = x + dx
    label_y = y + dy
    rect_x = label_x - label_width / 2
    rect_y = label_y - label_height + 4
    return (
        f'<rect x="{rect_x:.2f}" y="{rect_y:.2f}" width="{label_width}" height="{label_height}" '
        'rx="3" fill="#ffffff" stroke="#e5e7eb" />'
        f'<text x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="middle" '
        f'font-size="12" font-weight="700" fill="{color}">{html.escape(text)}</text>'
    )


def render_svg(title: str, results: list[dict[str, Any]]) -> str:
    has_sequential = all(
        "speedup_vs_sequential_S_1" in item and "efficiency_vs_sequential_E_1" in item
        for item in results
    )
    speedup_key = "speedup_vs_sequential_S_1" if has_sequential else "relative_speedup_S_ref"
    efficiency_key = "efficiency_vs_sequential_E_1" if has_sequential else "relative_efficiency_E_ref"
    speedup_label = "Speedup S(1)" if has_sequential else "Speedup S_ref"
    efficiency_label = "Efektywnosc E(1)" if has_sequential else "Efektywnosc E_ref"

    y_max = nice_upper(
        max(
            max(float(item["mean_time_seconds_T_p"]) for item in results),
            max(float(item[speedup_key]) for item in results),
            max(float(item[efficiency_key]) for item in results),
        )
    )
    series = [
        ("Czas T(p) [s]", "mean_time_seconds_T_p", "#2563eb", -28, -12),
        (speedup_label, speedup_key, "#16a34a", 28, -12),
        (efficiency_label, efficiency_key, "#dc2626", 0, 24),
    ]

    x_labels = []
    for item in results:
        min_np = min(row["np"] for row in results)
        max_np = max(row["np"] for row in results)
        span = max(max_np - min_np, 1)
        x = MARGIN_LEFT + ((item["np"] - min_np) / span) * PLOT_WIDTH
        x_labels.append(
            f'<line x1="{x:.2f}" y1="{MARGIN_TOP}" x2="{x:.2f}" y2="{HEIGHT - MARGIN_BOTTOM}" '
            'stroke="#f3f4f6" />'
            f'<text x="{x:.2f}" y="{HEIGHT - MARGIN_BOTTOM + 28}" text-anchor="middle" '
            'font-size="13" fill="#374151">'
            f'{item["np"]}</text>'
        )

    series_elements = []
    legend_elements = []
    for index, (label, key, color, dx, dy) in enumerate(series):
        point_list = points(results, key, y_max)
        series_elements.append(
            f'<polyline points="{polyline(point_list)}" fill="none" stroke="{color}" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
        )
        for (x, y), item in zip(point_list, results, strict=True):
            value = float(item[key])
            series_elements.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" fill="{color}">'
                f'<title>np={item["np"]}, {html.escape(label)}={value:.3f}</title>'
                "</circle>"
            )
            series_elements.append(value_label(x, y, label_text(value), color, dx, dy))
        legend_x = MARGIN_LEFT + index * 215
        legend_y = HEIGHT - 22
        legend_elements.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 26}" y2="{legend_y}" '
            f'stroke="{color}" stroke-width="3" />'
            f'<text x="{legend_x + 34}" y="{legend_y + 4}" font-size="13" fill="#111827">'
            f"{html.escape(label)}</text>"
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<rect width="100%" height="100%" fill="#ffffff" />
<text x="{WIDTH / 2:.0f}" y="30" text-anchor="middle" font-size="22" font-family="Arial, sans-serif" font-weight="700" fill="#111827">{html.escape(title)}</text>
<g font-family="Arial, sans-serif">
{y_grid(y_max)}
{"".join(x_labels)}
<line x1="{MARGIN_LEFT}" y1="{MARGIN_TOP}" x2="{MARGIN_LEFT}" y2="{HEIGHT - MARGIN_BOTTOM}" stroke="#111827" />
<line x1="{MARGIN_LEFT}" y1="{HEIGHT - MARGIN_BOTTOM}" x2="{WIDTH - MARGIN_RIGHT}" y2="{HEIGHT - MARGIN_BOTTOM}" stroke="#111827" />
<text x="{WIDTH / 2:.0f}" y="{HEIGHT - 40}" text-anchor="middle" font-size="14" fill="#111827">Liczba procesow MPI (np)</text>
<text x="22" y="{HEIGHT / 2:.0f}" text-anchor="middle" transform="rotate(-90 22 {HEIGHT / 2:.0f})" font-size="14" fill="#111827">Wartosc</text>
{"".join(series_elements)}
{"".join(legend_elements)}
</g>
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an SVG chart from evaluate-scaling JSON output.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--sequential", type=Path, default=None)
    args = parser.parse_args()

    title, results = load_results(args.input_json)
    if args.sequential:
        results = add_sequential_baseline(results, args.sequential)
        title = f"{title} vs sekwencyjne"
    output = args.output or args.input_json.with_suffix(".svg")
    output.write_text(render_svg(title, results), encoding="utf-8")
    print(f"Chart written to: {output}")


if __name__ == "__main__":
    main()
