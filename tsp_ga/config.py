from __future__ import annotations

import argparse
from dataclasses import replace

from tsp_ga.models import AppConfig, ExperimentConfig, GAConfig, PopulationPlan


SUPPORTED_POPULATION_MODES = {"per-rank", "total"}
SUPPORTED_MIGRATION_STRATEGIES = {"none", "ring", "global-best"}


def build_config(args: argparse.Namespace) -> AppConfig:
    immigrants = 0 if args.migration_strategy == "none" else args.immigrants

    return AppConfig(
        ga=GAConfig(
            population=args.population,
            generations=args.generations,
            mutation=args.mutation,
            elite=args.elite,
            tournament=args.tournament,
            migration_interval=args.migration_interval,
            immigrants=immigrants,
            two_opt_attempts=args.two_opt_attempts,
            report_interval=args.report_interval,
            debug_routes=args.debug_routes,
            migration_strategy=args.migration_strategy,
            population_mode=args.population_mode,
        ),
        experiment=ExperimentConfig(
            input=args.input,
            cities=args.cities,
            seed=args.seed,
            output=args.output,
            run_id=args.run_id,
            scenario_name=args.scenario_name,
            metadata_containers_per_node=args.metadata_containers_per_node,
            hostfile=args.hostfile,
            cpu_limit=args.cpu_limit,
            code_version=args.code_version,
        ),
    )


def build_population_plan(config: GAConfig, world_size: int) -> PopulationPlan:
    if world_size < 1:
        raise ValueError("world_size must be >= 1")

    if config.population_mode == "per-rank":
        return PopulationPlan(
            requested_population=config.population,
            population_mode=config.population_mode,
            per_rank_populations=[config.population] * world_size,
        )

    base_population = config.population // world_size
    remainder = config.population % world_size

    per_rank_populations = [
        base_population + (1 if rank < remainder else 0)
        for rank in range(world_size)
    ]

    min_population = min(per_rank_populations)
    if min_population < 4:
        raise ValueError(
            "--population is too small for --population-mode total and current MPI size: "
            f"population={config.population}, mpi_processes={world_size}, "
            f"min_population_per_rank={min_population}. Increase --population or reduce -n."
        )

    return PopulationPlan(
        requested_population=config.population,
        population_mode=config.population_mode,
        per_rank_populations=per_rank_populations,
    )


def resolve_ga_config_for_rank(config: GAConfig, population_plan: PopulationPlan, rank: int) -> GAConfig:
    return replace(config, population=population_plan.per_rank_populations[rank])


def validate_experiment_config(config: ExperimentConfig) -> None:
    if config.cities < 3:
        raise ValueError("--cities must be >= 3")
    if not config.run_id.strip():
        raise ValueError("--run-id must not be empty")
    if not config.scenario_name.strip():
        raise ValueError("--scenario-name must not be empty")
    if config.metadata_containers_per_node is not None and config.metadata_containers_per_node < 1:
        raise ValueError("--metadata-containers-per-node must be >= 1 when provided")
    if config.cpu_limit is not None and not config.cpu_limit.strip():
        raise ValueError("--cpu-limit must not be empty when provided")
    if config.hostfile is not None and not config.hostfile.strip():
        raise ValueError("--hostfile must not be empty when provided")
    if config.code_version is not None and not config.code_version.strip():
        raise ValueError("--code-version must not be empty when provided")
    if not config.output.strip():
        raise ValueError("--output is required and must not be empty")


def validate_ga_config(config: GAConfig) -> None:
    if config.population < 4:
        raise ValueError("--population must be >= 4")
    if config.generations < 1:
        raise ValueError("--generations must be >= 1")
    if not 0.0 <= config.mutation <= 1.0:
        raise ValueError("--mutation must be between 0.0 and 1.0")
    if config.elite < 1 or config.elite >= config.population:
        raise ValueError("--elite must be >= 1 and < population")
    if config.tournament < 2 or config.tournament > config.population:
        raise ValueError("--tournament must be between 2 and population")
    if config.migration_interval < 1:
        raise ValueError("--migration-interval must be >= 1")
    if config.immigrants < 0 or config.immigrants >= config.population:
        raise ValueError("--immigrants must be >= 0 and < population")
    if config.two_opt_attempts < 0:
        raise ValueError("--two-opt-attempts must be >= 0")
    if config.report_interval < 1:
        raise ValueError("--report-interval must be >= 1")
    if config.population_mode not in SUPPORTED_POPULATION_MODES:
        raise ValueError("--population-mode must be either 'per-rank' or 'total'")
    if config.migration_strategy not in SUPPORTED_MIGRATION_STRATEGIES:
        raise ValueError("--migration-strategy must be one of: 'none', 'ring', 'global-best'")


def validate_config(config: AppConfig) -> None:
    validate_experiment_config(config.experiment)
    validate_ga_config(config.ga)
