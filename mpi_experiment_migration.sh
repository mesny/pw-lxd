#!/usr/bin/env bash
set -euo pipefail

HOSTFILE="./hosts-4-per-node.lxd"
NP=""
WORKDIR="/opt/pw-lxd"
PYTHON=".venv/bin/python3"
MAIN="main.py"
INPUT="inputs/mazowieckie_114.csv"
RESULT_DIR="results"
LOCAL_OUT_DIR="results"
SEEDS="12345,22345,32345"
POPULATION="1200"
GENERATIONS="1000"
MUTATION="0.15"
TWO_OPT_ATTEMPTS="5"
MIGRATION_STRATEGY="all"
CPU_LIMIT="1"
MEMORY_LIMIT="4GiB"
CODE_VERSION="manual-v1"
FETCH=0
DRY_RUN=0
TIMEOUT_SECONDS=""
MPI_IFACE=""
RUN_GROUP_ID=""

usage() {
  cat >&2 <<'EOF'
Usage:
  ./mpi_experiment_migration.sh [options]

Runs the migration quality experiment: fixed ranks and total population,
comparing none/ring/global-best.

Options:
  --hostfile path       MPI hostfile. Default: ./hosts-4-per-node.lxd
  --np n                MPI ranks. Default: number of hostfile entries
  --wdir path           MPI working directory. Default: /opt/pw-lxd
  --python path         Python executable in --wdir. Default: .venv/bin/python3
  --main path           Application entrypoint in --wdir. Default: main.py
  --input path          TSP CSV input. Default: inputs/mazowieckie_114.csv
  --result-dir path     Remote result directory inside --wdir. Default: results
  --local-out-dir path  Local directory for fetched results. Default: results
  --seeds csv           Seeds/repetitions. Default: 12345,22345,32345
  --population n        Total population budget. Default: 1200
  --generations n       Number of generations. Default: 1000
  --migration-strategy  none, ring, global-best or all. Default: all
  --run-group-id id     Identifier shared by comparable runs. Default: generated UUIDv7
  --fetch               Fetch each result from rank-0 container after a run
  --mpi-iface name      Force OpenMPI TCP traffic over this interface
  --timeout seconds     Stop each mpirun after this many seconds. Default: no timeout
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
    --population) POPULATION="${2:?}"; shift 2 ;;
    --generations) GENERATIONS="${2:?}"; shift 2 ;;
    --migration-strategy) MIGRATION_STRATEGY="${2:?}"; shift 2 ;;
    --run-group-id) RUN_GROUP_ID="${2:?}"; shift 2 ;;
    --fetch) FETCH=1; shift ;;
    --mpi-iface) MPI_IFACE="${2:?}"; shift 2 ;;
    --timeout) TIMEOUT_SECONDS="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Error: unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

generate_uuidv7() {
  local timestamp_ms
  local timestamp_hex
  local random_hex
  local variant_nibble

  timestamp_ms="$(date -u +%s%3N)"
  timestamp_hex="$(printf '%012x' "$timestamp_ms")"
  random_hex="$(od -An -N10 -tx1 /dev/urandom | tr -d ' \n')"
  variant_nibble="$(printf '%x' "$(( (0x${random_hex:3:1} & 3) | 8 ))")"

  printf '%s-%s-7%s-%s%s-%s\n' \
    "${timestamp_hex:0:8}" \
    "${timestamp_hex:8:4}" \
    "${random_hex:0:3}" \
    "$variant_nibble" \
    "${random_hex:4:3}" \
    "${random_hex:7:12}"
}

count_hostfile_entries() {
  awk 'NF && $1 !~ /^#/ {count++} END {print count + 0}' "$1"
}

validate_positive_integer() {
  local name="$1"
  local value="$2"

  if [[ ! "$value" =~ ^[0-9]+$ || "$value" -lt 1 ]]; then
    echo "Error: $name must be a positive integer: $value" >&2
    exit 1
  fi
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

if [[ -z "$RUN_GROUP_ID" ]]; then
  RUN_GROUP_ID="$(generate_uuidv7)"
fi

if [[ ! -f "$HOSTFILE" ]]; then
  echo "Error: hostfile does not exist: $HOSTFILE" >&2
  exit 1
fi

if [[ -z "$NP" ]]; then
  NP="$(count_hostfile_entries "$HOSTFILE")"
fi

validate_positive_integer "--np" "$NP"
validate_positive_integer "--population" "$POPULATION"

case "$MIGRATION_STRATEGY" in
  none|ring|global-best|all) ;;
  *)
    echo "Error: --migration-strategy must be one of: none, ring, global-best, all" >&2
    exit 1
    ;;
esac

min_total_population=$((NP * 4))
if [[ "$POPULATION" -lt "$min_total_population" ]]; then
  echo "Error: --population is too small before MPI start: population=$POPULATION, mpi_processes=$NP, minimum_total=$min_total_population." >&2
  exit 1
fi

summary_file="${LOCAL_OUT_DIR%/}/runs.tsv"
summary_header='run_group_id	run_id	scenario	hostfile	np	containers_per_node	seed	migration	population_mode	population	generations	result_file'
if [[ "$DRY_RUN" -ne 1 ]]; then
  mkdir -p "$LOCAL_OUT_DIR"
  if [[ -f "$summary_file" && "$(head -n 1 "$summary_file")" != "$summary_header" ]]; then
    mv "$summary_file" "${summary_file}.pre-run-ids.bak"
  fi
  if [[ ! -f "$summary_file" ]]; then
    printf '%s\n' "$summary_header" > "$summary_file"
  fi
fi

IFS=',' read -r -a seed_values <<< "$SEEDS"
CONTAINERS_PER_NODE="$(containers_per_node_from_hostfile "$HOSTFILE")"

run_one() {
  local strategy="$1"
  local interval="$2"
  local immigrants="$3"
  local seed="$4"
  local run_id
  local scenario
  local dry_args=()
  local timeout_args=()
  local mpi_iface_args=()

  run_id="$(generate_uuidv7)"
  scenario="migration-${strategy}-np${NP}-seed${seed}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    dry_args+=(--dry-run)
  fi

  if [[ -n "$TIMEOUT_SECONDS" ]]; then
    timeout_args+=(--timeout "$TIMEOUT_SECONDS")
  fi

  if [[ -n "$MPI_IFACE" ]]; then
    mpi_iface_args+=(--mpi-iface "$MPI_IFACE")
  fi

  result_file="$(
    ./mpi_run_ga.sh \
      --hostfile "$HOSTFILE" \
      --np "$NP" \
      --wdir "$WORKDIR" \
      --python "$PYTHON" \
      --main "$MAIN" \
      --result-dir "$RESULT_DIR" \
      --label migration \
      "${mpi_iface_args[@]}" \
      "${timeout_args[@]}" \
      "${dry_args[@]}" \
      -- \
      --input "$INPUT" \
      --seed "$seed" \
      --population "$POPULATION" \
      --population-mode total \
      --generations "$GENERATIONS" \
      --mutation "$MUTATION" \
      --migration-strategy "$strategy" \
      --migration-interval "$interval" \
      --immigrants "$immigrants" \
      --two-opt-attempts "$TWO_OPT_ATTEMPTS" \
      --metadata-run-id "$run_id" \
      --metadata-run-group-id "$RUN_GROUP_ID" \
      --metadata-scenario-name "migration-${strategy}" \
      --metadata-containers-per-node "$CONTAINERS_PER_NODE" \
      --metadata-hostfile "$HOSTFILE" \
      --metadata-cpu-limit "$CPU_LIMIT" \
      --metadata-memory-limit "$MEMORY_LIMIT" \
      --metadata-code-version "$CODE_VERSION"
  )"

  if [[ "$DRY_RUN" -ne 1 ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$RUN_GROUP_ID" "$run_id" "$scenario" "$HOSTFILE" "$NP" "$CONTAINERS_PER_NODE" "$seed" "$strategy" "total" "$POPULATION" "$GENERATIONS" "$result_file" >> "$summary_file"
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

run_strategy_for_seed() {
  local strategy="$1"
  local seed="$2"

  case "$strategy" in
    none)
      echo "Running migration experiment: strategy=none np=$NP seed=$seed" >&2
      run_one "none" "50" "0" "$seed"
      ;;
    ring)
      echo "Running migration experiment: strategy=ring np=$NP seed=$seed" >&2
      run_one "ring" "50" "2" "$seed"
      ;;
    global-best)
      echo "Running migration experiment: strategy=global-best np=$NP seed=$seed" >&2
      run_one "global-best" "100" "1" "$seed"
      ;;
  esac
}

for seed in "${seed_values[@]}"; do
  if [[ "$MIGRATION_STRATEGY" == "all" ]]; then
    run_strategy_for_seed "none" "$seed"
    run_strategy_for_seed "ring" "$seed"
    run_strategy_for_seed "global-best" "$seed"
  else
    run_strategy_for_seed "$MIGRATION_STRATEGY" "$seed"
  fi
done

if [[ "$DRY_RUN" -ne 1 ]]; then
  echo "Summary: $summary_file"
  echo "Run group: $RUN_GROUP_ID"
fi
