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


PANEL_SPECS = [
    ("Najlepszy dystans", "best_distance_mean", "#2563eb", "", 3550.0, 3750.0),
    ("Poprawa dystansu vs none", "improvement_vs_none_percent", "#16a34a", "%", None, None),
    ("Czas wykonania", "mean_time_seconds", "#dc2626", "s", 1.75, 1.90),
    ("Czas migracji", "migration_seconds_mean", "#7c3aed", "s", None, None),
    ("Narzut migracji [stosunek]", "migration_overhead_ratio_mean", "#ea580c", "", None, None),
    ("Różnorodność krawędzi [0-1]", "edge_diversity_mean", "#0891b2", "", 0.0, 1.0),
]


def load_results(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Load migration evaluator output and order rows by strategy."""

    with path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    title = f"Migracja: {document.get('run_group_id', path.stem)}"
    order = {"none": 0, "ring": 1, "global-best": 2}
    results = sorted(document["results"], key=lambda item: order.get(item["migration_strategy"], 99))
    return title, results


def fmt(value: float, suffix: str = "") -> str:
    """Format a compact metric label with an optional suffix."""

    if suffix == "%":
        return f"{value:.2f}%"
    if suffix == "s":
        return f"{value:.2f}s"
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def output_path_for_metric(output_prefix: Path, key: str) -> Path:
    """Build a deterministic PNG output path for one metric chart."""

    return output_prefix.with_name(f"{output_prefix.name}-{key.replace('_', '-')}.png")


def render_metric_chart(
    title: str,
    spec: tuple[str, str, str, str, float | None, float | None],
    results: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Render one migration metric as a standalone PNG chart."""

    panel_title, key, color, suffix, y_min, y_max = spec
    strategies = [str(item["migration_strategy"]) for item in results]
    values = [float(item[key]) for item in results]

    fig, ax = plt.subplots(figsize=(6.2, 4.1), dpi=180)
    bars = ax.bar(strategies, values, color=color, alpha=0.88)
    ax.set_title(f"{title} - {panel_title}", fontweight="bold", pad=12)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if y_min is not None or y_max is not None:
        ax.set_ylim(bottom=y_min, top=y_max)
    else:
        ax.margins(y=0.18)

    for bar, value in zip(bars, values, strict=True):
        ax.annotate(
            fmt(value, suffix),
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            color=color,
            fontweight="bold",
            fontsize=9,
        )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def render_combined_chart(title: str, results: list[dict[str, Any]], output_path: Path) -> None:
    """Render all migration metrics into one optional PNG overview."""

    fig, axes = plt.subplots(2, 3, figsize=(14, 8), dpi=160)
    fig.suptitle(title, fontweight="bold", fontsize=16)

    for ax, spec in zip(axes.flat, PANEL_SPECS, strict=True):
        panel_title, key, color, suffix, y_min, y_max = spec
        strategies = [str(item["migration_strategy"]) for item in results]
        values = [float(item[key]) for item in results]
        bars = ax.bar(strategies, values, color=color, alpha=0.88)
        ax.set_title(panel_title, fontweight="bold")
        ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if y_min is not None or y_max is not None:
            ax.set_ylim(bottom=y_min, top=y_max)
        else:
            ax.margins(y=0.18)
        for bar, value in zip(bars, values, strict=True):
            ax.annotate(
                fmt(value, suffix),
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                color=color,
                fontweight="bold",
                fontsize=8,
            )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """CLI entry point for generating migration PNG charts."""

    parser = argparse.ArgumentParser(description="Generate PNG charts from evaluate-quality migration JSON output.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--combined", action="store_true", help="Write one combined PNG instead of separate charts")
    args = parser.parse_args()

    title, results = load_results(args.input_json)
    output_prefix = (args.output or args.input_json).with_suffix("")
    if args.combined:
        output = output_prefix.with_suffix(".png")
        render_combined_chart(title, results, output)
        print(f"Chart written to: {output}")
        return

    for spec in PANEL_SPECS:
        output = output_path_for_metric(output_prefix, spec[1])
        render_metric_chart(title, spec, results, output)
        print(f"Chart written to: {output}")


if __name__ == "__main__":
    main()
