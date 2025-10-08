#!/bin/bash
kubectl exec deploy/rgnb -- docker exec rgnb ip -6 route add fd00:0:1::/64 encap seg6 mode encap segs fcff:11::1 dev eth2
