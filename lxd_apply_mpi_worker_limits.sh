#!/usr/bin/env bash
set -euo pipefail

PROFILE="mpi-worker"
CPU_LIMIT="1"
MEMORY_LIMIT="4GiB"
DRY_RUN=0

usage() {
  cat >&2 <<'EOF'
Usage:
  ./lxd_apply_mpi_worker_limits.sh [options]

Sets LXD resource limits on the MPI worker profile.

Options:
  --profile name        LXD profile name. Default: mpi-worker
  --cpu n              limits.cpu value. Default: 1
  --memory size        limits.memory value. Default: 4GiB
  --dry-run            Print commands without changing LXD
  -h, --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?}"; shift 2 ;;
    --cpu) CPU_LIMIT="${2:?}"; shift 2 ;;
    --memory) MEMORY_LIMIT="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Error: unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf 'lxc profile set %q limits.cpu %q\n' "$PROFILE" "$CPU_LIMIT"
  printf 'lxc profile set %q limits.memory %q\n' "$PROFILE" "$MEMORY_LIMIT"
  exit 0
fi

lxc profile set "$PROFILE" limits.cpu "$CPU_LIMIT"
lxc profile set "$PROFILE" limits.memory "$MEMORY_LIMIT"

echo "Applied LXD limits to profile ${PROFILE}: limits.cpu=${CPU_LIMIT}, limits.memory=${MEMORY_LIMIT}"
