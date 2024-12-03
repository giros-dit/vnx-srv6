#!/bin/bash

# Namespace en Kubernetes
NS="c9s-srv6"

# Lista de VLANs
VLANS=(1012 1023 1014 1034 2011 2032)

# Iterar sobre cada VLAN y crear la definición
for VLAN in "${VLANS[@]}"; do
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

