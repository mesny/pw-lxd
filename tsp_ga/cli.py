from __future__ import annotations

import argparse

from tsp_ga.config import build_config, validate_config
from tsp_ga.runner import run_ga


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MPI island-model genetic algorithm for TSP."
    )

    problem_group = parser.add_argument_group("TSP problem")
    problem_group.add_argument("--input", type=str, default=None, help="CSV file with columns: id,x,y")
    problem_group.add_argument("--cities", type=int, default=50, help="Number of generated cities when --input is not used")
    problem_group.add_argument("--seed", type=int, default=12345, help="Base random seed")

    ga_group = parser.add_argument_group("Genetic algorithm")
    ga_group.add_argument("--population", type=int, default=100, help="Population size. Meaning depends on --population-mode")
    ga_group.add_argument("--population-mode", choices=["per-rank", "total"], default="per-rank", help="Interpret --population as per-rank population or total population budget")
    ga_group.add_argument("--generations", type=int, default=500, help="Number of GA generations")
    ga_group.add_argument("--mutation", type=float, default=0.15, help="Swap mutation probability")
    ga_group.add_argument("--elite", type=int, default=2, help="Number of elite individuals copied to next generation")
    ga_group.add_argument("--tournament", type=int, default=4, help="Tournament selection size")
    ga_group.add_argument("--two-opt-attempts", type=int, default=3, help="Random 2-opt improvement attempts per child")

    migration_group = parser.add_argument_group("Migration")
    migration_group.add_argument("--migration-strategy", choices=["none", "ring", "global-best"], default="ring", help="Migration strategy between MPI islands")
    migration_group.add_argument("--migration-interval", type=int, default=25, help="Migrate every N generations")
    migration_group.add_argument("--immigrants", type=int, default=2, help="Number of best individuals migrated")

    reporting_group = parser.add_argument_group("Reporting")
    reporting_group.add_argument("--output", type=str, required=True, help="Required JSON output path for experiment results")
    reporting_group.add_argument("--report-interval", type=int, default=50, help="Store local history every N generations")

    metadata_group = parser.add_argument_group("Metadata")
    metadata_group.add_argument("--metadata-run-id", type=str, default="manual-run", help="Metadata only: experiment run identifier")
    metadata_group.add_argument("--metadata-scenario-name", type=str, default="default", help="Metadata only: human-readable experiment scenario name")
    metadata_group.add_argument("--metadata-containers-per-node", type=int, default=None, help="Metadata only: number of LXD containers per physical cluster node in this scenario")
    metadata_group.add_argument("--metadata-hostfile", type=str, default=None, help="Metadata only: MPI hostfile used for this run")
    metadata_group.add_argument("--metadata-cpu-limit", type=str, default=None, help="Metadata only: LXD CPU limit used per container")
    metadata_group.add_argument("--metadata-code-version", type=str, default=None, help="Metadata only: code version, git commit, tag or manual version label")

    debug_group = parser.add_argument_group("Debug")
    debug_group.add_argument("--debug-routes", action="store_true", help="Validate TSP route permutations during evolution")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = build_config(args)
    validate_config(config)

    run_ga(config)
