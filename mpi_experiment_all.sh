#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  ./mpi_experiment_all.sh [common options]

Runs the recommended experiment suite:
  1. scaling experiment
  2. migration strategy experiment

Passes common options through to both scripts. For the optional population-mode
experiment, run ./mpi_experiment_population_modes.sh separately.

Common options include:
  --hostfile path
  --wdir path
  --python path
  --main path
  --input path
  --seeds csv
  --population n
  --generations n
  --fetch
  --dry-run
  -h, --help
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

echo "Running experiment suite: scaling" >&2
./mpi_experiment_scaling.sh "$@"

echo "Running experiment suite: migration" >&2
./mpi_experiment_migration.sh "$@"

echo "Done. Optional population-mode experiment:"
echo "  ./mpi_experiment_population_modes.sh $*"
