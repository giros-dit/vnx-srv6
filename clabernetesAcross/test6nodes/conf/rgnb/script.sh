#!/bin/bash
kubectl exec -n across-tc32 deploy/gnb -- docker exec gnb ip -6 route add fd00:0:1::/127 encap seg6 mode encap segs fcff:1::1,fcff:2::1,fcff:6::1,fcff:8::1 dev eth2.111
