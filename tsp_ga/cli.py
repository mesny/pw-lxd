from __future__ import annotations

import argparse

from tsp_ga.config import build_config, validate_config
from tsp_ga.runner import run_ga


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MPI island-model genetic algorithm for TSP."
    )

    parser.add_argument("--input", type=str, default=None, help="CSV file with columns: id,x,y")
    parser.add_argument("--cities", type=int, default=50, help="Number of generated cities when --input is not used")
    parser.add_argument("--population", type=int, default=100, help="Population size. Meaning depends on --population-mode")
    parser.add_argument("--population-mode", choices=["per-rank", "total"], default="per-rank", help="Interpret --population as per-rank population or total population budget")
    parser.add_argument("--generations", type=int, default=500, help="Number of GA generations")
    parser.add_argument("--mutation", type=float, default=0.15, help="Swap mutation probability")
    parser.add_argument("--elite", type=int, default=2, help="Number of elite individuals copied to next generation")
    parser.add_argument("--tournament", type=int, default=4, help="Tournament selection size")
    parser.add_argument("--migration-strategy", choices=["none", "ring", "global-best"], default="ring", help="Migration strategy between MPI islands")
    parser.add_argument("--migration-interval", type=int, default=25, help="Migrate every N generations")
    parser.add_argument("--immigrants", type=int, default=2, help="Number of best individuals migrated")
    parser.add_argument("--two-opt-attempts", type=int, default=3, help="Random 2-opt improvement attempts per child")
    parser.add_argument("--report-interval", type=int, default=50, help="Store local history every N generations")
    parser.add_argument("--seed", type=int, default=12345, help="Base random seed")
    parser.add_argument("--output", type=str, required=True, help="Required JSON output path for experiment results")
    parser.add_argument("--run-id", type=str, default="manual-run", help="Experiment run identifier")
    parser.add_argument("--scenario-name", type=str, default="default", help="Human-readable experiment scenario name")
    parser.add_argument("--metadata-containers-per-node", type=int, default=None, help="Metadata only: number of LXD containers per physical cluster node in this scenario")
    parser.add_argument("--containers-per-node", type=int, dest="metadata_containers_per_node", help=argparse.SUPPRESS)
    parser.add_argument("--hostfile", type=str, default=None, help="MPI hostfile used in this run, stored as metadata only")
    parser.add_argument("--cpu-limit", type=str, default=None, help="LXD CPU limit used per container, stored as metadata only")
    parser.add_argument("--code-version", type=str, default=None, help="Code version, git commit, tag or manual version label, stored as metadata only")
    parser.add_argument("--debug-routes", action="store_true", help="Validate TSP route permutations during evolution")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = build_config(args)
    validate_config(config)

    run_ga(config)
