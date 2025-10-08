#!/bin/bash
# Script to capture packets on router r9

ROUTER="r9"
INTERFACE="eth1"
DURATION="60"
OUTPUT_FILE="/tmp/r9_capture.pcap"

echo "Starting packet capture on ${ROUTER}:${INTERFACE} for ${DURATION} seconds..."

kubectl exec deploy/${ROUTER} -- docker exec ${ROUTER} \
  timeout ${DURATION} tcpdump -i ${INTERFACE} -w ${OUTPUT_FILE} -v

echo "Capture complete. Copying file from pod..."

kubectl exec deploy/${ROUTER} -- docker cp ${ROUTER}:${OUTPUT_FILE} /tmp/
kubectl cp ${ROUTER}:/tmp/$(basename ${OUTPUT_FILE}) ./r9_capture_$(date +%Y%m%d_%H%M%S).pcap

echo "Packet capture saved locally"
