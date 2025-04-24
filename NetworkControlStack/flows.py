#!/usr/bin/env python3
import json
import sys
import os
import time
import boto3
from botocore.exceptions import ClientError

# Configuración S3 (Minio) mediante variables de entorno
S3_ENDPOINT = os.environ.get('S3_ENDPOINT')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

# Se crea el cliente de S3 con la región "local"
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name='local'
)

def read_flows():
    """
    Descarga el fichero más reciente de la carpeta "flows" en S3 y retorna la lista de flujos.
    """
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="flows/")
        if 'Contents' not in response or len(response['Contents']) == 0:
            print("[flows] read_flows: No se encontró ningún fichero en 'flows'.")
            return []
        # Selecciona el fichero con la fecha de modificación más reciente
        objects = response['Contents']
        latest_obj = max(objects, key=lambda x: x['LastModified'])
        latest_key = latest_obj['Key']
        print(f"[flows] read_flows: Descargando el último fichero: {latest_key}")
        obj_response = s3_client.get_object(Bucket=S3_BUCKET, Key=latest_key)
        content = obj_response["Body"].read().decode("utf-8").strip()
        if not content:
            return []
        data = json.loads(content)
        # Si la estructura contiene la clave "flows", extrae su valor
        if isinstance(data, dict) and "flows" in data:
            flows = data["flows"]
        elif isinstance(data, list):
            flows = data
        else:
            raise ValueError("Invalid flows data: se esperaba una lista o un dict con clave 'flows'.")
        if not isinstance(flows, list) or not all(isinstance(flow, dict) for flow in flows):
            raise ValueError("Invalid flows data: se esperaba una lista de diccionarios.")
        return flows
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "NoSuchKey":
            print("[flows] read_flows: flows.json no existe en S3.")
            return []
        else:
            print(f"[flows] read_flows: Error leyendo flows.json desde S3: {e}")
            raise
    except Exception as e:
        print(f"[flows] read_flows: Error leyendo flows: {e}")
        raise

def write_flows(flows, inactive_routers=None, router_utilization=None):
    """
    Escribe el fichero de flujos en la carpeta "flows" del bucket S3.
    El nombre del fichero incluye la marca de tiempo actual.
    """
    try:
        data = {
            "flows": flows,
            "inactive_routers": inactive_routers or [],
            "router_utilization": router_utilization or {}
        }
        content = json.dumps(data, indent=4)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_key = f"flows/flows_{timestamp}.json"
        s3_client.put_object(Bucket=S3_BUCKET, Key=file_key, Body=content.encode("utf-8"))
        print(f"[flows] write_flows: Fichero guardado en s3://{S3_BUCKET}/{file_key}")
    except Exception as e:
        print(f"[flows] write_flows: Error escribiendo flows.json en S3: {e}")

def main():
    if len(sys.argv) != 2:
        print("Uso: flows.py <id>")
        sys.exit(1)

    flow_id = sys.argv[1]
    try:
        flows = read_flows()

        # Busca si el flujo ya existe
        existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
        if existing_flow:
            # Si existe, se elimina
            flows = [f for f in flows if f.get("_id") != flow_id]
            print(f"Flujo con ID {flow_id} eliminado.")
        else:
            # Si no existe, se añade con versión 1
            new_flow = {"_id": flow_id, "version": 1}
            flows.append(new_flow)
            print(f"Flujo con ID {flow_id} añadido con versión 1.")

        write_flows(flows)
    except Exception as e:
        print(f"[flows] main: Error processing flows: {e}")
        raise

if __name__ == "__main__":
    main()
