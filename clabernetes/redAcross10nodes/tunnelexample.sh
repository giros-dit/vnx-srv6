#!/bin/bash
kubectl exec -n across-tc32 deploy/ru -- docker exec ru sh -c 'echo "1 tunel1" >> /etc/iproute2/rt_tables'
kubectl exec -n across-tc32 deploy/ru -- docker exec ru sh -c 'echo "2 tunel2" >> /etc/iproute2/rt_tables'
kubectl exec -n across-tc32 deploy/ru -- docker exec ru sh -c 'echo "4 tunel4" >> /etc/iproute2/rt_tables'
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 rule add to fd00:0:2::2 lookup tunel1
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 rule add to fd00:0:2::3 lookup tunel2
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 rule add to fd00:0:3::2 lookup tunel4
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 route add fd00:0:2::2 encap seg6 mode encap segs fcff:3::1,fcff:2::1,fcff:1::1,fcff:11::1 dev eth1 table tunel1
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 route add fd00:0:2::3 encap seg6 mode encap segs fcff:7::1,fcff:6::1,fcff:4::1,fcff:11::1 dev eth1 table tunel2
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 route add fd00:0:3::2 encap seg6 mode encap segs fcff:7::1,fcff:6::1,fcff:5::1,fcff:2::1,fcff:12::1 dev eth1 table tunel4