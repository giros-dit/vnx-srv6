#!/bin/bash
kubectl exec deploy/rg -- docker exec rg1 ip -6 route add fd00:0:1::/127 encap seg6 mode encap segs fcff:13::1 dev eth1
kubectl exec deploy/rc -- docker exec rg2 ip -6 route add fd00:0:1::/127 encap seg6 mode encap segs fcff:13::1 dev eth1