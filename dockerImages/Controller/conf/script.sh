#!/bin/bash
kubectl exec -n across-tc32 deploy/ru -- docker exec ru ip -6 route add fd00:0:2::2/64 encap seg6 mode encap segs fcff:2::1,fcff:1::1,fcff:6::1 dev eth1 table1
