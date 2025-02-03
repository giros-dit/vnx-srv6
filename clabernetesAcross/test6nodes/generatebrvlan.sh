#!/bin/bash

for i in {1..3}; do
ssh root@compute${i} "
  apt install -y openvswitch-switch
  ovs-vsctl add-br br-vlan
  ovs-vsctl add-port br-vlan vlannet
  ip link set br-vlan up
"
for v in 1001 1002 1003 1004 1005 1006 1007 1008 2001 2002; do
ssh root@compute${i} "
  ip link add link br-vlan name br-vlan.${v} type vlan id ${v}
  ip link set br-vlan.${v} up
"
done
done
