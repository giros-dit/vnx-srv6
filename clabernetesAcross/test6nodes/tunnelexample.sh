#!/bin/bash
kubectl exec -n across-tc32 deploy/rupf -- docker exec rupf ip -6 route add  fd00:0:2::1 encap seg6 mode encap segs fcff:2::1,fcff:1::1 dev eth2.111
kubectl exec -n across-tc32 deploy/rgnb -- docker exec rgnb ip -6 route add fd00:0:1::1 encap seg6 mode encap segs fcff:1::1,fcff:2::1 dev eth2.111