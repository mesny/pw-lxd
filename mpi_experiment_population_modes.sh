#!/usr/bin/env bash
set -euo pipefail

HOSTFILE="./hosts.lxd"
NP="12"
WORKDIR="/opt/pw-lxd"
PYTHON=".venv/bin/python3"
MAIN="main.py"
INPUT="inputs/mazowieckie_114_miasta.csv"
RESULT_DIR="results/experiments/population-modes"
LOCAL_OUT_DIR="results/experiments/population-modes"
SEEDS="12345,22345,32345"
GENERATIONS="1000"
MUTATION="0.15"
TWO_OPT_ATTEMPTS="5"
CPU_LIMIT="1"
MEMORY_LIMIT="4GiB"
CONTAINERS_PER_NODE="4"
CODE_VERSION="manual-v1"
FETCH=0
DRY_RUN=0

usage() {
  cat >&2 <<'EOF'
Usage:
  ./mpi_experiment_population_modes.sh [options]

Runs the optional population-mode experiment:
  total 1200, per-rank 100, per-rank 1200.

Options:
  --hostfile path       MPI hostfile. Default: ./hosts.lxd
  --np n                MPI ranks. Default: 12
  --wdir path           MPI working directory. Default: /opt/pw-lxd
  --python path         Python executable in --wdir. Default: .venv/bin/python3
  --main path           Application entrypoint in --wdir. Default: main.py
  --input path          TSP CSV input. Default: inputs/mazowieckie_114_miasta.csv
  --result-dir path     Remote result directory inside --wdir. Default: results/experiments/population-modes
  --local-out-dir path  Local directory for fetched results. Default: results/experiments/population-modes
  --seeds csv           Seeds/repetitions. Default: 12345,22345,32345
  --generations n       Number of generations. Default: 1000
  --fetch               Fetch each result from rank-0 container after a run
  --dry-run             Print generated commands without running MPI
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostfile) HOSTFILE="${2:?}"; shift 2 ;;
    --np) NP="${2:?}"; shift 2 ;;
    --wdir) WORKDIR="${2:?}"; shift 2 ;;
    --python) PYTHON="${2:?}"; shift 2 ;;
    --main) MAIN="${2:?}"; shift 2 ;;
    --input) INPUT="${2:?}"; shift 2 ;;
    --result-dir) RESULT_DIR="${2:?}"; shift 2 ;;
    --local-out-dir) LOCAL_OUT_DIR="${2:?}"; shift 2 ;;
    --seeds) SEEDS="${2:?}"; shift 2 ;;
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
    printf 'scenario\tnp\tseed\tmigration\tpopulation_mode\tpopulation\tgenerations\tresult_file\n' > "$summary_file"
  fi
fi

IFS=',' read -r -a seed_values <<< "$SEEDS"

run_one() {
  local mode="$1"
  local population="$2"
  local label="$3"
  local seed="$4"
  local scenario="population-${label}-np${NP}-seed${seed}"
  local dry_args=()
  if [[ "$DRY_RUN" -eq 1 ]]; then
    dry_args+=(--dry-run)
  fi

  result_file="$(
    ./mpi_run_ga.sh \
      --hostfile "$HOSTFILE" \
      --np "$NP" \
      --wdir "$WORKDIR" \
      --python "$PYTHON" \
      --main "$MAIN" \
      --result-dir "$RESULT_DIR" \
      --label population \
      "${dry_args[@]}" \
      -- \
      --input "$INPUT" \
      --seed "$seed" \
      --population "$population" \
      --population-mode "$mode" \
      --generations "$GENERATIONS" \
      --mutation "$MUTATION" \
      --migration-strategy none \
      --two-opt-attempts "$TWO_OPT_ATTEMPTS" \
      --metadata-run-id "$scenario" \
      --metadata-scenario-name "population-${label}" \
      --metadata-containers-per-node "$CONTAINERS_PER_NODE" \
      --metadata-hostfile "$HOSTFILE" \
      --metadata-cpu-limit "$CPU_LIMIT" \
      --metadata-memory-limit "$MEMORY_LIMIT" \
      --metadata-code-version "$CODE_VERSION"
  )"

  if [[ "$DRY_RUN" -ne 1 ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$scenario" "$NP" "$seed" "none" "$mode" "$population" "$GENERATIONS" "$result_file" >> "$summary_file"
  fi

  if [[ "$FETCH" -eq 1 && "$DRY_RUN" -ne 1 ]]; then
    ./mpi_fetch_result.sh \
      --hostfile "$HOSTFILE" \
      --workdir "$WORKDIR" \
      --out-dir "$LOCAL_OUT_DIR" \
      --result "${RESULT_DIR%/}/$result_file" \
      --force
  fi
}

for seed in "${seed_values[@]}"; do
  echo "Running population-mode experiment: total population=1200 np=$NP seed=$seed" >&2
  run_one "total" "1200" "total-1200" "$seed"

  echo "Running population-mode experiment: per-rank population=100 np=$NP seed=$seed" >&2
  run_one "per-rank" "100" "per-rank-100" "$seed"

  echo "Running population-mode experiment: per-rank population=1200 np=$NP seed=$seed" >&2
  run_one "per-rank" "1200" "per-rank-1200" "$seed"
done

if [[ "$DRY_RUN" -ne 1 ]]; then
  echo "Summary: $summary_file"
fi
