#!/bin/bash

# Script to create VLAN interfaces using CNI for redAcross11Nodes topology

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 <compute_node_number>"
  echo "Ejemplo: $0 1"
  exit 1
fi

COMPUTE_NODE=$1

echo "Creating VLANs on compute${COMPUTE_NODE} for 11-node topology..."

# Core network VLANs (1001-1017)
CORE_VLANS=(1001 1002 1003 1004 1005 1006 1007 1008 1009 1010 1011 1012 1013 1014 1015 1016 1017)

# Edge network VLANs (2001-2005)
EDGE_VLANS=(2001 2002 2003 2004 2005)

# Ensure OVS bridge exists
ssh root@compute${COMPUTE_NODE} "
  ovs-vsctl list-br | grep -q br-vlan || {
    ovs-vsctl add-br br-vlan
    ovs-vsctl add-port br-vlan vlannet
    ip link set br-vlan up
  }
"

# Create core VLANs
for VLAN in "${CORE_VLANS[@]}"; do
  echo "Creating VLAN ${VLAN} on compute${COMPUTE_NODE}..."
  ssh root@compute${COMPUTE_NODE} "
    ip link show br-vlan.${VLAN} >/dev/null 2>&1 || {
      ip link add link br-vlan name br-vlan.${VLAN} type vlan id ${VLAN}
      ip link set br-vlan.${VLAN} up
    }
  "
done

# Create edge VLANs
for VLAN in "${EDGE_VLANS[@]}"; do
  echo "Creating VLAN ${VLAN} on compute${COMPUTE_NODE}..."
  ssh root@compute${COMPUTE_NODE} "
    ip link show br-vlan.${VLAN} >/dev/null 2>&1 || {
      ip link add link br-vlan name br-vlan.${VLAN} type vlan id ${VLAN}
      ip link set br-vlan.${VLAN} up
    }
  "
done

echo "VLAN creation complete on compute${COMPUTE_NODE}!"
echo "Total VLANs created: $((${#CORE_VLANS[@]} + ${#EDGE_VLANS[@]}))"
