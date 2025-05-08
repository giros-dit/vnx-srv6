#!/bin/bash
kubectl exec deploy/rg1 -- docker exec rg1 ip -6 route add fd00:0:1::/127 encap seg6 mode encap segs fcff:5::1 dev eth1