service frr start
sysctl -p
vtysh -c 'configure terminal' -f /etc/frr/zebra.conf
vtysh -c 'configure terminal' -f /etc/frr/isisd.conf
sysctl -w net.ipv6.conf.eth1.seg6_enabled=1
sysctl -w net.ipv6.conf.eth2.seg6_enabled=1