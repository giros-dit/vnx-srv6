#!/bin/bash
kubectl exec -n across-tc32 deploy/upf -- docker exec upf ip -6 route replace fd00:0:2::/127 encap seg6 mode encap segs fcff:2::1,fcff:1::1,fcff:5::1,fcff:7::1 dev eth2.111
