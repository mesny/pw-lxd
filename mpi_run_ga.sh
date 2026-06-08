#!/usr/bin/env bash
set -euo pipefail

HOSTFILE="./hosts.lxd"
NP=""
WORKDIR="/opt/pw-lxd"
PYTHON=".venv/bin/python3"
MAIN="main.py"
RESULT_DIR=""
LABEL=""
DRY_RUN=0

usage() {
  cat >&2 <<'EOF'
Usage:
  ./mpi_run_ga.sh [wrapper options] -- [main.py arguments without --output]

Wrapper options:
  --hostfile path       MPI hostfile. Default: ./hosts.lxd
  --np n                Number of MPI processes. Default: number of hostfile entries
  --wdir path           MPI working directory. Default: /opt/pw-lxd
  --python path         Python executable relative to --wdir or absolute. Default: .venv/bin/python3
  --main path           Application entrypoint relative to --wdir or absolute. Default: main.py
  --result-dir path     Directory for result file inside --wdir. Default: --wdir directly
  --label text          Extra filename label
  --dry-run             Print generated filename and command, but do not run MPI
  -h, --help            Show this help

The wrapper generates a JSON result filename from selected arguments and UTC time,
passes it to main.py as --output, runs mpirun, and prints only the result filename
to stdout after a successful run. mpirun/application output is written to stderr.
EOF
}

slugify() {
  printf '%s' "$1" |
    tr '[:upper:]' '[:lower:]' |
    sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

count_hostfile_entries() {
  awk 'NF && $1 !~ /^#/ {count++} END {print count + 0}' "$1"
}

arg_value() {
  local name="$1"
  shift

  while [[ $# -gt 0 ]]; do
    case "$1" in
      "$name")
        if [[ $# -lt 2 ]]; then
          return 0
        fi
        printf '%s' "$2"
        return 0
        ;;
      "$name="*)
        printf '%s' "${1#*=}"
        return 0
        ;;
    esac
    shift
  done
}

add_name_part() {
  local value="$1"
  local slug

  slug="$(slugify "$value")"
  if [[ -n "$slug" ]]; then
    name_parts+=("$slug")
  fi
}

add_labeled_name_part() {
  local label="$1"
  local value="$2"

  if [[ -n "$value" ]]; then
    add_name_part "${label}${value}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostfile)
      HOSTFILE="${2:?Error: --hostfile requires a value}"
      shift 2
      ;;
    --np)
      NP="${2:?Error: --np requires a value}"
      shift 2
      ;;
    --wdir)
      WORKDIR="${2:?Error: --wdir requires a value}"
      shift 2
      ;;
    --python)
      PYTHON="${2:?Error: --python requires a value}"
      shift 2
      ;;
    --main)
      MAIN="${2:?Error: --main requires a value}"
      shift 2
      ;;
    --result-dir)
      RESULT_DIR="${2:?Error: --result-dir requires a value}"
      shift 2
      ;;
    --label)
      LABEL="${2:?Error: --label requires a value}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "Error: unknown wrapper argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

APP_ARGS=("$@")

if [[ ${#APP_ARGS[@]} -eq 0 ]]; then
  echo "Error: missing main.py arguments after --" >&2
  usage
  exit 1
fi

for arg in "${APP_ARGS[@]}"; do
  if [[ "$arg" == "--output" || "$arg" == --output=* ]]; then
    echo "Error: do not pass --output; this wrapper generates it." >&2
    exit 1
  fi
done

if [[ ! -f "$HOSTFILE" ]]; then
  echo "Error: hostfile does not exist: $HOSTFILE" >&2
  exit 1
fi

if [[ -z "$NP" ]]; then
  NP="$(count_hostfile_entries "$HOSTFILE")"
  if [[ "$NP" -lt 1 ]]; then
    echo "Error: hostfile has no usable host entries: $HOSTFILE" >&2
    exit 1
  fi
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_id="$(arg_value --metadata-run-id "${APP_ARGS[@]}")"
scenario="$(arg_value --metadata-scenario-name "${APP_ARGS[@]}")"
cities="$(arg_value --cities "${APP_ARGS[@]}")"
population="$(arg_value --population "${APP_ARGS[@]}")"
generations="$(arg_value --generations "${APP_ARGS[@]}")"
migration="$(arg_value --migration-strategy "${APP_ARGS[@]}")"

name_parts=()
add_name_part "$LABEL"
add_name_part "$run_id"
add_name_part "$scenario"
add_labeled_name_part "np" "$NP"
add_labeled_name_part "c" "$cities"
add_labeled_name_part "p" "$population"
add_labeled_name_part "g" "$generations"
add_name_part "$migration"
add_name_part "$timestamp"

if [[ ${#name_parts[@]} -eq 0 ]]; then
  result_file="mpi-ga-${timestamp}.json"
else
  result_file="$(IFS=-; printf '%s' "${name_parts[*]}").json"
fi

if [[ -n "$RESULT_DIR" ]]; then
  output_path="${RESULT_DIR%/}/$result_file"
else
  output_path="$result_file"
fi

cmd=(
  mpirun
  --mca orte_keep_fqdn_hostnames 1
  --hostfile "$HOSTFILE"
  -np "$NP"
  --wdir "$WORKDIR"
  "$PYTHON" "$MAIN"
  "${APP_ARGS[@]}"
  --output "$output_path"
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf 'result_file=%s\n' "$result_file" >&2
  printf 'output_path=%s\n' "$output_path" >&2
  printf 'command:' >&2
  printf ' %q' "${cmd[@]}" >&2
  printf '\n' >&2
  printf '%s\n' "$result_file"
  exit 0
fi

"${cmd[@]}" >&2
printf '%s\n' "$result_file"
