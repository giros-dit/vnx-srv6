#!/usr/bin/env python3
import json
import time
import os
import threading
import networkx as nx
import re
import subprocess
import boto3
from kafka import KafkaConsumer
from botocore.exceptions import ClientError

# Parámetros globales
OCCUPANCY_LIMIT = 0.8
ROUTER_LIMIT = 0.95
NODE_TIMEOUT = 15  # Si el timestamp es mayor a 15 seg, se considera que el router está caído.
router_state = {}
state_lock = threading.Lock()  # Lock para proteger router_state

# Configuración S3 (Minio) mediante variables de entorno
S3_ENDPOINT = os.environ.get('S3_ENDPOINT')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

# Se crea un cliente global para S3/Minio (región "local")
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name='local'
)

# Función para verificar que el bucket existe (solo verificación)
def ensure_bucket_exists(bucket_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        print(f"Error: El bucket {bucket_name} no existe o no se puede acceder: {e}")

ensure_bucket_exists(S3_BUCKET)

# Función para asegurar que existe al menos un fichero en la carpeta "flows"
def ensure_flows_folder_exists():
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="flows/")
        if 'Contents' not in response or len(response['Contents']) == 0:
            print("[mynetworkx] ensure_flows_folder_exists: No se encontró ningún fichero en 'flows/', creando fichero inicial.")
            initial_data = {
                "flows": [
                    {
                        "_id": "1",
                        "version": 1
                    }
                ],
                "inactive_routers": [],
                "router_utilization": {}
            }
            content = json.dumps(initial_data, indent=4)
            # Se guarda un fichero inicial en "flows/"
            s3_client.put_object(Bucket=S3_BUCKET, Key="flows/flows_initial.json", Body=content.encode("utf-8"))
        else:
            print("[mynetworkx] ensure_flows_folder_exists: Existe al menos un fichero en la carpeta 'flows/'.")
    except Exception as e:
        print(f"[mynetworkx] ensure_flows_folder_exists: Error al verificar o crear el fichero inicial: {e}")

ensure_flows_folder_exists()

def create_graph():
    # Se carga localmente el final_output.json; si lo deseas en S3, debes adaptar esta función
    with open("final_output.json") as f:
        data = json.load(f)
    G = nx.DiGraph()
    for node in data["graph"]["nodes"]:
        G.add_node(node)
    for edge in data["graph"]["edges"]:
        G.add_edge(edge["source"], edge["target"], cost=edge["cost"])
    return G

def read_flows():
    try:
        # Listamos los ficheros en la carpeta "flows" del bucket
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="flows/")
        if 'Contents' not in response or len(response['Contents']) == 0:
            print("[mynetworkx] read_flows: No se encontró ningún fichero en la carpeta 'flows'.")
            return []
        
        # Obtenemos el objeto con la fecha de modificación más reciente
        objects = response['Contents']
        latest_obj = max(objects, key=lambda x: x['LastModified'])
        latest_key = latest_obj['Key']
        print(f"[mynetworkx] read_flows: Descargando el último fichero: {latest_key}")
        
        obj_response = s3_client.get_object(Bucket=S3_BUCKET, Key=latest_key)
        content = obj_response['Body'].read().decode('utf-8')
        data = json.loads(content)
        
        if isinstance(data, dict) and "flows" in data:
            return data["flows"]
        elif isinstance(data, list):
            return data
        else:
            return []
    except Exception as e:
        print(f"[mynetworkx] read_flows: Error leyendo el último fichero de flows desde S3: {e}")
        return []

def write_flows(flows, inactive_routers):
    data_to_write = {
        "flows": flows,
        "inactive_routers": inactive_routers,
    }
    content = json.dumps(data_to_write, indent=4)
    # Se genera un nombre de fichero con la marca de tiempo actual en la carpeta "flows"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    file_key = f"flows/flows_{timestamp}.json"
    try:
        s3_client.put_object(Bucket=S3_BUCKET, Key=file_key, Body=content.encode("utf-8"))
        print(f"[mynetworkx] write_flows: Fichero guardado en s3://{S3_BUCKET}/{file_key}")
    except Exception as e:
        print(f"[mynetworkx] write_flows: Error escribiendo flows.json en S3: {e}")

def remove_inactive_nodes(G, flows):
    now = time.time()
    removed = []
    with state_lock:
        for r, data in router_state.items():
            if (now - data.get("ts", 0)) > NODE_TIMEOUT and r in G:
                G.remove_node(r)
                removed.append(r)
    if removed:
        print(f"[mynetworkx] remove_inactive_nodes: Removed inactive routers: {removed}")
        for f in flows:
            if "route" in f and any(r in f["route"] for r in removed):
                f.pop("route", None)
                f["version"] = f.get("version", 1) + 1
    return G, flows, removed

def assign_node_costs(G):
    now = time.time()
    with state_lock:
        for u, v in G.edges():
            if v in router_state and (now - router_state[v].get("ts", 0)) <= NODE_TIMEOUT:
                G[u][v]["cost"] = router_state[v].get("energy", 9999)
            else:
                G[u][v]["cost"] = 9999
    return G

def recalc_routes(G, flows, removed):
    for f in flows:
        route = f.get("route")
        if route and not any(r in route for r in removed):
            continue
        source, target = "ru", "rg"
        if not (G.has_node(source) and G.has_node(target)):
            continue

        with state_lock:
            excluded = [n for n, data in router_state.items() if data.get("usage", 0) >= OCCUPANCY_LIMIT]
            excluded_max = [n for n, data in router_state.items() if data.get("usage", 0) >= ROUTER_LIMIT]
        G2 = G.copy()
        G2.remove_nodes_from(excluded)
        G3 = G.copy()
        G3.remove_nodes_from(excluded_max)

        try:
            path = nx.shortest_path(G2, source, target, weight="cost")
        except Exception:
            print("No se encontró ruta en el subgrafo, intentando con G completo...")
            try:
                path = nx.shortest_path(G3, source, target, weight="cost")
                if path:
                    print(f"[mynetworkx] recalc_routes: Flow {f.get('_id', '???')} usage above {OCCUPANCY_LIMIT}")
            except Exception:
                print("WARNING: No se encontró ruta.")
                continue

        print(f"[mynetworkx] recalc_routes: Assigned route {path} to flow {f.get('_id')}")
        f["route"] = path

        try:
            print(f"Ejecutando tunnelmaker para el flujo {f.get('_id')} con versión {f.get('version', 1)}, ruta: {json.dumps(path)}")
            cmd = [
                "python3",
                "tunnelmaker.py",
                str(f.get("_id")),
                str(f.get("version", 1)),
                json.dumps(path)
            ]
            print("Ejecutando comando:", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True)
            print(result.stdout)
        except Exception as e:
            print(f"Error al llamar a tunnelmaker: {e}")
    return flows

def routing_algorithm_loop():
    while True:
        time.sleep(5)
        G = create_graph()
        flows = read_flows()  # Carga la última versión de flows desde S3
        G, flows, removed = remove_inactive_nodes(G, flows)
        G = assign_node_costs(G)
        flows = recalc_routes(G, flows, removed)
        write_flows(flows, removed)  # Guarda la versión actualizada en S3

def kafka_consumer_thread(router_id):
    topic = f"ML_{router_id}"
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=['kafka-service:9092'],
        auto_offset_reset='latest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    print(f"Conectado al topic {topic}")
    for message in consumer:
        data = message.value
        energy = None
        usage = None
        for metric in data.get("output_ml_metrics", []):
            if metric.get("name") == "node_network_power_consumption_variation_rate_occupation":
                try:
                    energy = float(metric.get("value", 0))
                except (ValueError, TypeError):
                    energy = 0
                break
        for metric in data.get("input_ml_metrics", []):
            if metric.get("name") == "node_network_router_capacity_occupation":
                try:
                    usage = float(metric.get("value", 0)) / 100.0
                except (ValueError, TypeError):
                    usage = 0
                break
        if energy is not None and usage is not None:
            with state_lock:
                router_state[router_id] = {
                    "energy": energy,
                    "usage": usage,
                    "ts": time.time()
                }

def start_kafka_consumers():
    with open("final_output.json", "r") as f:
        data = json.load(f)
    all_nodes = data["graph"]["nodes"]
    routers = [node for node in all_nodes if re.match(r"^r\d$", node)]
    threads = []
    for r in routers:
        t = threading.Thread(target=kafka_consumer_thread, args=(r,))
        t.daemon = True
        t.start()
        threads.append(t)
    return threads

def main():
    start_kafka_consumers()  # Inicia consumidores de Kafka para cada router
    routing_algorithm_loop()   # Ejecuta el algoritmo de rutas en el hilo principal

if __name__ == "__main__":
    main()
