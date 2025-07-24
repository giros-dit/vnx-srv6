#!/usr/bin/env python3
import json
import sys
import os
import time
import re
import boto3
import argparse
import threading
import queue
import uuid
from botocore.exceptions import ClientError

# Configuración S3 (Minio)
S3_ENDPOINT = os.environ.get('S3_ENDPOINT')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name='local'
)

# Variable de entorno para medida de latencia
LOGTS = os.environ.get('LOGTS', 'false').lower() == 'true'

# Lock local simple para evitar condiciones de carrera dentro del mismo proceso
local_lock = threading.RLock()

# Nueva configuración para cola FIFO
QUEUE_DIR = "/tmp/flows_queue"
PROCESSING_FLAG = "/tmp/flows_processing.lock"

# Crear directorio de cola si no existe
os.makedirs(QUEUE_DIR, exist_ok=True)

# Cola thread-safe para operaciones de escritura
write_queue = queue.Queue()
write_worker_thread = None
write_worker_running = False

def read_data():
    """Lee datos de S3"""
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="flows/")

        print("[flows] Objetos en S3/flows/:")
        for obj in response.get("Contents", []):
            print("  -", obj["Key"], "(LastModified:", obj["LastModified"], ")")

        if 'Contents' not in response or not response['Contents']:
            print("[flows] No se encontró ningún fichero en 'flows/'.")
            return {"flows": []}

        json_files = [obj for obj in response['Contents'] if obj['Key'].endswith('.json') and 'flows_' in obj['Key']]
        if not json_files:
            print("[flows] No hay ficheros JSON válidos.")
            return {"flows": []}

        pattern = re.compile(r'flows_(\d{8}_\d{6})\.json')

        valid_files = [f for f in json_files if pattern.search(f['Key'])]

        if valid_files:
            sorted_files = sorted(valid_files, key=lambda x: pattern.search(x['Key']).group(1), reverse=True)
        else:
            print("[flows] Ningún fichero válido por nombre, usando LastModified.")
            sorted_files = sorted(json_files, key=lambda x: x['LastModified'], reverse=True)

        latest_key = sorted_files[0]['Key']
        print(f"[flows] Leyendo: {latest_key}")
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=latest_key)
        content = obj['Body'].read().decode('utf-8').strip()
        return json.loads(content) if content else {"flows": []}
    except Exception as e:
        print(f"[flows] Error leyendo flows: {e}", file=sys.stderr)
        return {"flows": []}

def write_data(flows, inactive_routers=None):
    """Escribe datos a S3"""
    try:
        data = {
            "flows": flows,
            "inactive_routers": inactive_routers or []
        }
        content = json.dumps(data, indent=4)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_key = f"flows/flows_{timestamp}.json"
        s3_client.put_object(Bucket=S3_BUCKET, Key=file_key, Body=content.encode("utf-8"))
        print(f"[flows] Datos guardados en s3://{S3_BUCKET}/{file_key}")
    except Exception as e:
        print(f"[flows] Error escribiendo: {e}", file=sys.stderr)

def start_write_worker():
    """Inicia el worker thread para procesar la cola de escrituras"""
    global write_worker_thread, write_worker_running
    if write_worker_thread is None or not write_worker_thread.is_alive():
        write_worker_running = True
        write_worker_thread = threading.Thread(target=write_worker, daemon=True)
        write_worker_thread.start()
        print("[flows] Write worker iniciado")

def write_worker():
    """Worker thread que procesa la cola de escrituras de forma serializada"""
    global write_worker_running
    while write_worker_running:
        try:
            # Esperar por una operación de escritura
            operation = write_queue.get(timeout=1.0)
            
            if operation is None:  # Señal de parada
                break
                
            # Procesar la operación con lock completo
            with local_lock:
                try:
                    _process_write_operation(operation)
                except Exception as e:
                    print(f"[flows] ERROR en write worker: {e}", file=sys.stderr)
                finally:
                    write_queue.task_done()
                    
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[flows] ERROR crítico en write worker: {e}", file=sys.stderr)

def _process_write_operation(operation):
    """Procesa una operación de escritura individual"""
    op_type = operation.get('type')
    op_id = operation.get('id')
    
    print(f"[flows] Procesando operación {op_type} ID:{op_id}")
    
    # Leer estado actual
    data = read_data()
    flows = data.get("flows", [])
    inactive = data.get("inactive_routers", [])
    
    if op_type == 'add':
        result = _execute_add_operation(flows, inactive, operation)
    elif op_type == 'delete':
        result = _execute_delete_operation(flows, inactive, operation)
    elif op_type == 'update':
        result = _execute_update_operation(flows, inactive, operation)
    else:
        print(f"[flows] ERROR: Tipo de operación desconocido: {op_type}", file=sys.stderr)
        return
    
    if result['success']:
        write_data(result['flows'], result['inactive'])
        print(f"[flows] Operación {op_type} ID:{op_id} completada exitosamente")
    else:
        print(f"[flows] ERROR: Operación {op_type} ID:{op_id} falló: {result['error']}", file=sys.stderr)

def _execute_add_operation(flows, inactive, operation):
    """Ejecuta operación de añadir flujo"""
    ip = operation['ip']
    route = operation.get('route')
    timestamps = operation.get('timestamps')
    api_timestamp = operation.get('api_timestamp')
    
    # Verificar si ya existe
    for f in flows:
        if f["_id"] == ip:
            return {'success': False, 'error': f"El flujo {ip} ya existe"}
    
    new_flow = {"_id": ip, "version": 1}
    if route:
        new_flow["route"] = route
    
    # Manejar timestamps
    if LOGTS:
        new_flow["timestamps"] = {}
        if api_timestamp is not None:
            new_flow["timestamps"]["ts_api_created"] = api_timestamp
        if timestamps:
            new_flow["timestamps"].update(timestamps)
    
    flows.append(new_flow)
    return {'success': True, 'flows': flows, 'inactive': inactive}

def _execute_delete_operation(flows, inactive, operation):
    """Ejecuta operación de eliminar flujo"""
    flow_id = operation['flow_id']
    
    existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
    if existing_flow:
        flows = [f for f in flows if f.get("_id") != flow_id]
        return {'success': True, 'flows': flows, 'inactive': inactive}
    else:
        return {'success': False, 'error': f"Flujo {flow_id} no encontrado"}

def _execute_update_operation(flows, inactive, operation):
    """Ejecuta operación de actualizar flujo"""
    ip = operation['ip']
    route = operation.get('route')
    timestamps = operation.get('timestamps')
    
    for f in flows:
        if f["_id"] == ip:
            if route is not None:
                f["route"] = route
                f["version"] = f.get("version", 1) + 1
            if timestamps and LOGTS:
                if "timestamps" not in f:
                    f["timestamps"] = {}
                f["timestamps"].update(timestamps)
            return {'success': True, 'flows': flows, 'inactive': inactive}
    
    return {'success': False, 'error': f"Flujo {ip} no encontrado"}

def read_flows():
    """Lee flujos sin lock de escritura (solo lectura rápida)"""
    data = read_data()
    return data.get("flows", []), data.get("inactive_routers", []), None

def write_flows(flows, inactive_routers=None):
    """Mantener compatibilidad - ahora usa la cola"""
    operation = {
        'type': 'write_direct',
        'id': str(uuid.uuid4())[:8],
        'flows': flows,
        'inactive': inactive_routers or []
    }
    write_queue.put(operation)

def list_flows():
    """Lista flujos - solo lectura, sin cola"""
    data = read_data()
    print(json.dumps(data, indent=4))

def add_flow(ip, route=None, timestamps=None, api_timestamp=None):
    """Añade flujo usando cola FIFO"""
    try:
        start_write_worker()  # Asegurar que el worker está ejecutándose
        
        operation = {
            'type': 'add',
            'id': str(uuid.uuid4())[:8],
            'ip': ip,
            'route': route,
            'timestamps': timestamps,
            'api_timestamp': api_timestamp
        }
        
        print(f"[flows] Encolando operación ADD para {ip} (ID: {operation['id']})")
        write_queue.put(operation)
        
        # Esperar a que se procese (con timeout)
        write_queue.join()
        print(f"[flows] Operación ADD para {ip} procesada")
        return True
        
    except Exception as e:
        print(f"[flows] ERROR: Excepción añadiendo {ip}: {e}", file=sys.stderr)
        return False

def delete_flow(flow_id, data=None):
    """Elimina flujo usando cola FIFO"""
    try:
        start_write_worker()
        
        operation = {
            'type': 'delete',
            'id': str(uuid.uuid4())[:8],
            'flow_id': flow_id
        }
        
        print(f"[flows] Encolando operación DELETE para {flow_id} (ID: {operation['id']})")
        write_queue.put(operation)
        
        # Esperar a que se procese
        write_queue.join()
        print(f"[flows] Operación DELETE para {flow_id} procesada")
        return True
        
    except Exception as e:
        print(f"[flows] ERROR: Excepción eliminando {flow_id}: {e}", file=sys.stderr)
        return False

def update_flow(ip, route=None, timestamps=None):
    """Actualiza flujo usando cola FIFO"""
    try:
        start_write_worker()
        
        operation = {
            'type': 'update',
            'id': str(uuid.uuid4())[:8],
            'ip': ip,
            'route': route,
            'timestamps': timestamps
        }
        
        print(f"[flows] Encolando operación UPDATE para {ip} (ID: {operation['id']})")
        write_queue.put(operation)
        
        # Esperar a que se procese
        write_queue.join()
        print(f"[flows] Operación UPDATE para {ip} procesada")
        return True
        
    except Exception as e:
        print(f"[flows] ERROR: Excepción actualizando {ip}: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='Gestión de flujos en S3 (versión simplificada)')
    parser.add_argument('flow_id', nargs='?', help='ID del flujo (dirección IPv6)')
    parser.add_argument('--add', action='store_true', help='Añadir un nuevo flujo')
    parser.add_argument('--delete', action='store_true', help='Eliminar un flujo')
    parser.add_argument('--update', action='store_true', help='Actualizar un flujo existente')
    parser.add_argument('--route', type=str, help='Ruta del flujo en formato JSON array')
    parser.add_argument('--timestamps', type=str, help='Timestamps en formato JSON')
    parser.add_argument('--api-timestamp', type=float, help='Timestamp de cuando se recibió la petición en la API')
    parser.add_argument('--list', action='store_true', help='Listar todos los flujos')

    args = parser.parse_args()

    if args.list:
        try:
            list_flows()
            return
        except Exception as e:
            print(f"[flows] ERROR: Error listando flujos: {e}", file=sys.stderr)
            sys.exit(1)

    if not args.flow_id:
        print("Error: Debe especificar un flow_id", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    options_count = sum([args.add, args.delete, args.update])
    if options_count == 0:
        print("Error: Debe especificar una acción (--add, --delete, o --update)", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
    elif options_count > 1:
        print("Error: Solo puede especificar una acción a la vez", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    route = None
    timestamps = None
    if args.route:
        try:
            route = json.loads(args.route)
        except json.JSONDecodeError:
            print("Error: El formato de --route no es JSON válido", file=sys.stderr)
            sys.exit(1)
    if args.timestamps:
        try:
            timestamps = json.loads(args.timestamps)
        except json.JSONDecodeError:
            print("Error: El formato de --timestamps no es JSON válido", file=sys.stderr)
            sys.exit(1)

    success = False
    if args.add:
        success = add_flow(args.flow_id, route, timestamps, args.api_timestamp)
    elif args.delete:
        success = delete_flow(args.flow_id)
    elif args.update:
        if not args.route:
            print("Error: --update requiere especificar --route", file=sys.stderr)
            parser.print_help()
            sys.exit(1)
        success = update_flow(args.flow_id, route, timestamps)

    if not success:
        print(f"[flows] ERROR: Acción fallida sobre flujo {args.flow_id}", file=sys.stderr)

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()