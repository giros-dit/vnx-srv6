#!/usr/bin/env python3
import json
import sys
import os
import time
import re
import boto3
import argparse
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

def read_data():
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

        # Filtrar los que coinciden con el patrón
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
        print(f"[flows] Error leyendo flows: {e}")
        return {"flows": []}

def write_data(flows, inactive_routers=None):
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
        print(f"[flows] Error escribiendo: {e}")

# Funciones de compatibilidad para mantener la interfaz existente
def read_flows():
    """Función de compatibilidad que devuelve flows, inactive_routers y filename"""
    data = read_data()
    return data.get("flows", []), data.get("inactive_routers", []), None

def write_flows(flows, inactive_routers=None):
    """Función de compatibilidad que usa write_data"""
    write_data(flows, inactive_routers)

def list_flows():
    """Lista todos los flujos"""
    data = read_data()
    print(json.dumps(data, indent=4))

def add_flow(ip, route=None, timestamps=None):
    """Añade un nuevo flujo"""
    flows, inactive, filename = read_flows()
    
    # Verificar si ya existe
    for f in flows:
        if f["_id"] == ip:
            print(f"ERROR: El flujo {ip} ya existe")
            return False
    
    # Crear nuevo flujo
    new_flow = {"_id": ip, "version": 1}
    
    if route:
        new_flow["route"] = route
    
    # Añadir timestamps si se proporcionan y LOGTS está habilitado
    if timestamps and LOGTS:
        new_flow["timestamps"] = timestamps
    
    flows.append(new_flow)
    write_flows(flows, inactive)
    print(f"Flujo {ip} añadido exitosamente")
    return True

def delete_flow(flow_id, data=None):
    """Elimina un flujo existente"""
    if data is None:
        data = read_data()
    
    flows = data.get("flows", [])
    
    # Buscar y eliminar el flujo
    existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
    if existing_flow:
        flows = [f for f in flows if f.get("_id") != flow_id]
        print(f"[flows] Flujo {flow_id} eliminado.")
        write_data(flows, data.get("inactive_routers"))
        return True
    else:
        print(f"[flows] Error: Flujo {flow_id} no encontrado.")
        return False

def update_flow(ip, route=None, timestamps=None):
    """Actualiza un flujo existente"""
    flows, inactive, filename = read_flows()
    
    for f in flows:
        if f["_id"] == ip:
            if route is not None:
                f["route"] = route
                f["version"] = f.get("version", 1) + 1
            
            # Actualizar timestamps si se proporcionan y LOGTS está habilitado
            if timestamps and LOGTS:
                if "timestamps" not in f:
                    f["timestamps"] = {}
                f["timestamps"].update(timestamps)
            
            write_flows(flows, inactive)
            print(f"Flujo {ip} actualizado exitosamente")
            return True
    
    print(f"ERROR: Flujo {ip} no encontrado")
    return False

def main():
    parser = argparse.ArgumentParser(description='Gestión de flujos en S3')
    parser.add_argument('flow_id', nargs='?', help='ID del flujo (dirección IPv6)')
    parser.add_argument('--add', action='store_true', help='Añadir un nuevo flujo')
    parser.add_argument('--delete', action='store_true', help='Eliminar un flujo')
    parser.add_argument('--update', action='store_true', help='Actualizar un flujo existente')
    parser.add_argument('--route', type=str, help='Ruta del flujo en formato JSON array (ej: \'["ru", "r7", "r6"]\')')
    parser.add_argument('--timestamps', type=str, help='Timestamps en formato JSON')
    parser.add_argument('--list', action='store_true', help='Listar todos los flujos')
    
    args = parser.parse_args()
    
    # Caso especial: listar flujos
    if args.list:
        list_flows()
        return
    
    # Validar argumentos
    if not args.flow_id:
        print("Error: Debe especificar un flow_id")
        parser.print_help()
        sys.exit(1)
    
    # Contar las opciones seleccionadas
    options_count = sum([args.add, args.delete, args.update])
    if options_count == 0:
        print("Error: Debe especificar una acción (--add, --delete, o --update)")
        parser.print_help()
        sys.exit(1)
    elif options_count > 1:
        print("Error: Solo puede especificar una acción a la vez")
        parser.print_help()
        sys.exit(1)
    
    # Procesar argumentos JSON
    route = None
    timestamps = None
    
    if args.route:
        try:
            route = json.loads(args.route)
        except json.JSONDecodeError:
            print("Error: El formato de --route no es JSON válido")
            sys.exit(1)
    
    if args.timestamps:
        try:
            timestamps = json.loads(args.timestamps)
        except json.JSONDecodeError:
            print("Error: El formato de --timestamps no es JSON válido")
            sys.exit(1)
    
    # Ejecutar la acción correspondiente
    success = False
    
    if args.add:
        success = add_flow(args.flow_id, route, timestamps)
    elif args.delete:
        success = delete_flow(args.flow_id)
    elif args.update:
        if not args.route:
            print("Error: --update requiere especificar --route")
            parser.print_help()
            sys.exit(1)
        success = update_flow(args.flow_id, route, timestamps)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()