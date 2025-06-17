#!/usr/bin/env python3
import json
import sys
import os
import time
import re
import boto3
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
            return {"flows": [], "tables": {}}

        json_files = [obj for obj in response['Contents'] if obj['Key'].endswith('.json') and 'flows_' in obj['Key']]
        if not json_files:
            print("[flows] No hay ficheros JSON válidos.")
            return {"flows": [], "tables": {}}

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



def write_data(flows, tables, inactive_routers=None, router_utilization=None):
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

def delete_table_and_flows(table_id, data):
    table_id = str(table_id)
    flows = data.get("flows", [])
    tables = data.get("tables", {})

    if table_id not in tables:
        print(f"[flows] Tabla {table_id} no existe.")
        return flows, tables

    new_flows = [f for f in flows if str(f.get("table")) != table_id]
    del tables[table_id]
    print(f"[flows] Tabla {table_id} y flujos asociados eliminados.")
    return new_flows, tables

def delete_or_toggle_flow(flow_id, data):
    flows = data.get("flows", [])
    tables = data.get("tables", {})

    existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)
    if existing_flow:
        table_id = str(existing_flow.get("table"))
        flows = [f for f in flows if f.get("_id") != flow_id]
        print(f"[flows] Flujo {flow_id} eliminado.")
        if table_id and not any(str(f.get("table")) == table_id for f in flows):
            if table_id in tables:
                del tables[table_id]
                print(f"[flows] Tabla {table_id} eliminada al no quedar flujos.")
    else:
        print(f"[flows] Añadiendo nuevo flujo {flow_id} con versión 1.")
        flows.append({"_id": flow_id, "version": 1})

    return flows, tables

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "f":
        data = read_data()
        print(json.dumps(data, indent=4))
        return

    if len(sys.argv) == 2:
        mode = 'flow'
        arg = sys.argv[1]
    elif len(sys.argv) == 3 and sys.argv[1] == 't':
        mode = 'table'
        arg = sys.argv[2]
    else:
        print("Uso:\n  python3 flows.py <flow_id>\n  python3 flows.py t <table_id>\n  python3 flows.py f")
        sys.exit(1)

    data = read_data()

    if mode == 'flow':
        flows, tables = delete_or_toggle_flow(arg, data)
    else:
        flows, tables = delete_table_and_flows(arg, data)

    write_data(flows, tables)

if __name__ == "__main__":
    main()