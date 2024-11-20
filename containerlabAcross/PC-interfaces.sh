#!/bin/sh
sudo docker exec clab-srv6-r1 service frr start
sudo docker exec clab-srv6-r2 service frr start
sudo docker exec clab-srv6-r3 service frr start
sudo docker exec clab-srv6-r4 service frr start

sudo docker exec clab-srv6-h1 ip link add link eth1 name eth1.111 type vlan id 111
sudo docker exec clab-srv6-h1 ip link add link eth1 name eth1.112 type vlan id 112
sudo docker exec clab-srv6-h1 ip -6 addr add fd00:0:1::1/127 dev eth1.111
sudo docker exec clab-srv6-h1 ip -6 addr add fd00:0:1::3/127 dev eth1.112
sudo docker exec clab-srv6-h1 ip link set eth1.111 up
sudo docker exec clab-srv6-h1 ip link set eth1.112 up
sudo docker exec clab-srv6-h1 ip -6 route add fd00:0:2::1/127 via fd00:0:1::
sudo docker exec clab-srv6-h1 ip -6 route add fd00:0:2::3/127 via fd00:0:1::2

sudo docker exec clab-srv6-h2 ip link add link eth1 name eth1.111 type vlan id 111
sudo docker exec clab-srv6-h2 ip link add link eth1 name eth1.112 type vlan id 112
sudo docker exec clab-srv6-h2 ip -6 addr add fd00:0:2::1/127 dev eth1.111
sudo docker exec clab-srv6-h2 ip -6 addr add fd00:0:2::3/127 dev eth1.112
sudo docker exec clab-srv6-h2 ip link set eth1.111 up
sudo docker exec clab-srv6-h2 ip link set eth1.112 up
sudo docker exec clab-srv6-h2 ip -6 route add fd00:0:1::1/127 via fd00:0:2::
sudo docker exec clab-srv6-h2 ip -6 route add fd00:0:1::3/127 via fd00:0:2::2

sudo docker exec clab-srv6-r1 sysctl -p
sudo docker exec clab-srv6-r1 vtysh -c 'configure terminal' -f /etc/frr/zebra.conf
sudo docker exec clab-srv6-r1 vtysh -c 'configure terminal' -f /etc/frr/isisd.conf
sudo docker exec clab-srv6-r1 sysctl -w net.ipv6.conf.eth1.seg6_enabled=1
sudo docker exec clab-srv6-r1 sysctl -w net.ipv6.conf.eth2.seg6_enabled=1
sudo docker exec clab-srv6-r1 ip link add link eth3 name eth3.111 type vlan id 111
sudo docker exec clab-srv6-r1 ip link add link eth3 name eth3.112 type vlan id 112
sudo docker exec clab-srv6-r1 ip -6 addr add fd00:0:1::/127 dev eth3.111
sudo docker exec clab-srv6-r1 ip -6 addr add fd00:0:1::2/127 dev eth3.112
sudo docker exec clab-srv6-r1 ip link set eth3.111 up
sudo docker exec clab-srv6-r1 ip link set eth3.112 up

sudo docker exec clab-srv6-r2 sysctl -p
sudo docker exec clab-srv6-r2 vtysh -c 'configure terminal' -f /etc/frr/zebra.conf
sudo docker exec clab-srv6-r2 vtysh -c 'configure terminal' -f /etc/frr/isisd.conf
sudo docker exec clab-srv6-r2 sysctl -w net.ipv6.conf.eth1.seg6_enabled=1
sudo docker exec clab-srv6-r2 sysctl -w net.ipv6.conf.eth2.seg6_enabled=1

sudo docker exec clab-srv6-r3 sysctl -p
sudo docker exec clab-srv6-r3 vtysh -c 'configure terminal' -f /etc/frr/zebra.conf
sudo docker exec clab-srv6-r3 vtysh -c 'configure terminal' -f /etc/frr/isisd.conf
sudo docker exec clab-srv6-r3 sysctl -w net.ipv6.conf.eth1.seg6_enabled=1
sudo docker exec clab-srv6-r3 sysctl -w net.ipv6.conf.eth2.seg6_enabled=1
sudo docker exec clab-srv6-r3 ip link add link eth3 name eth3.111 type vlan id 111
sudo docker exec clab-srv6-r3 ip link add link eth3 name eth3.112 type vlan id 112
sudo docker exec clab-srv6-r3 ip -6 addr add fd00:0:2::/127 dev eth3.111
sudo docker exec clab-srv6-r3 ip -6 addr add fd00:0:2::2/127 dev eth3.112
sudo docker exec clab-srv6-r3 ip link set eth3.111 up
sudo docker exec clab-srv6-r3 ip link set eth3.112 up

sudo docker exec clab-srv6-r4 sysctl -p
sudo docker exec clab-srv6-r4 vtysh -c 'configure terminal' -f /etc/frr/zebra.conf
sudo docker exec clab-srv6-r4 vtysh -c 'configure terminal' -f /etc/frr/isisd.conf
sudo docker exec clab-srv6-r4 sysctl -w net.ipv6.conf.eth1.seg6_enabled=1
sudo docker exec clab-srv6-r4 sysctl -w net.ipv6.conf.eth2.seg6_enabled=1

