#!/usr/bin/env bash
set -euo pipefail

OUT=""
NAME_FILTER=""

usage() {
  echo "Usage: $0 --out /path/to/file [--name name-filter]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT="${2:?Error: --out requires a value}"
      shift 2
      ;;
    --name)
      NAME_FILTER="${2:?Error: --name requires a value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$OUT" ]]; then
  echo "Error: missing required option: --out" >&2
  usage
  exit 1
fi

if [[ ! -e "$OUT" ]]; then
  echo "Error: target file does not exist: $OUT" >&2
  exit 1
fi

if [[ ! -f "$OUT" ]]; then
  echo "Error: target path is not a regular file: $OUT" >&2
  exit 1
fi

lxc list --format json | jq -r --arg name_filter "$NAME_FILTER" '
  .[] as $c
  | select($c.status == "Running")
  | select($name_filter == "" or ($c.name | contains($name_filter)))
  | (
      $c.state.network.eth0.addresses // []
      | map(select(.family == "inet" and .scope == "global"))
      | .[0].address
    ) as $ip
  | select($ip != null)
  | "\($ip) \($c.name).lxd \($c.name)"
' | sudo tee "$OUT" >/dev/null

cat "$OUT"
