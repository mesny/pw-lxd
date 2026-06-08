lxc list --format json | jq -r '
  .[]
  | select(.status == "Running")
  | select(.name | test("^mpi-"))
  | "\(.name).lxd slots=1"
' | sort > hosts.lxd

cat hosts.lxd

