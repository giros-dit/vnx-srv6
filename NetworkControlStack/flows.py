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

def add_flow(flow_id, route=None, data=None):
    flows = data.get("flows", [])
    
    # Verificar si el flujo ya existe
    existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
    if existing_flow:
        print(f"[flows] Error: El flujo {flow_id} ya existe. Use --update para modificarlo.")
        return flows
    
    # Crear nuevo flujo
    new_flow = {"_id": flow_id, "version": 1}
    
    # Procesar la ruta
    if route:
        try:
            # Intentar parsear como JSON
            route_array = json.loads(route)
            if not isinstance(route_array, list):
                print(f"[flows] Error: La ruta debe ser un array JSON válido.")
                return flows
            new_flow["route"] = route_array
            route_msg = f" con ruta {route_array}"
        except json.JSONDecodeError:
            print(f"[flows] Error: La ruta debe ser un JSON válido. Ejemplo: '[\"ru\", \"r7\", \"r6\"]'")
            return flows
    else:
        # Sin ruta, no añadir el campo route
        route_msg = " sin ruta"
    
    flows.append(new_flow)
    print(f"[flows] Flujo {flow_id} añadido{route_msg} con versión 1.")
    
    return flows

def delete_flow(flow_id, data):
    flows = data.get("flows", [])
    
    # Buscar y eliminar el flujo
    existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
    if existing_flow:
        flows = [f for f in flows if f.get("_id") != flow_id]
        print(f"[flows] Flujo {flow_id} eliminado.")
    else:
        print(f"[flows] Error: Flujo {flow_id} no encontrado.")
    
    return flows

def update_flow(flow_id, route, data):
    flows = data.get("flows", [])
    
    # Buscar el flujo existente
    existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
    if not existing_flow:
        print(f"[flows] Error: Flujo {flow_id} no encontrado. Use --add para crearlo.")
        return flows
    
    # Parsear la nueva ruta
    try:
        new_route = json.loads(route)
        if not isinstance(new_route, list):
            print(f"[flows] Error: La ruta debe ser un array JSON válido.")
            return flows
    except json.JSONDecodeError:
        print(f"[flows] Error: La ruta debe ser un JSON válido. Ejemplo: '[\"ru\", \"r7\", \"r6\"]'")
        return flows
    
    # Verificar si la ruta ha cambiado
    current_route = existing_flow.get("route", [])
    if current_route == new_route:
        print(f"[flows] La ruta del flujo {flow_id} no ha cambiado.")
        return flows
    
    # Actualizar la ruta y incrementar la versión
    existing_flow["route"] = new_route
    existing_flow["version"] = existing_flow.get("version", 1) + 1
    
    print(f"[flows] Flujo {flow_id} actualizado con nueva ruta {new_route}. Nueva versión: {existing_flow['version']}")
    
    return flows

def main():
    parser = argparse.ArgumentParser(description='Gestión de flujos en S3')
    parser.add_argument('flow_id', nargs='?', help='ID del flujo')
    parser.add_argument('--add', action='store_true', help='Añadir un nuevo flujo')
    parser.add_argument('--delete', action='store_true', help='Eliminar un flujo')
    parser.add_argument('--update', action='store_true', help='Actualizar un flujo existente')
    parser.add_argument('--route', type=str, help='Ruta del flujo en formato JSON array (ej: \'["ru", "r7", "r6"]\')')
    parser.add_argument('--list', action='store_true', help='Listar todos los flujos')
    
    args = parser.parse_args()
    
    # Caso especial: listar flujos
    if args.list:
        data = read_data()
        print(json.dumps(data, indent=4))
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
    
    # Validar que solo --update requiere --route obligatoriamente
    if args.update and not args.route:
        print("Error: --update requiere especificar --route")
        parser.print_help()
        sys.exit(1)
    
    # Leer datos actuales
    data = read_data()
    
    # Ejecutar la acción correspondiente
    if args.add:
        flows = add_flow(args.flow_id, args.route, data)
    elif args.delete:
        flows = delete_flow(args.flow_id, data)
    elif args.update:
        flows = update_flow(args.flow_id, args.route, data)
    
    # Guardar los cambios
    write_data(flows, data.get("inactive_routers"))

if __name__ == "__main__":
    main()