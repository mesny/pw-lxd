from __future__ import annotations

import itertools
import json
import statistics
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from tsp_ga.models import AppConfig, GAConfig, IslandResult, MpiContext, PopulationPlan, Problem, RuntimeMetrics, Route


BEST_ROUTE_VALUES_PER_LINE = 10


def route_edges(route: Route) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    n = len(route)

    for i in range(n):
        a = route[i]
        b = route[(i + 1) % n]
        edges.add((a, b) if a < b else (b, a))

    return edges


def edge_distance(route_a: Route, route_b: Route) -> float:
    edges_a = route_edges(route_a)
    edges_b = route_edges(route_b)

    if not edges_a and not edges_b:
        return 0.0

    common_edges = len(edges_a & edges_b)
    total_edges = max(len(edges_a), len(edges_b))

    return 1.0 - (common_edges / total_edges)


def build_diversity_document(all_results: list[IslandResult]) -> dict:
    sorted_results = sorted(all_results, key=lambda r: r.rank)
    best_routes = [result.best_route for result in sorted_results]
    canonical_routes = {tuple(route) for route in best_routes}

    pairwise_distances = [
        edge_distance(route_a, route_b)
        for route_a, route_b in itertools.combinations(best_routes, 2)
    ]

    return {
        "unique_best_routes": len(canonical_routes),
        "pairwise_comparisons": len(pairwise_distances),
        "mean_pairwise_edge_distance": statistics.mean(pairwise_distances) if pairwise_distances else 0.0,
        "min_pairwise_edge_distance": min(pairwise_distances) if pairwise_distances else 0.0,
        "max_pairwise_edge_distance": max(pairwise_distances) if pairwise_distances else 0.0,
    }


def build_result_document(
    original_config: AppConfig,
    effective_ga_config: GAConfig,
    population_plan: PopulationPlan,
    problem: Problem,
    mpi: MpiContext,
    all_results: list[IslandResult],
    runtime_metrics: RuntimeMetrics,
) -> dict:
    best = min(all_results, key=lambda r: r.best_distance)
    distances = [r.best_distance for r in all_results]
    migration_times = [result.migration_time_seconds for result in all_results]
    migration_counts = [result.migration_count for result in all_results]
    evolution_times = [result.evolution_time_seconds for result in all_results]

    total_migration_time = sum(migration_times)
    total_migration_count = sum(migration_counts)

    return {
        "metadata": {
            "metadata_run_id": original_config.experiment.metadata_run_id,
            "metadata_scenario_name": original_config.experiment.metadata_scenario_name,
            "metadata_containers_per_node": original_config.experiment.metadata_containers_per_node,
            "metadata_hostfile": original_config.experiment.metadata_hostfile,
            "metadata_cpu_limit": original_config.experiment.metadata_cpu_limit,
            "metadata_code_version": original_config.experiment.metadata_code_version,
            "mpi_processes": mpi.size,
            "elapsed_seconds": runtime_metrics.total_seconds,
        },
        "problem": {
            "input": original_config.experiment.input,
            "cities": len(problem.cities),
            "seed": original_config.experiment.seed,
        },
        "ga_config_requested": asdict(original_config.ga),
        "ga_config_effective_rank0": asdict(effective_ga_config),
        "work_budget": {
            "population_mode": population_plan.population_mode,
            "requested_population": population_plan.requested_population,
            "per_rank_populations": population_plan.per_rank_populations,
            "effective_population_rank0": effective_ga_config.population,
            "effective_total_population": population_plan.effective_total_population,
            "generations": effective_ga_config.generations,
            "migration_strategy": effective_ga_config.migration_strategy,
        },
        "timing": {
            "prepare_problem_seconds": runtime_metrics.prepare_problem_seconds,
            "run_island_seconds": runtime_metrics.run_island_seconds,
            "gather_seconds": runtime_metrics.gather_seconds,
            "report_seconds": runtime_metrics.report_seconds,
            "total_seconds": runtime_metrics.total_seconds,
            "migration_time_total_all_ranks": total_migration_time,
            "migration_count_total_all_ranks": total_migration_count,
            "migration_time_avg_per_migration": (
                total_migration_time / total_migration_count if total_migration_count > 0 else 0.0
            ),
            "migration_time_max_rank": max(migration_times) if migration_times else 0.0,
            "evolution_time_max_rank": max(evolution_times) if evolution_times else 0.0,
        },
        "summary": {
            "best_rank": best.rank,
            "best_distance": best.best_distance,
            "best_route": best.best_route,
            "min_distance": min(distances),
            "mean_distance": statistics.mean(distances),
            "max_distance": max(distances),
        },
        "diversity": build_diversity_document(all_results),
        "islands": [asdict(result) for result in sorted(all_results, key=lambda r: r.rank)],
    }


def compact_best_route_arrays(json_text: str, values_per_line: int = BEST_ROUTE_VALUES_PER_LINE) -> str:
    lines = json_text.splitlines()
    output_lines: list[str] = []
    line_index = 0

    while line_index < len(lines):
        line = lines[line_index]

        if line.strip() != '"best_route": [':
            output_lines.append(line)
            line_index += 1
            continue

        output_lines.append(line)
        line_index += 1

        value_lines: list[str] = []
        while line_index < len(lines):
            candidate = lines[line_index]
            if candidate.strip() in {"]", "],"}:
                break
            value_lines.append(candidate)
            line_index += 1

        values = [value_line.strip().rstrip(",") for value_line in value_lines]
        if values:
            value_indent = value_lines[0][: len(value_lines[0]) - len(value_lines[0].lstrip())]
            for chunk_start in range(0, len(values), values_per_line):
                chunk = values[chunk_start:chunk_start + values_per_line]
                suffix = "," if chunk_start + values_per_line < len(values) else ""
                output_lines.append(f"{value_indent}{', '.join(chunk)}{suffix}")

        if line_index < len(lines):
            output_lines.append(lines[line_index])
            line_index += 1

    return "\n".join(output_lines)


def write_result_document(output_path: str, result_document: dict) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(result_document, indent=2, ensure_ascii=False)
    path.write_text(
        compact_best_route_arrays(json_text),
        encoding="utf-8",
    )


def print_summary(result_document: dict, output_path: str) -> None:
    metadata = result_document["metadata"]
    problem = result_document["problem"]
    work_budget = result_document["work_budget"]
    timing = result_document["timing"]
    summary = result_document["summary"]
    diversity = result_document["diversity"]

    print(
        "DONE "
        f"run_id={metadata['metadata_run_id']} "
        f"mode=mpi "
        f"ranks={metadata['mpi_processes']} "
        f"cities={problem['cities']} "
        f"population_total={work_budget['effective_total_population']} "
        f"best_distance={summary['best_distance']:.6f} "
        f"edge_diversity_mean={diversity['mean_pairwise_edge_distance']:.6f} "
        f"elapsed_seconds={metadata['elapsed_seconds']:.6f} "
        f"migration_seconds={timing['migration_time_total_all_ranks']:.6f} "
        f"output={output_path}"
    )


def finalize_run(
    original_config: AppConfig,
    effective_ga_config: GAConfig,
    population_plan: PopulationPlan,
    problem: Problem,
    mpi: MpiContext,
    all_results: list[IslandResult],
    runtime_metrics: RuntimeMetrics,
    timer: Callable[[], float] | None = None,
) -> dict:
    result_document = build_result_document(
        original_config=original_config,
        effective_ga_config=effective_ga_config,
        population_plan=population_plan,
        problem=problem,
        mpi=mpi,
        all_results=all_results,
        runtime_metrics=runtime_metrics,
    )

    output_path = original_config.experiment.output

    if timer is None:
        write_result_document(output_path, result_document)
        print_summary(result_document, output_path)
        return result_document

    report_start = timer()
    runtime_metrics.report_seconds = timer() - report_start
    result_document["timing"]["report_seconds"] = runtime_metrics.report_seconds
    write_result_document(output_path, result_document)
    print_summary(result_document, output_path)

    return result_document
