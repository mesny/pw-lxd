from __future__ import annotations

import itertools
import json
import statistics
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from tsp_ga.models import AppConfig, GAConfig, IslandResult, MpiContext, PopulationPlan, Problem, RuntimeMetrics, Route


def route_edges(route: Route) -> set[tuple[int, int]]:
    """Return undirected edges used by a closed TSP route."""

    edges: set[tuple[int, int]] = set()
    n = len(route)

    for i in range(n):
        a = route[i]
        b = route[(i + 1) % n]
        edges.add((a, b) if a < b else (b, a))

    return edges


def edge_distance(route_a: Route, route_b: Route) -> float:
    """Compute pairwise edge diversity between two routes."""

    edges_a = route_edges(route_a)
    edges_b = route_edges(route_b)

    if not edges_a and not edges_b:
        return 0.0

    common_edges = len(edges_a & edges_b)
    total_edges = max(len(edges_a), len(edges_b))

    # This treats reversed routes as equivalent because route_edges stores undirected edges.
    return 1.0 - (common_edges / total_edges)


def build_diversity_document(all_results: list[IslandResult]) -> dict:
    """Aggregate route diversity metrics across island results."""

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


def route_fingerprint(route: Route) -> str:
    """Create a short stable hash for a route without storing the full route."""

    route_json = json.dumps(route, separators=(",", ":"))
    return sha256(route_json.encode("utf-8")).hexdigest()[:16]


def build_best_route_info(best: IslandResult) -> dict:
    """Build compact metadata for the globally best route."""

    return {
        "rank": best.rank,
        "distance": best.best_distance,
        "found_generation": best.best_generation,
        "city_count": len(best.best_route),
        "edge_count": len(best.best_route),
        "route_fingerprint": route_fingerprint(best.best_route),
        "full_route_saved": False,
    }


def build_progress_history(history: list[tuple[int, float]]) -> list[dict]:
    """Convert local progress tuples into JSON-friendly records."""

    return [
        {
            "generation": generation,
            "best_distance_so_far": best_distance,
        }
        for generation, best_distance in history
    ]


def safe_divide(numerator: float, denominator: float) -> float | None:
    """Divide two numbers and return None for a zero denominator."""

    if denominator == 0:
        return None
    return numerator / denominator


def build_result_document(
    original_config: AppConfig,
    effective_ga_config: GAConfig,
    population_plan: PopulationPlan,
    problem: Problem,
    mpi: MpiContext,
    all_results: list[IslandResult],
    runtime_metrics: RuntimeMetrics,
) -> dict:
    """Assemble the full JSON result document written by rank 0."""

    best = min(all_results, key=lambda r: r.best_distance)
    distances = [r.best_distance for r in all_results]
    migration_times = [result.migration_time_seconds for result in all_results]
    migration_counts = [result.migration_count for result in all_results]
    evolution_times = [result.evolution_time_seconds for result in all_results]

    total_migration_time = sum(migration_times)
    total_migration_count = sum(migration_counts)
    total_time_max_rank = runtime_metrics.total_seconds_max_rank
    sorted_results = sorted(all_results, key=lambda r: r.rank)
    diversity = build_diversity_document(all_results)
    reference_islands = 3
    t_p = total_time_max_rank
    t_ref = t_p if mpi.size == reference_islands else None
    # Per-run reports only know their own time; evaluators fill T_ref for non-reference sizes.
    relative_speedup = safe_divide(t_ref, t_p) if t_ref is not None else None
    relative_efficiency = (
        safe_divide(relative_speedup, mpi.size / reference_islands)
        if relative_speedup is not None
        else None
    )
    migration_overhead_ratio = safe_divide(total_migration_time, t_p)
    improvement_vs_none_percent = 0.0 if effective_ga_config.migration_strategy == "none" else None

    return {
        "run": {
            "run_id": original_config.experiment.metadata_run_id,
            "run_group_id": original_config.experiment.metadata_run_group_id,
            "scenario_name": original_config.experiment.metadata_scenario_name,
            "hostfile": original_config.experiment.metadata_hostfile,
            "code_version": original_config.experiment.metadata_code_version,
        },
        "params": {
            "input": original_config.experiment.input,
            "cities": len(problem.cities),
            "seed": original_config.experiment.seed,
            "islands": mpi.size,
            "generations": effective_ga_config.generations,
            "population_mode": population_plan.population_mode,
            "population_total": population_plan.effective_total_population,
            "population_per_island": population_plan.per_rank_populations,
            "mutation": effective_ga_config.mutation,
            "elite": effective_ga_config.elite,
            "tournament": effective_ga_config.tournament,
            "two_opt_attempts": effective_ga_config.two_opt_attempts,
            "migration_strategy": effective_ga_config.migration_strategy,
            "migration_interval": effective_ga_config.migration_interval,
            "immigrants": effective_ga_config.immigrants,
            "cpu_limit": original_config.experiment.metadata_cpu_limit,
            "memory_limit": original_config.experiment.metadata_memory_limit,
        },
        "metrics": {
            "quality_measures": {
                "formulas": {
                    "best_route_distance": "min(best_distance_rank_i)",
                    "mean_island_distance": "avg(best_distance_rank_i)",
                    "distance_spread": "max(best_distance_rank_i) - min(best_distance_rank_i)",
                    "improvement_vs_none_percent": "100 * (D_none - D_strategy) / D_none",
                    "edge_distance": "1 - common_edges(route_a, route_b) / edge_count",
                },
                "best_distance": best.best_distance,
                "best_rank": best.rank,
                "best_generation": best.best_generation,
                "mean_island_distance": statistics.mean(distances),
                "min_island_distance": min(distances),
                "max_island_distance": max(distances),
                "distance_spread": max(distances) - min(distances),
                "improvement_vs_none_percent": improvement_vs_none_percent,
                "improvement_vs_none_note": (
                    "This run uses migration-strategy none, so it is the baseline."
                    if effective_ga_config.migration_strategy == "none"
                    else "Requires a matching baseline run with migration-strategy none."
                ),
                "diversity": diversity,
                "best_route": build_best_route_info(best),
            },
            "performance_measures": {
                "formulas": {
                    "total_time": "T(p)",
                    "relative_speedup": "S_ref(p) = T_ref / T(p)",
                    "relative_efficiency": "E_ref(p) = S_ref(p) / (p / 3)",
                    "migration_overhead_ratio": "M = migration_seconds_total / T(p)",
                },
                "p_ranks": mpi.size,
                "reference_ranks": reference_islands,
                "total_time_seconds_T_p": t_p,
                "reference_time_seconds_T_ref": t_ref,
                "relative_speedup_S_ref": relative_speedup,
                "relative_efficiency_E_ref": relative_efficiency,
                "migration_overhead_ratio": migration_overhead_ratio,
                "elapsed_seconds": runtime_metrics.total_seconds,
                "prepare_problem_seconds": runtime_metrics.prepare_problem_seconds,
                "run_island_seconds": runtime_metrics.run_island_seconds,
                "gather_seconds": runtime_metrics.gather_seconds,
                "report_seconds": runtime_metrics.report_seconds,
                "evolution_max_rank_seconds": max(evolution_times) if evolution_times else 0.0,
                "migration_total_seconds": total_migration_time,
                "migration_count_total": total_migration_count,
                "migration_avg_seconds": safe_divide(total_migration_time, total_migration_count) or 0.0,
                "migration_max_rank_seconds": max(migration_times) if migration_times else 0.0,
                "scaling_note": (
                    "This run is the reference for S_ref and E_ref."
                    if mpi.size == reference_islands
                    else "S_ref and E_ref require T_ref from a matching hosts-1-per-node run."
                ),
            },
        },
        "islands": [
            {
                "rank": result.rank,
                "best_distance": result.best_distance,
                "best_generation": result.best_generation,
                "evolution_time_seconds": result.evolution_time_seconds,
                "migration_time_seconds": result.migration_time_seconds,
                "migration_count": result.migration_count,
                "progress": build_progress_history(result.history),
            }
            for result in sorted_results
        ],
        "notes": {
            "full_routes_saved": False,
            "progress": "Best distance so far at report checkpoints.",
        },
    }


def write_result_document(output_path: str, result_document: dict) -> None:
    """Write a result document as formatted UTF-8 JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(result_document, indent=2, ensure_ascii=False)
    path.write_text(json_text, encoding="utf-8")


def print_summary(result_document: dict, output_path: str) -> None:
    """Print a compact one-line summary for shell scripts."""

    run = result_document["run"]
    params = result_document["params"]
    quality = result_document["metrics"]["quality_measures"]
    performance = result_document["metrics"]["performance_measures"]
    diversity = quality["diversity"]

    print(
        "DONE "
        f"run_id={run['run_id']} "
        f"mode=mpi "
        f"ranks={params['islands']} "
        f"cities={params['cities']} "
        f"population_total={params['population_total']} "
        f"best_distance={quality['best_distance']:.6f} "
        f"edge_diversity_mean={diversity['mean_pairwise_edge_distance']:.6f} "
        f"elapsed_seconds={performance['elapsed_seconds']:.6f} "
        f"migration_seconds={performance['migration_total_seconds']:.6f} "
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
    """Build, persist and print the final run report."""

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
    write_result_document(output_path, result_document)
    print_summary(result_document, output_path)
    runtime_metrics.report_seconds = timer() - report_start
    result_document["metrics"]["performance_measures"]["report_seconds"] = runtime_metrics.report_seconds
    write_result_document(output_path, result_document)

    return result_document
