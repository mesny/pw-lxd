#!/usr/bin/env bash
set -euo pipefail

HOSTFILES="./hosts-1-per-node.lxd,./hosts-2-per-node.lxd,./hosts-4-per-node.lxd"
WORKDIR="/opt/pw-lxd"
PYTHON=".venv/bin/python3"
MAIN="main.py"
INPUT="inputs/mazowieckie_114_miasta.csv"
RESULT_DIR="results/experiments/scaling"
LOCAL_OUT_DIR="results/experiments/scaling"
SEEDS="12345,22345,32345"
POPULATION="1200"
GENERATIONS="1000"
MUTATION="0.15"
TWO_OPT_ATTEMPTS="5"
CPU_LIMIT="1"
MEMORY_LIMIT="4GiB"
CODE_VERSION="manual-v1"
FETCH=0
DRY_RUN=0

usage() {
  cat >&2 <<'EOF'
Usage:
  ./mpi_experiment_scaling.sh [options]

Runs the scaling experiment: fixed total population, no migration, varying hostfiles.
Each hostfile defines the exact containers and LXD nodes used by a scenario.

Options:
  --hostfiles csv       MPI hostfiles to test. Default: ./hosts-1-per-node.lxd,./hosts-2-per-node.lxd,./hosts-4-per-node.lxd
  --hostfile path       Run a single MPI hostfile. Shorthand for --hostfiles path
  --wdir path           MPI working directory. Default: /opt/pw-lxd
  --python path         Python executable in --wdir. Default: .venv/bin/python3
  --main path           Application entrypoint in --wdir. Default: main.py
  --input path          TSP CSV input. Default: inputs/mazowieckie_114_miasta.csv
  --result-dir path     Remote result directory inside --wdir. Default: results/experiments/scaling
  --local-out-dir path  Local directory for fetched results. Default: results/experiments/scaling
  --seeds csv           Seeds/repetitions. Default: 12345,22345,32345
  --population n        Total population budget. Default: 1200
  --generations n       Number of generations. Default: 1000
  --fetch               Fetch each result from rank-0 container after a run
  --dry-run             Print generated commands without running MPI
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostfiles) HOSTFILES="${2:?}"; shift 2 ;;
    --hostfile) HOSTFILES="${2:?}"; shift 2 ;;
    --wdir) WORKDIR="${2:?}"; shift 2 ;;
    --python) PYTHON="${2:?}"; shift 2 ;;
    --main) MAIN="${2:?}"; shift 2 ;;
    --input) INPUT="${2:?}"; shift 2 ;;
    --result-dir) RESULT_DIR="${2:?}"; shift 2 ;;
    --local-out-dir) LOCAL_OUT_DIR="${2:?}"; shift 2 ;;
    --np-list)
      echo "Error: --np-list is no longer used; pass explicit --hostfiles instead." >&2
      exit 1
      ;;
    --seeds) SEEDS="${2:?}"; shift 2 ;;
    --population) POPULATION="${2:?}"; shift 2 ;;
    --generations) GENERATIONS="${2:?}"; shift 2 ;;
    --fetch) FETCH=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Error: unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

summary_file="${LOCAL_OUT_DIR%/}/runs.tsv"
if [[ "$DRY_RUN" -ne 1 ]]; then
  mkdir -p "$LOCAL_OUT_DIR"
  if [[ ! -f "$summary_file" ]]; then
    printf 'scenario\thostfile\tnp\tcontainers_per_node\tseed\tmigration\tpopulation_mode\tpopulation\tgenerations\tresult_file\n' > "$summary_file"
  fi
fi

IFS=',' read -r -a hostfile_values <<< "$HOSTFILES"
IFS=',' read -r -a seed_values <<< "$SEEDS"

count_hostfile_entries() {
  awk 'NF && $1 !~ /^#/ {count++} END {print count + 0}' "$1"
}

containers_per_node_from_hostfile() {
  local hostfile="$1"
  local base

  base="$(basename "$hostfile")"
  if [[ "$base" =~ ^hosts-([0-9]+)-per-node[.]lxd$ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
  else
    printf 'unknown\n'
  fi
}

run_one() {
  local hostfile="$1"
  local seed="$2"
  local np
  local containers_per_node
  local scenario
  local dry_args=()

  if [[ ! -f "$hostfile" ]]; then
    echo "Error: hostfile does not exist: $hostfile" >&2
    exit 1
  fi

  np="$(count_hostfile_entries "$hostfile")"
  if [[ "$np" -lt 1 ]]; then
    echo "Error: hostfile has no usable host entries: $hostfile" >&2
    exit 1
  fi

  containers_per_node="$(containers_per_node_from_hostfile "$hostfile")"
  scenario="scaling-${containers_per_node}pernode-np${np}-seed${seed}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    dry_args+=(--dry-run)
  fi

  result_file="$(
    ./mpi_run_ga.sh \
      --hostfile "$hostfile" \
      --wdir "$WORKDIR" \
      --python "$PYTHON" \
      --main "$MAIN" \
      --result-dir "$RESULT_DIR" \
      --label scaling \
      "${dry_args[@]}" \
      -- \
      --input "$INPUT" \
      --seed "$seed" \
      --population "$POPULATION" \
      --population-mode total \
      --generations "$GENERATIONS" \
      --mutation "$MUTATION" \
      --migration-strategy none \
      --two-opt-attempts "$TWO_OPT_ATTEMPTS" \
      --metadata-run-id "$scenario" \
      --metadata-scenario-name "scaling-${containers_per_node}-per-node-np-${np}" \
      --metadata-containers-per-node "$containers_per_node" \
      --metadata-hostfile "$hostfile" \
      --metadata-cpu-limit "$CPU_LIMIT" \
      --metadata-memory-limit "$MEMORY_LIMIT" \
      --metadata-code-version "$CODE_VERSION"
  )"

  if [[ "$DRY_RUN" -ne 1 ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$scenario" "$hostfile" "$np" "$containers_per_node" "$seed" "none" "total" "$POPULATION" "$GENERATIONS" "$result_file" >> "$summary_file"
  fi

  if [[ "$FETCH" -eq 1 && "$DRY_RUN" -ne 1 ]]; then
    ./mpi_fetch_result.sh \
      --hostfile "$hostfile" \
      --workdir "$WORKDIR" \
      --out-dir "$LOCAL_OUT_DIR" \
      --result "${RESULT_DIR%/}/$result_file" \
      --force
  fi
}

for hostfile in "${hostfile_values[@]}"; do
  for seed in "${seed_values[@]}"; do
    echo "Running scaling experiment: hostfile=$hostfile seed=$seed" >&2
    run_one "$hostfile" "$seed"
  done
done

if [[ "$DRY_RUN" -ne 1 ]]; then
  echo "Summary: $summary_file"
fi
