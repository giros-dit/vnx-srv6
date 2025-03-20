#!/bin/bash
kubectl exec deploy/r13 -- docker exec r13 sh -c 'echo "101 tunel1" >> /etc/iproute2/rt_tables'
kubectl exec deploy/r13 -- docker exec r13 sh -c 'echo "102 tunel2" >> /etc/iproute2/rt_tables'
kubectl exec deploy/r13 -- docker exec r13 sh -c 'echo "103 tunel3" >> /etc/iproute2/rt_tables'
kubectl exec deploy/r13 -- docker exec r13 sh -c 'echo "104 tunel4" >> /etc/iproute2/rt_tables'
kubectl exec deploy/r13 -- docker exec r13 sh -c 'echo "105 tunel5" >> /etc/iproute2/rt_tables'
kubectl exec deploy/r13 -- docker exec r13 sh -c 'echo "106 tunel6" >> /etc/iproute2/rt_tables'
kubectl exec deploy/r13 -- docker exec r13 ip -6 rule add to fd00:0:2::2 lookup tunel1
kubectl exec deploy/r13 -- docker exec r13 ip -6 rule add to fd00:0:2::3 lookup tunel2
kubectl exec deploy/r13 -- docker exec r13 ip -6 rule add to fd00:0:2::4 lookup tunel3
kubectl exec deploy/r13 -- docker exec r13 ip -6 rule add to fd00:0:3::2 lookup tunel4
kubectl exec deploy/r13 -- docker exec r13 ip -6 rule add to fd00:0:3::3 lookup tunel5
kubectl exec deploy/r13 -- docker exec r13 ip -6 rule add to fd00:0:3::4 lookup tunel6