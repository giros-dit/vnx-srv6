#!/bin/bash
kubectl exec -n across-tc32 deploy/rupf -- docker exec rupf ip -6 route add fd00:0:2::2 encap seg6 mode encap segs fcff:10::1,fcff:5::1,fcff:4::1,fcff:1::1 dev eth1
kubectl exec -n across-tc32 deploy/rupf -- docker exec rupf ip -6 route add fd00:0:2::3 encap seg6 mode encap segs fcff:11::1,fcff:8::1,fcff:7::1,fcff:1::1 dev eth1
