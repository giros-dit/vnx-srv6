#!/bin/bash

# Lista de routers
routers=(
  r1
  r2
  r3
  r4
  r5
  r6
  r7
  rc
  rcpd
  rg
  rgnb
  ru
  rupf
)

echo "Checking internal Docker containers inside each router Pod..."

for router in "${routers[@]}"; do
  echo "--------------------------------------"
  echo "Router: $router"

  # Ejecuta docker ps dentro del Pod usando kubectl exec al Deployment
  output=$(kubectl exec deploy/$router -- docker ps --format "{{.Names}} {{.Status}}" 2>/dev/null)

  if [ $? -ne 0 ]; then
    echo "❌ Error connecting to deploy/$router or docker not available"
    continue
  fi

  # Verifica si el contenedor con nombre exacto existe y está Up
  if echo "$output" | grep -q "^$router.*Up"; then
    echo "✅ Internal container '$router' is Up"
  else
    echo "⚠️  Internal container '$router' is NOT Up"
    echo "$output"
  fi
done
