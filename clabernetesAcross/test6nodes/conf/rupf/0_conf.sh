#!/bin/bash
ip link add link eth1 name eth1.111 type vlan id 111
ip link add link eth1 name eth1.112 type vlan id 112
ip link add link eth1 name eth1.113 type vlan id 113
ip link add link eth2 name eth2.111 type vlan id 111
ip link add link eth2 name eth2.112 type vlan id 112
ip link add link eth2 name eth2.113 type vlan id 113