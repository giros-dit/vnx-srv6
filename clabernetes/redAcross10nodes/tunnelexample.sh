#!/bin/bash
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 route add  fd00:0:2::2 encap seg6 mode encap segs fcff:2::1,fcff:1::1,fcff:11::1  dev eth1 table tunel1
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 route add  fd00:0:2::3 encap seg6 mode encap segs fcff:4::1,fcff:11::1  dev eth1 table tunel2
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 route add  fd00:0:2::4 encap seg6 mode encap segs fcff:7::1,fcff:2::1,fcff:11::1  dev eth1 table tunel3
kubectl exec -n across-tc32 deploy/r11 -- docker exec r11 ip -6 route add fd00:0:1::1 encap seg6 mode encap segs fcff:13::1 dev eth1