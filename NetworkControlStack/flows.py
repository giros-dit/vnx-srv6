#!/usr/bin/env python3
import json
import sys
import os
import time
import re
import boto3
import argparse
import threading
import contextlib
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

class DistributedLock:
    """
    Implementa un lock distribuido usando S3 como backend
    Versión simplificada para flows.py
    """
    def __init__(self, lock_name, s3_client, bucket, timeout=60):
        self.lock_name = lock_name
        self.s3_client = s3_client
        self.bucket = bucket
        self.timeout = timeout
        self.lock_key = f"locks/{lock_name}.lock"
        self.owner_id = f"flows_{os.getpid()}_{threading.current_thread().ident}_{time.time()}"
        
    def acquire(self, blocking=True, timeout=None):
        """Intenta adquirir el lock distribuido"""
        start_time = time.time()
        actual_timeout = timeout or self.timeout
        
        while True:
            try:
                lock_data = {
                    "owner": self.owner_id,
                    "acquired_at": time.time(),
                    "expires_at": time.time() + self.timeout,
                    "process": "flows.py"
                }
                
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=self.lock_key,
                    Body=json.dumps(lock_data).encode(),
                    Metadata={'owner': self.owner_id},
                    IfNoneMatch='*'
                )
                
                print(f"[flows] Lock '{self.lock_name}' adquirido")
                return True
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                
                if error_code == 'PreconditionFailed':
                    try:
                        obj = self.s3_client.get_object(Bucket=self.bucket, Key=self.lock_key)
                        lock_data = json.loads(obj['Body'].read().decode())
                        
                        if time.time() > lock_data.get('expires_at', 0):
                            print(f"[flows] Lock expirado, intentando renovar")
                            try:
                                self.s3_client.delete_object(Bucket=self.bucket, Key=self.lock_key)
                                continue
                            except:
                                pass
                        
                        if not blocking:
                            return False
                            
                        if timeout and (time.time() - start_time) >= actual_timeout:
                            print(f"[flows] ERROR: Timeout esperando lock '{self.lock_name}'", file=sys.stderr)
                            return False
                            
                        time.sleep(0.1)
                        
                    except ClientError:
                        if not blocking:
                            return False
                        time.sleep(0.1)
                else:
                    print(f"[flows] ERROR: Error adquiriendo lock: {e}", file=sys.stderr)
                    return False
                    
            except Exception as e:
                print(f"[flows] ERROR: Error inesperado adquiriendo lock: {e}", file=sys.stderr)
                return False
    
    def release(self):
        """Libera el lock distribuido"""
        try:
            obj = self.s3_client.get_object(Bucket=self.bucket, Key=self.lock_key)
            lock_data = json.loads(obj['Body'].read().decode())
            
            if lock_data.get('owner') == self.owner_id:
                self.s3_client.delete_object(Bucket=self.bucket, Key=self.lock_key)
                print(f"[flows] Lock '{self.lock_name}' liberado")
                return True
            else:
                print(f"[flows] WARN: Intento de liberar lock sin ser propietario", file=sys.stderr)
                return False
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"[flows] Lock ya no existe")
                return True
            else:
                print(f"[flows] ERROR: Error liberando lock: {e}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"[flows] ERROR: Error inesperado liberando lock: {e}", file=sys.stderr)
            return False

# Lock local para operaciones en memoria
local_lock = threading.RLock()

# Lock distribuido para operaciones de archivo
flows_lock = DistributedLock("flows_operations", s3_client, S3_BUCKET, timeout=60)

@contextlib.contextmanager
def acquire_flows_lock(timeout=30):
    """Context manager para adquirir el lock de flujos de forma segura"""
    local_acquired = local_lock.acquire(timeout=1)
    if not local_acquired:
        raise RuntimeError("No se pudo adquirir el lock local")
    
    try:
        distributed_acquired = flows_lock.acquire(blocking=True, timeout=timeout)
        if not distributed_acquired:
            raise RuntimeError(f"No se pudo adquirir el lock distribuido en {timeout}s")
        
        try:
            yield
        finally:
            flows_lock.release()
    finally:
        local_lock.release()

def read_data():
    """Lee datos de S3 - DEBE ejecutarse dentro del lock"""
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
    """Escribe datos a S3 - DEBE ejecutarse dentro del lock"""
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

def read_flows():
    """Lee flujos - CON lock automático"""
    with acquire_flows_lock(timeout=10):
        data = read_data()
        return data.get("flows", []), data.get("inactive_routers", []), None

def write_flows(flows, inactive_routers=None):
    """Escribe flujos - CON lock automático"""
    with acquire_flows_lock(timeout=10):
        write_data(flows, inactive_routers)

def list_flows():
    """Lista flujos - CON lock automático"""
    with acquire_flows_lock(timeout=10):
        data = read_data()
        print(json.dumps(data, indent=4))

def add_flow(ip, route=None, timestamps=None, api_timestamp=None):
    """Añade flujo - CON lock automático"""
    try:
        with acquire_flows_lock(timeout=30):
            print(f"[flows] Lock adquirido para añadir flujo {ip}")
            
            data = read_data()
            flows = data.get("flows", [])
            inactive = data.get("inactive_routers", [])
            
            # Verificar si ya existe
            for f in flows:
                if f["_id"] == ip:
                    print(f"[flows] ERROR: El flujo {ip} ya existe", file=sys.stderr)
                    return False

            new_flow = {"_id": ip, "version": 1}
            if route:
                new_flow["route"] = route
            
            # Manejar timestamps
            if LOGTS:
                new_flow["timestamps"] = {}
                
                if api_timestamp is not None:
                    new_flow["timestamps"]["ts_api_created"] = api_timestamp
                    print(f"[flows] Timestamp API añadido: ts_api_created = {api_timestamp}")
                
                if timestamps:
                    new_flow["timestamps"].update(timestamps)

            flows.append(new_flow)
            write_data(flows, inactive)
            print(f"[flows] Flujo {ip} añadido exitosamente")
            return True
            
    except RuntimeError as e:
        print(f"[flows] ERROR: No se pudo adquirir lock para añadir {ip}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[flows] ERROR: Excepción añadiendo {ip}: {e}", file=sys.stderr)
        return False

def delete_flow(flow_id, data=None):
    """Elimina flujo - CON lock automático"""
    try:
        with acquire_flows_lock(timeout=30):
            print(f"[flows] Lock adquirido para eliminar flujo {flow_id}")
            
            if data is None:
                data = read_data()

            flows = data.get("flows", [])
            existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
            if existing_flow:
                flows = [f for f in flows if f.get("_id") != flow_id]
                print(f"[flows] Flujo {flow_id} eliminado.")
                write_data(flows, data.get("inactive_routers"))
                return True
            else:
                print(f"[flows] ERROR: Flujo {flow_id} no encontrado.", file=sys.stderr)
                return False
                
    except RuntimeError as e:
        print(f"[flows] ERROR: No se pudo adquirir lock para eliminar {flow_id}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[flows] ERROR: Excepción eliminando {flow_id}: {e}", file=sys.stderr)
        return False

def update_flow(ip, route=None, timestamps=None):
    """Actualiza flujo - CON lock automático"""
    try:
        with acquire_flows_lock(timeout=30):
            print(f"[flows] Lock adquirido para actualizar flujo {ip}")
            
            data = read_data()
            flows = data.get("flows", [])
            inactive = data.get("inactive_routers", [])
            
            for f in flows:
                if f["_id"] == ip:
                    if route is not None:
                        f["route"] = route
                        f["version"] = f.get("version", 1) + 1
                    if timestamps and LOGTS:
                        if "timestamps" not in f:
                            f["timestamps"] = {}
                        f["timestamps"].update(timestamps)

                    write_data(flows, inactive)
                    print(f"[flows] Flujo {ip} actualizado exitosamente")
                    return True

            print(f"[flows] ERROR: Flujo {ip} no encontrado", file=sys.stderr)
            return False
            
    except RuntimeError as e:
        print(f"[flows] ERROR: No se pudo adquirir lock para actualizar {ip}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[flows] ERROR: Excepción actualizando {ip}: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='Gestión de flujos en S3 con cerrojos distribuidos')
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