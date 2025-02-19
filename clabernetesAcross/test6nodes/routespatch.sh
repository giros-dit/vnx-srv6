#!/bin/bash
kubectl exec deploy/hgnb-h1 -- docker exec hgnb-h1 ip -6 route add fd00:0:1::1/127 via fd00:0:2::0
kubectl exec deploy/hgnb-h2 -- docker exec hgnb-h2 ip -6 route add fd00:0:1::3/127 via fd00:0:2::2
kubectl exec deploy/hgnb-h3 -- docker exec hgnb-h3 ip -6 route add fd00:0:1::5/127 via fd00:0:2::4
kubectl exec deploy/hupf-h1 -- docker exec hupf-h1 ip -6 route add fd00:0:2::1/127 via fd00:0:1::0
kubectl exec deploy/hupf-h1 -- docker exec hupf-h1 ip -6 route add fd00:0:2::3/127 via fd00:0:1::2
kubectl exec deploy/hupf-h1 -- docker exec hupf-h1 ip -6 route add fd00:0:2::5/127 via fd00:0:1::4  
