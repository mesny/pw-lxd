#!/usr/bin/env bash
set -euo pipefail

HOSTFILE="hosts.lxd"
WORKDIR="/opt/pw-lxd"
OUT_DIR="."
RANK0_CONTAINER=""
RESULT=""
FORCE=0

usage() {
  cat >&2 <<'EOF'
Usage:
  ./mpi_fetch_result.sh --result mpi-lxd-12-smoke-001.json [options]

Options:
  --result file-or-path       Result file written by rank 0. Required.
  --hostfile path             MPI hostfile used for the run. Default: hosts.lxd
  --rank0 container           Rank-0 LXD container. Default: first host in hostfile
  --workdir path              MPI working directory in the container. Default: /opt/pw-lxd
  --out-dir path              Local destination directory. Default: current directory
  --force                     Overwrite an existing local destination file
  -h, --help                  Show this help

If --result is relative, it is resolved inside --workdir in the rank-0 container.
The remote file is removed only after it has been pulled successfully.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --result)
      RESULT="${2:?Error: --result requires a value}"
      shift 2
      ;;
    --hostfile)
      HOSTFILE="${2:?Error: --hostfile requires a value}"
      shift 2
      ;;
    --rank0)
      RANK0_CONTAINER="${2:?Error: --rank0 requires a value}"
      shift 2
      ;;
    --workdir)
      WORKDIR="${2:?Error: --workdir requires a value}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:?Error: --out-dir requires a value}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$RESULT" ]]; then
        RESULT="$1"
        shift
      else
        echo "Error: unknown argument: $1" >&2
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$RESULT" ]]; then
  echo "Error: missing required option: --result" >&2
  usage
  exit 1
fi

if [[ -z "$RANK0_CONTAINER" ]]; then
  if [[ ! -f "$HOSTFILE" ]]; then
    echo "Error: hostfile does not exist: $HOSTFILE" >&2
    exit 1
  fi

  first_host="$(awk 'NF && $1 !~ /^#/ {print $1; exit}' "$HOSTFILE")"
  if [[ -z "$first_host" ]]; then
    echo "Error: hostfile has no usable host entries: $HOSTFILE" >&2
    exit 1
  fi

  RANK0_CONTAINER="${first_host%.lxd}"
fi

if [[ "$RESULT" = /* ]]; then
  remote_path="$RESULT"
else
  remote_path="${WORKDIR%/}/$RESULT"
fi

local_path="${OUT_DIR%/}/$(basename "$RESULT")"

if [[ -e "$local_path" && "$FORCE" -ne 1 ]]; then
  echo "Error: local destination already exists: $local_path" >&2
  echo "Use --force to overwrite it." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

tmp_path="${local_path}.tmp.$$"
cleanup() {
  rm -f "$tmp_path"
}
trap cleanup EXIT

echo "Rank-0 container: $RANK0_CONTAINER"
echo "Remote result:    $remote_path"
echo "Local result:     $local_path"

lxc exec "$RANK0_CONTAINER" -- test -f "$remote_path"
lxc file pull "${RANK0_CONTAINER}${remote_path}" "$tmp_path"
mv -f "$tmp_path" "$local_path"
lxc exec "$RANK0_CONTAINER" -- rm -f -- "$remote_path"

echo "Pulled result to: $local_path"
echo "Removed remote result from: ${RANK0_CONTAINER}${remote_path}"
