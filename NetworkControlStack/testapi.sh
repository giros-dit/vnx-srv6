#!/usr/bin/env bash

BASE="http://138.4.21.11:32500/flows"
IPS=(b2 b3 b4 b5 b6 b7 b8 b9)

logfile="delete_flows_$(date +%Y%m%d_%H%M%S).log"
echo "Inicio de script en $(date)" | tee "$logfile"

for ip in "${IPS[@]}"; do
  fullip="fd00:0:2::b${ip:1}"
  enc=$(printf '%s' "$fullip" | sed -e 's/:/%3A/g')
  echo -e "\n[$(date '+%Y-%m-%d %H:%M:%S')] Eliminando $fullip ..." | tee -a "$logfile"

  # Ejecutar DELETE y capturar resultado
  resp=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X DELETE "$BASE/$enc")
  body=$(printf '%s\n' "$resp" | sed '/^HTTP_CODE:/d')
  code=$(printf '%s\n' "$resp" | awk -F'HTTP_CODE:' '/HTTP_CODE/ {print $2}')

  echo "$body" | tee -a "$logfile"

  if [[ "$code" -ge 200 && "$code" -lt 300 ]]; then
    echo "✅ Éxito ($code): $fullip" | tee -a "$logfile"
  else
    echo "❌ Error ($code): $fullip" | tee -a "$logfile"
    echo "---- detalle respuesta ----" | tee -a "$logfile"
    echo "$body" | tee -a "$logfile"
    echo "---------------------------" | tee -a "$logfile"
  fi
done

echo -e "\nFinalizado en $(date)" | tee -a "$logfile"
echo "Revisa $logfile para detalles."
