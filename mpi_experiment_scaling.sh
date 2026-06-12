#!/usr/bin/env bash
set -euo pipefail

HOSTFILES="./hosts-1-per-node.lxd,./hosts-2-per-node.lxd,./hosts-4-per-node.lxd"
WORKDIR="/opt/pw-lxd"
PYTHON=".venv/bin/python3"
MAIN="main.py"
INPUT="inputs/mazowieckie_30.csv"
RESULT_DIR="results"
LOCAL_OUT_DIR="results"
SEEDS="12345,22345,32345"
POPULATION=""
GENERATIONS="10"
MUTATION="0.15"
TWO_OPT_ATTEMPTS="5"
CPU_LIMIT="1"
MEMORY_LIMIT="4GiB"
CODE_VERSION="manual-v1"
FETCH=0
DRY_RUN=0
TIMEOUT_SECONDS=""
MPI_IFACE=""
AUTO_POPULATION=0
MIN_POPULATION_PER_RANK=4
RUN_GROUP_ID=""

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
  --result-dir path     Remote result directory inside --wdir. Default: results
  --local-out-dir path  Local directory for fetched results. Default: results
  --seeds csv           Seeds/repetitions. Default: 12345,22345,32345
  --population n        Total population budget. Default: 4 * ranks from hostfile
  --auto-population     Increase explicit --population to the minimum valid total for each hostfile
  --generations n       Number of generations. Default: 1000
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
    --auto-population) AUTO_POPULATION=1; shift ;;
    --generations) GENERATIONS="${2:?}"; shift 2 ;;
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

if [[ -z "$RUN_GROUP_ID" ]]; then
  RUN_GROUP_ID="$(generate_uuidv7)"
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

IFS=',' read -r -a hostfile_values <<< "$HOSTFILES"
IFS=',' read -r -a seed_values <<< "$SEEDS"

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

run_one() {
  local hostfile="$1"
  local seed="$2"
  local np
  local containers_per_node
  local scenario
  local run_id
  local effective_population
  local min_total_population
  local dry_args=()
  local timeout_args=()
  local mpi_iface_args=()

  if [[ ! -f "$hostfile" ]]; then
    echo "Error: hostfile does not exist: $hostfile" >&2
    exit 1
  fi

  np="$(count_hostfile_entries "$hostfile")"
  if [[ "$np" -lt 1 ]]; then
    echo "Error: hostfile has no usable host entries: $hostfile" >&2
    exit 1
  fi

  min_total_population=$((np * MIN_POPULATION_PER_RANK))
  if [[ -z "$POPULATION" ]]; then
    effective_population="$min_total_population"
    echo "Using default population for hostfile=$hostfile: population=$effective_population np=$np per_rank=$MIN_POPULATION_PER_RANK" >&2
  else
    validate_positive_integer "--population" "$POPULATION"
    effective_population="$POPULATION"
  fi

  if [[ "$effective_population" -lt "$min_total_population" ]]; then
    if [[ "$AUTO_POPULATION" -eq 1 ]]; then
      echo "Adjusting population for hostfile=$hostfile: requested=$POPULATION minimum=$min_total_population np=$np" >&2
      effective_population="$min_total_population"
    else
      echo "Error: --population is too small before MPI start: population=$POPULATION, mpi_processes=$np, minimum_total=$min_total_population." >&2
      echo "Use --population $min_total_population or add --auto-population." >&2
      exit 1
    fi
  fi

  containers_per_node="$(containers_per_node_from_hostfile "$hostfile")"
  scenario="scaling-${containers_per_node}pernode-np${np}-seed${seed}"
  run_id="$(generate_uuidv7)"

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
      --hostfile "$hostfile" \
      --wdir "$WORKDIR" \
      --python "$PYTHON" \
      --main "$MAIN" \
      --result-dir "$RESULT_DIR" \
      --label scaling \
      "${mpi_iface_args[@]}" \
      "${timeout_args[@]}" \
      "${dry_args[@]}" \
      -- \
      --input "$INPUT" \
      --seed "$seed" \
      --population "$effective_population" \
      --population-mode total \
      --generations "$GENERATIONS" \
      --mutation "$MUTATION" \
      --migration-strategy none \
      --two-opt-attempts "$TWO_OPT_ATTEMPTS" \
      --metadata-run-id "$run_id" \
      --metadata-run-group-id "$RUN_GROUP_ID" \
      --metadata-scenario-name "scaling-${containers_per_node}-per-node-np-${np}" \
      --metadata-containers-per-node "$containers_per_node" \
      --metadata-hostfile "$hostfile" \
      --metadata-cpu-limit "$CPU_LIMIT" \
      --metadata-memory-limit "$MEMORY_LIMIT" \
      --metadata-code-version "$CODE_VERSION"
  )"

  if [[ "$DRY_RUN" -ne 1 ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$RUN_GROUP_ID" "$run_id" "$scenario" "$hostfile" "$np" "$containers_per_node" "$seed" "none" "total" "$effective_population" "$GENERATIONS" "$result_file" >> "$summary_file"
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
