from __future__ import annotations

import random
import time

from mpi4py import MPI

from tsp_ga.config import build_population_plan, resolve_ga_config_for_rank, validate_ga_config
from tsp_ga.evolution import best_individual, evolve_one_generation
from tsp_ga.migration import migrate_population
from tsp_ga.models import AppConfig, GAConfig, History, IslandResult, MpiContext, Problem, RuntimeMetrics
from tsp_ga.mpi_runtime import collect_results, get_mpi_context
from tsp_ga.operators import initial_population, validate_route
from tsp_ga.problem import prepare_problem
from tsp_ga.reporting import finalize_run
from tsp_ga.timing import StageTimer


def build_rank_seed(base_seed: int, rank: int) -> int:
    return base_seed + rank * 100_003


def monotonic_seconds(mpi: MpiContext) -> float:
    if mpi.comm is None:
        return time.perf_counter()
    return MPI.Wtime()


def run_island(
    ga_config: GAConfig,
    rng_seed: int,
    problem: Problem,
    mpi: MpiContext,
    timer: StageTimer,
) -> IslandResult:
    rng = random.Random(rng_seed)

    pop = initial_population(ga_config.population, len(problem.cities), problem.distances, rng)
    best_seen = best_individual(pop)
    history: History = []
    migration_count = 0
    migration_time_seconds = 0.0
    evolution_time_seconds = 0.0

    if ga_config.debug_routes:
        for individual in pop:
            validate_route(individual.route, len(problem.cities))

    for generation in range(1, ga_config.generations + 1):
        pop_obj, elapsed = timer.measure(
            lambda: evolve_one_generation(
                pop=pop,
                dist=problem.distances,
                config=ga_config,
                rng=rng,
            )
        )
        pop = pop_obj
        evolution_time_seconds += elapsed

        if generation % ga_config.migration_interval == 0:
            pop_obj, migration_elapsed = timer.measure(
                lambda: migrate_population(
                    strategy=ga_config.migration_strategy,
                    pop=pop,
                    comm=mpi.comm,
                    rank=mpi.rank,
                    size=mpi.size,
                    immigrants=ga_config.immigrants,
                )
            )
            pop = pop_obj

            if ga_config.migration_strategy != "none" and mpi.size > 1 and ga_config.immigrants > 0:
                migration_count += 1
                migration_time_seconds += migration_elapsed

            if ga_config.debug_routes:
                for individual in pop:
                    validate_route(individual.route, len(problem.cities))

        current_best = best_individual(pop)
        if current_best.distance < best_seen.distance:
            best_seen = current_best

        if generation % ga_config.report_interval == 0 or generation == ga_config.generations:
            history.append((generation, best_seen.distance))

    return IslandResult(
        rank=mpi.rank,
        best_distance=best_seen.distance,
        best_route=best_seen.route,
        history=history,
        migration_count=migration_count,
        migration_time_seconds=migration_time_seconds,
        evolution_time_seconds=evolution_time_seconds,
    )


def run_ga(config: AppConfig) -> dict | None:
    mpi = get_mpi_context()
    timer = StageTimer(lambda: monotonic_seconds(mpi))
    population_plan = build_population_plan(config.ga, mpi.size)
    effective_ga_config = resolve_ga_config_for_rank(config.ga, population_plan, mpi.rank)
    validate_ga_config(effective_ga_config)
    metrics = RuntimeMetrics()
    total_start = monotonic_seconds(mpi)

    problem_obj, metrics.prepare_problem_seconds = timer.measure(lambda: prepare_problem(config.experiment, mpi))
    problem = problem_obj

    local_result_obj, metrics.run_island_seconds = timer.measure(
        lambda: run_island(
            ga_config=effective_ga_config,
            rng_seed=build_rank_seed(config.experiment.seed, mpi.rank),
            problem=problem,
            mpi=mpi,
            timer=timer,
        )
    )
    local_result = local_result_obj

    all_results_obj, metrics.gather_seconds = timer.measure(lambda: collect_results(local_result, mpi))
    all_results = all_results_obj
    metrics.total_seconds = monotonic_seconds(mpi) - total_start
    if mpi.comm is None:
        metrics.total_seconds_max_rank = metrics.total_seconds
    else:
        metrics.total_seconds_max_rank = mpi.comm.allreduce(metrics.total_seconds, op=MPI.MAX)

    if mpi.rank != 0:
        return None

    if all_results is None:
        raise RuntimeError("Rank 0 did not receive gathered MPI results.")

    return finalize_run(
        config,
        effective_ga_config,
        population_plan,
        problem,
        mpi,
        all_results,
        metrics,
        timer=lambda: monotonic_seconds(mpi),
    )
