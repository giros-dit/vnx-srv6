#!/bin/bash

# Script para limpiar reglas IPv6 y tablas de routing personalizadas
# Se ejecuta dentro del contenedor 'ru' usando kubectl

set -e  # Salir si hay algún error

echo "=== Limpieza de reglas IPv6 y tablas de routing en contenedor 'ru' ==="

# Función para ejecutar comandos en el contenedor
exec_in_container() {
    kubectl exec -it deploy/ru -- docker exec -it ru sh -c "$1"
}

# Función para mostrar el estado actual
show_current_state() {
    echo "Estado actual de las reglas IPv6:"
    exec_in_container "ip -6 rule show"
    echo
    echo "Tablas de routing actuales:"
    exec_in_container "cat /etc/iproute2/rt_tables"
    echo
}

# Mostrar estado inicial
echo "ANTES de la limpieza:"
show_current_state

# 1. Eliminar todas las reglas IPv6 entre 'local' (0) y 'main' (32766)
echo "Eliminando reglas IPv6 intermedias..."

# Crear script temporal dentro del contenedor para eliminar reglas
CLEANUP_SCRIPT='
#!/bin/sh
ip -6 rule show | grep -E "^[0-9]+:" | while read line; do
    priority=$(echo "$line" | cut -d: -f1)
    if [ "$priority" -gt 0 ] && [ "$priority" -lt 32766 ]; then
        echo "Eliminando regla con prioridad $priority"
        ip -6 rule del prio "$priority" 2>/dev/null || echo "No se pudo eliminar regla $priority"
    fi
done
'

exec_in_container "echo '$CLEANUP_SCRIPT' > /tmp/cleanup_rules.sh && chmod +x /tmp/cleanup_rules.sh && /tmp/cleanup_rules.sh"

# 2. Hacer backup del archivo rt_tables
echo "Creando backup de /etc/iproute2/rt_tables..."
exec_in_container "cp /etc/iproute2/rt_tables /etc/iproute2/rt_tables.backup.\$(date +%Y%m%d_%H%M%S)"

# 3. Limpiar el archivo rt_tables, manteniendo solo las líneas del sistema
echo "Limpiando /etc/iproute2/rt_tables..."

# Crear nuevo contenido para rt_tables
RT_TABLES_CONTENT='#
# reserved values
#
255	local
254	main
253	default
0	unspec
#
# local
#'

exec_in_container "echo '$RT_TABLES_CONTENT' > /etc/iproute2/rt_tables"

# 4. Eliminar las tablas de routing personalizadas que puedan existir
echo "Eliminando tablas de routing personalizadas..."

# Script para limpiar tablas
FLUSH_TABLES_SCRIPT='
#!/bin/sh
# Lista de posibles tablas personalizadas a eliminar
CUSTOM_TABLES="tunnel1 tunnel2 tunnel3 tunnel4 tunnel5"

for table in $CUSTOM_TABLES; do
    echo "Intentando limpiar tabla: $table"
    ip route flush table "$table" 2>/dev/null && echo "Tabla $table vaciada" || echo "Tabla $table no existe o ya está vacía"
done

# También eliminar por número de tabla (1, 2, 3, etc.)
for i in 1 2 3 4 5 6 7 8 9 10; do
    ip route flush table "$i" 2>/dev/null && echo "Tabla $i vaciada" || true
done
'

exec_in_container "echo '$FLUSH_TABLES_SCRIPT' > /tmp/flush_tables.sh && chmod +x /tmp/flush_tables.sh && /tmp/flush_tables.sh"

# 5. Limpiar archivos temporales
echo "Limpiando archivos temporales..."
exec_in_container "rm -f /tmp/cleanup_rules.sh /tmp/flush_tables.sh"

echo
echo "DESPUÉS de la limpieza:"
show_current_state

echo "=== Limpieza completada ==="
echo "Se ha creado un backup en /etc/iproute2/rt_tables.backup.* dentro del contenedor"
echo "Para aplicar completamente los cambios, se recomienda reiniciar el contenedor."