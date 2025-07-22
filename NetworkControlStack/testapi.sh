#!/usr/bin/env bash

# Configuración base
BASE_URL="http://138.4.21.11:32500"  # Ajustar según tu configuración
# BASE_URL="http://your-service-ip:5000"  # Para Kubernetes

echo "=== PROBANDO CONTROLADOR DE FLUJOS ==="

# 1. Health Check
echo -e "\n🏥 1. Health Check"
curl -X GET "$BASE_URL/health" -w "\nStatus: %{http_code}\n"

# 2. Ver estado inicial de los flujos
echo -e "\n📋 2. Listar flujos iniciales"
curl -X GET "$BASE_URL/flows" \
  -H "Accept: application/json" \
  -w "\nStatus: %{http_code}\n" | jq .

# 3. Crear flujo sin ruta (requiere recálculo automático)
echo -e "\n➕ 3. Crear flujo SIN ruta (2001:db8::1)"
curl -X POST "$BASE_URL/flows/2001%3Adb8%3A%3A1" \
  -H "Content-Type: application/json" \
  -d '{}' \
  -w "\nStatus: %{http_code}\n"

# 4. Crear flujo con ruta específica
echo -e "\n➕ 4. Crear flujo CON ruta (2001:db8::2)"
curl -X POST "$BASE_URL/flows/2001%3Adb8%3A%3A2" \
  -H "Content-Type: application/json" \
  -d '{
    "route": ["r1", "r3", "r5"]
  }' \
  -w "\nStatus: %{http_code}\n"

# 5. Crear otro flujo con ruta diferente
echo -e "\n➕ 5. Crear flujo CON ruta alternativa (2001:db8::3)"
curl -X POST "$BASE_URL/flows/2001%3Adb8%3A%3A3" \
  -H "Content-Type: application/json" \
  -d '{
    "route": ["r2", "r4", "r6"]
  }' \
  -w "\nStatus: %{http_code}\n"

# 6. Intentar crear flujo duplicado (debe fallar)
echo -e "\n❌ 6. Intentar crear flujo duplicado (debe fallar con 409)"
curl -X POST "$BASE_URL/flows/2001%3Adb8%3A%3A1" \
  -H "Content-Type: application/json" \
  -d '{
    "route": ["r7", "r8"]
  }' \
  -w "\nStatus: %{http_code}\n"

# 7. Ver todos los flujos después de las creaciones
echo -e "\n📋 7. Listar todos los flujos después de creaciones"
curl -X GET "$BASE_URL/flows" \
  -H "Accept: application/json" \
  -w "\nStatus: %{http_code}\n" | jq .

# 8. Actualizar ruta de un flujo existente
echo -e "\n🔄 8. Actualizar ruta del flujo 2001:db8::2"
curl -X PUT "$BASE_URL/flows/2001%3Adb8%3A%3A2" \
  -H "Content-Type: application/json" \
  -d '{
    "route": ["r1", "r4", "r7", "r9"]
  }' \
  -w "\nStatus: %{http_code}\n"

# 9. Intentar actualizar flujo inexistente
echo -e "\n❌ 9. Intentar actualizar flujo inexistente (debe fallar con 404)"
curl -X PUT "$BASE_URL/flows/2001%3Adb8%3A%3A999" \
  -H "Content-Type: application/json" \
  -d '{
    "route": ["r1", "r2"]
  }' \
  -w "\nStatus: %{http_code}\n"

# 10. Ver flujos después de la actualización
echo -e "\n📋 10. Listar flujos después de actualización"
curl -X GET "$BASE_URL/flows" \
  -H "Accept: application/json" \
  -w "\nStatus: %{http_code}\n" | jq .

# 11. Eliminar un flujo
echo -e "\n🗑️ 11. Eliminar flujo 2001:db8::1"
curl -X DELETE "$BASE_URL/flows/2001%3Adb8%3A%3A1" \
  -w "\nStatus: %{http_code}\n"

# 12. Intentar eliminar flujo inexistente
echo -e "\n❌ 12. Intentar eliminar flujo inexistente (debe retornar 404)"
curl -X DELETE "$BASE_URL/flows/2001%3Adb8%3A%3A999" \
  -w "\nStatus: %{http_code}\n"

# 13. Ver flujos finales
echo -e "\n📋 13. Listar flujos después de eliminaciones"
curl -X GET "$BASE_URL/flows" \
  -H "Accept: application/json" \
  -w "\nStatus: %{http_code}\n" | jq .

# 14. Verificar estado de los locks (debugging)
echo -e "\n🔒 14. Verificar estado de locks"
curl -X GET "$BASE_URL/locks/status" \
  -H "Accept: application/json" \
  -w "\nStatus: %{http_code}\n" | jq .

# 15. Limpiar - eliminar flujos restantes
echo -e "\n🧹 15. Limpiar flujos restantes"
curl -X DELETE "$BASE_URL/flows/2001%3Adb8%3A%3A2" \
  -w "\nStatus: %{http_code}\n"
curl -X DELETE "$BASE_URL/flows/2001%3Adb8%3A%3A3" \
  -w "\nStatus: %{http_code}\n"

# 16. Verificar limpieza final
echo -e "\n📋 16. Verificar limpieza final"
curl -X GET "$BASE_URL/flows" \
  -H "Accept: application/json" \
  -w "\nStatus: %{http_code}\n" | jq .

echo -e "\n✅ PRUEBAS COMPLETADAS"