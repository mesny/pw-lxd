#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  sudo setup-ovn-node.sh --node <julia|maria|solene>

This script uses fixed Tailscale IPs:
  julia  = 100.109.187.40
  maria  = 100.66.227.27
  solene = 100.105.203.22

Example:
  sudo setup-ovn-node.sh --node julia
  sudo setup-ovn-node.sh --node maria
  sudo setup-ovn-node.sh --node solene
EOF
}

NODE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node)
      NODE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$NODE" ]]; then
  usage
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

JULIA_IP="100.109.187.40"
MARIA_IP="100.66.227.27"
SOLENE_IP="100.105.203.22"

case "$NODE" in
  julia)
    LOCAL_IP="$JULIA_IP"
    ;;
  maria)
    LOCAL_IP="$MARIA_IP"
    ;;
  solene)
    LOCAL_IP="$SOLENE_IP"
    ;;
  *)
    echo "Invalid node: $NODE. Expected: julia, maria, or solene." >&2
    exit 1
    ;;
esac

NB_CONN="tcp:${JULIA_IP}:6641,tcp:${MARIA_IP}:6641,tcp:${SOLENE_IP}:6641"
SB_CONN="tcp:${JULIA_IP}:6642,tcp:${MARIA_IP}:6642,tcp:${SOLENE_IP}:6642"

echo "Node:       $NODE"
echo "Local IP:   $LOCAL_IP"
echo "Julia IP:   $JULIA_IP"
echo "Maria IP:   $MARIA_IP"
echo "Solene IP:  $SOLENE_IP"
echo "NB conn:    $NB_CONN"
echo "SB conn:    $SB_CONN"
echo

echo "Installing OVN/OVS packages..."
apt update
apt install -y ovn-central ovn-host openvswitch-switch

echo "Enabling services..."
systemctl enable openvswitch-switch
systemctl enable ovn-central
systemctl enable ovn-host

echo "Stopping OVN central before configuration..."
systemctl stop ovn-central || true

echo "Backing up /etc/default/ovn-central..."
if [[ -f /etc/default/ovn-central ]]; then
  cp -a /etc/default/ovn-central "/etc/default/ovn-central.bak.$(date +%Y%m%d%H%M%S)"
fi

echo "Writing /etc/default/ovn-central..."

if [[ "$NODE" == "julia" ]]; then
  cat > /etc/default/ovn-central <<EOF
OVN_CTL_OPTS=" \\
  --db-nb-addr=${LOCAL_IP} \\
  --db-nb-create-insecure-remote=yes \\
  --db-sb-addr=${LOCAL_IP} \\
  --db-sb-create-insecure-remote=yes \\
  --db-nb-cluster-local-addr=${LOCAL_IP} \\
  --db-sb-cluster-local-addr=${LOCAL_IP} \\
  --ovn-northd-nb-db=${NB_CONN} \\
  --ovn-northd-sb-db=${SB_CONN}"
EOF
else
  cat > /etc/default/ovn-central <<EOF
OVN_CTL_OPTS=" \\
  --db-nb-addr=${LOCAL_IP} \\
  --db-nb-cluster-remote-addr=${JULIA_IP} \\
  --db-nb-create-insecure-remote=yes \\
  --db-sb-addr=${LOCAL_IP} \\
  --db-sb-cluster-remote-addr=${JULIA_IP} \\
  --db-sb-create-insecure-remote=yes \\
  --db-nb-cluster-local-addr=${LOCAL_IP} \\
  --db-sb-cluster-local-addr=${LOCAL_IP} \\
  --ovn-northd-nb-db=${NB_CONN} \\
  --ovn-northd-sb-db=${SB_CONN}"
EOF
fi

echo "Starting OVN central..."
systemctl start ovn-central
systemctl restart openvswitch-switch

echo "Configuring Open vSwitch external_ids..."
ovs-vsctl set open_vswitch . \
  external_ids:ovn-remote="${SB_CONN}" \
  external_ids:ovn-encap-type=geneve \
  external_ids:ovn-encap-ip="${LOCAL_IP}"

echo "Restarting ovn-host..."
systemctl restart ovn-host

echo
echo "Status:"
systemctl --no-pager --full status ovn-central | sed -n '1,12p' || true
systemctl --no-pager --full status ovn-host | sed -n '1,12p' || true

echo
echo "OVS external_ids:"
ovs-vsctl get open_vswitch . external_ids

echo
echo "Done on node: $NODE"


