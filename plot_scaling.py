from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt


def load_results(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Load scaling evaluator output and return a chart title with rows."""

    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    title = f"Skalowanie: {document.get('run_group_id', path.stem)}"
    results = sorted(document["results"], key=lambda item: item["np"])
    return title, results


def load_total_time(path: Path) -> float:
    """Read total execution time from a single run report."""

    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)
    return float(report["metrics"]["performance_measures"]["total_time_seconds_T_p"])


def add_sequential_baseline(results: list[dict[str, Any]], sequential_path: Path) -> list[dict[str, Any]]:
    """Add sequential baseline metrics to scaling rows."""

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
    rows.append(
        {
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


def choose_series(results: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    """Choose speedup and efficiency fields available in the input rows."""

    has_sequential = all(
        "speedup_vs_sequential_S_1" in item and "efficiency_vs_sequential_E_1" in item
        for item in results
    )
    if has_sequential:
        return [
            ("Czas T(p) [s]", "mean_time_seconds_T_p", "#2563eb", "time"),
            ("Przyspieszenie S(1)", "speedup_vs_sequential_S_1", "#16a34a", "speedup"),
            ("Efektywność E(1)", "efficiency_vs_sequential_E_1", "#dc2626", "efficiency"),
        ]
    return [
        ("Czas T(p) [s]", "mean_time_seconds_T_p", "#2563eb", "time"),
        ("Przyspieszenie S_ref", "relative_speedup_S_ref", "#16a34a", "speedup"),
        ("Efektywność E_ref", "relative_efficiency_E_ref", "#dc2626", "efficiency"),
    ]


def style_axes(ax, x_values: list[int], ylabel: str = "Wartość") -> None:
    """Apply common styling to scaling chart axes."""

    ax.set_xlabel("Liczba procesów MPI (np)")
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_values)
    ax.grid(True, color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def annotate_points(ax, x_values: list[int], y_values: list[float], color: str) -> None:
    """Add value labels above plotted points."""

    for x, y in zip(x_values, y_values, strict=True):
        ax.annotate(
            f"{y:.2f}",
            xy=(x, y),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            color=color,
            fontweight="bold",
            fontsize=9,
        )


def render_series_chart(
    title: str,
    series: tuple[str, str, str, str],
    results: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Render one scaling series as a standalone PNG chart."""

    label, key, color, _slug = series
    x_values = [int(item["np"]) for item in results]
    y_values = [float(item[key]) for item in results]
    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=180)
    ax.plot(x_values, y_values, marker="o", linewidth=2.5, label=label, color=color)
    annotate_points(ax, x_values, y_values, color)
    ax.set_title(f"{title} - {label}", fontweight="bold", pad=14)
    style_axes(ax, x_values, label)
    ax.margins(y=0.18)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def render_combined_chart(title: str, results: list[dict[str, Any]], output_path: Path) -> None:
    """Render all scaling series in one optional PNG chart."""

    x_values = [int(item["np"]) for item in results]
    fig, ax = plt.subplots(figsize=(9.8, 6.4), dpi=160)
    for label, key, color, _slug in choose_series(results):
        y_values = [float(item[key]) for item in results]
        ax.plot(x_values, y_values, marker="o", linewidth=2.5, label=label, color=color)
        annotate_points(ax, x_values, y_values, color)

    ax.set_title(title, fontweight="bold", pad=14)
    style_axes(ax, x_values)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncols=3, frameon=False)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def output_path_for_series(output_prefix: Path, slug: str) -> Path:
    """Build a deterministic PNG output path for one scaling series."""

    return output_prefix.with_name(f"{output_prefix.name}-{slug}.png")


def main() -> None:
    """CLI entry point for generating scaling PNG charts."""

    parser = argparse.ArgumentParser(description="Generate a PNG chart from evaluate-scaling JSON output.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--sequential", type=Path, default=None)
    parser.add_argument("--combined", action="store_true", help="Write one combined PNG instead of separate charts")
    args = parser.parse_args()

    title, results = load_results(args.input_json)
    if args.sequential:
        results = add_sequential_baseline(results, args.sequential)
        title = f"{title} vs sekwencyjne"
    output_prefix = (args.output or args.input_json).with_suffix("")
    if args.combined:
        output = output_prefix.with_suffix(".png")
        render_combined_chart(title, results, output)
        print(f"Chart written to: {output}")
        return

    for series in choose_series(results):
        output = output_path_for_series(output_prefix, series[3])
        render_series_chart(title, series, results, output)
        print(f"Chart written to: {output}")


if __name__ == "__main__":
    main()
