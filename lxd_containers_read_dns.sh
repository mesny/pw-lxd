#!/usr/bin/env bash
set -euo pipefail

NAME_FILTER=""

usage() {
  echo "Usage: $0 [--name name-filter]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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
'

