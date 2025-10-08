#!/bin/bash

# Script to create network interfaces and Network Attachment Definitions for redAcross11Nodes
# This script configures VLANs and NADs for the 11-node topology

# Verificar que al menos se pasen dos parámetros
if [ "$#" -lt 2 ]; then
  echo "Uso: $0 <namespace> <vlan1> [<vlan2> ... <vlanN>]"
  echo "Ejemplo: $0 c9s 1001 1002 1003 ... 1017 2001 2002 2003 2004 2005"
  exit 1
fi

# Namespace en Kubernetes
NS="$1"
shift

# Lista de VLANs
VLANS=("$@")

echo "Creating Network Attachment Definitions for namespace: $NS"
echo "VLANs: ${VLANS[@]}"

# Crear definiciones de NetworkAttachment en Kubernetes
for VLAN in "${VLANS[@]}"; do
  echo "Creating NAD for net${VLAN}..."
  cat <<EOF | kubectl create -f -
apiVersion: "k8s.cni.cncf.io/v1"
kind: NetworkAttachmentDefinition
metadata:
  name: net${VLAN}
  namespace: $NS
spec:
  config: '{
      "cniVersion": "0.3.0",
      "type": "macvlan",
      "master": "br-vlan.${VLAN}",
      "mode": "bridge",
      "ipam": {}
    }'
EOF
done

# Configurar Open vSwitch y VLANs en los servidores
echo "Configuring Open vSwitch on compute nodes..."
for i in {1..3}; do
  echo "Configuring compute${i}..."
  ssh root@compute${i} "
    apt install -y openvswitch-switch
    ovs-vsctl add-br br-vlan
    ovs-vsctl add-port br-vlan vlannet
    ip link set br-vlan up
  " 2>/dev/null
  
  for VLAN in "${VLANS[@]}"; do
    ssh root@compute${i} "
      ip link add link br-vlan name br-vlan.${VLAN} type vlan id ${VLAN}
      ip link set br-vlan.${VLAN} up
    " 2>/dev/null
  done
done

echo "Network configuration complete!"
echo ""
echo "Core network VLANs: 1001-1017 (17 links)"
echo "Edge network VLANs: 2001-2005 (5 links)"
