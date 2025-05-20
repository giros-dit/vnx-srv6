#!/usr/bin/env python3
import json
import time
import os
import threading
import networkx as nx
import re
import subprocess
import boto3
import ipaddress
from kafka import KafkaConsumer
from botocore.exceptions import ClientError
from botocore.config import Config

# Parámetros globales
OCCUPANCY_LIMIT = 0.8
ROUTER_LIMIT = 0.95
NODE_TIMEOUT = 15  # Segundos tras los cuales un router se considera caído
router_state = {}
state_lock = threading.Lock()

# Configuración MinIO/S3 desde variables de entorno
S3_ENDPOINT = os.environ.get('S3_ENDPOINT')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

# Modo energía: True usa valor real, False fija a 0.1
ENERGYAWARE = os.environ.get('ENERGYAWARE', 'true').lower() == 'true'

# Flag para debug de costes
DEBUG_COSTS = os.environ.get('DEBUG_COSTS', 'false').lower() == 'true'

# Configurar boto3 para path-style (no virtual host)
s3_cfg = Config(
    signature_version='s3v4',
    s3={'addressing_style': 'path'}
)

print(f"[pce] Inicializando S3 client -> endpoint={S3_ENDPOINT!r}, bucket={S3_BUCKET!r}")
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=s3_cfg,
    region_name='local'
)

# Métricas de rendimiento
metrics = {
    "routes_recalculated": 0,
    "tables_created": 0,
    "nodes_removed": 0,
    "flows_updated": 0
}


def ensure_bucket_exists(bucket_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"[pce] Bucket '{bucket_name}' OK.")
    except ClientError as e:
        print(f"[pce][ERROR] El bucket {bucket_name} no existe o no se puede acceder: {e}")

ensure_bucket_exists(S3_BUCKET)


def ensure_flows_folder_exists():
    try:
        resp = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="flows/")
        if 'Contents' not in resp or not resp['Contents']:
            initial = {"flows": [], "tables": {}, "router_utilization": {}, "inactive_routers": []}
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key="flows/flows_initial.json",
                Body=json.dumps(initial, indent=4).encode()
            )
            print("[pce] flows/ creado e inicializado.")
        else:
            print("[pce] Ya existe al menos un fichero en flows/.")
    except Exception as e:
        print(f"[pce][ERROR] ensure_flows_folder_exists: {e}")

ensure_flows_folder_exists()


def create_graph():
    with open("networkinfo.json") as f:
        data = json.load(f)
    G = nx.DiGraph()
    for n in data["graph"]["nodes"]:
        G.add_node(n)
    for e in data["graph"]["edges"]:
        G.add_edge(e["source"], e["target"], cost=e["cost"])
    return G




def read_flows():
    try:
        resp = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="flows/")
        if 'Contents' not in resp or not resp['Contents']:
            return [], {}, {}
        latest_key = max(resp['Contents'], key=lambda o: o['LastModified'])['Key']
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=latest_key)
        flows_data = json.loads(obj['Body'].read().decode())
        if isinstance(flows_data, dict):
            return (flows_data.get("flows", []),
                    flows_data.get("tables", {}),
                    flows_data.get("router_utilization", {}))
        else:
            return flows_data, {}, {}
    except Exception as e:
        print(f"[pce][ERROR] read_flows: {e}")
        return [], {}, {}


def write_flows(flows, tables, router_util, inactive):
    payload = {"flows": flows,
               "tables": tables,
               "router_utilization": router_util,
               "inactive_routers": inactive}
    ts = time.strftime("%Y%m%d_%H%M%S")
    key = f"flows/flows_{ts}.json"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(payload, indent=4).encode()
        )
        print(f"[pce] write_flows: guardado {key}")
        print(f"[pce] Métricas: {metrics}")
    except Exception as e:
        print(f"[pce][ERROR] write_flows: {e}")


def increment_version(flow):
    """Incrementa la versión de un flujo de manera consistente"""
    flow["version"] = flow.get("version", 1) + 1
    return flow["version"]


def is_route_valid(G, route):
    """Verifica si una ruta sigue siendo válida en el grafo actual"""
    if not route or len(route) < 2:
        return False
    for i in range(len(route) - 1):
        if not G.has_edge(route[i], route[i + 1]):
            return False
    return True


def get_or_create_table(tables, path):
    """Obtiene una tabla existente por ruta o crea una nueva"""
    # Buscar tabla existente por ruta
    route_str = "->".join(path)
    for tid, info in tables.items():
        if "->".join(info.get("route", [])) == route_str:
            return tid
    
    # Crear nueva tabla
    tid = f"t{len(tables)+1}"
    tables[tid] = {"route": path}
    metrics["tables_created"] += 1
    print(f"[pce] Nueva tabla {tid} creada para ruta {path}")
    return tid


def remove_inactive_nodes(G, flows):
    now = time.time()
    removed, modified = [], False
    with state_lock:
        for r, d in list(router_state.items()):
            age = now - d.get("ts", 0)
            if age > NODE_TIMEOUT and r in G:
                G.remove_node(r)
                removed.append(r)
                modified = True
                metrics["nodes_removed"] += 1
    if removed:
        for f in flows:
            # Revisar si el flujo tiene tabla y la ruta de esa tabla está afectada
            if "table" in f:
                # La ruta se obtiene de la tabla, no del flujo directamente
                f.pop("route", None)  # Eliminar route si existe (redundancia)
                increment_version(f)
                modified = True
                metrics["flows_updated"] += 1
    return G, flows, removed, modified


def assign_node_costs(G):
    now = time.time()
    with state_lock:
        for u, v in G.edges():
            entry = router_state.get(v)
            if entry and (now - entry.get("ts", 0)) <= NODE_TIMEOUT:
                cost = entry.get("energy") if ENERGYAWARE else 0.1
            else:
                cost = 9999
            G[u][v]["cost"] = cost
    return G


def choose_destination(dest_ip):
    addr = ipaddress.IPv6Address(dest_ip.split('/')[0])
    if addr in ipaddress.IPv6Network('fd00:0:2::/64'):
        return 'rg1'
    if addr in ipaddress.IPv6Network('fd00:0:3::/64'):
        return 'rg2'
    return 'rg1'


def recalc_routes(G, flows, tables, removed):
    modified = False
    
    # Debug de costes solo si está habilitado
    if DEBUG_COSTS:
        print("[pce] Costes de todos los enlaces en la red:")
        for u, v, data in G.edges(data=True):
            print(f"  {u} -> {v}: {data.get('cost')}")
    
    for f in flows:
        # Verificar si necesita recálculo
        current_table = f.get("table")
        needs_recalc = False
        
        if current_table and current_table in tables:
            current_route = tables[current_table].get("route", [])
            if not is_route_valid(G, current_route):
                needs_recalc = True
        else:
            needs_recalc = True
        
        if not needs_recalc:
            continue
        
        source, target = "ru", choose_destination(f["_id"])
        if not (G.has_node(source) and G.has_node(target)):
            continue
        
        # Lógica de umbrales para evitar nodos congestionados
        with state_lock:
            excluded = [n for n, data in router_state.items() 
                       if data.get("usage", 0) >= OCCUPANCY_LIMIT]
            excluded_max = [n for n, data in router_state.items() 
                           if data.get("usage", 0) >= ROUTER_LIMIT]
        
        # Crear subgrafos excluyendo nodos congestionados
        G2 = G.copy()
        G2.remove_nodes_from(excluded)
        
        G3 = G.copy()
        G3.remove_nodes_from(excluded_max)
        
        # Intentar primero con el subgrafo más restrictivo (excluye nodos ≥ OCCUPANCY_LIMIT)
        try:
            path = nx.shortest_path(G2, source, target, weight="cost")
        except nx.NetworkXNoPath:
            print(f"[pce] No se encontró ruta en subgrafo con límite {OCCUPANCY_LIMIT}, intentando con límite {ROUTER_LIMIT}...")
            # Intentar con el segundo subgrafo menos restrictivo (excluye nodos ≥ ROUTER_LIMIT)
            try:
                path = nx.shortest_path(G3, source, target, weight="cost")
                if path:
                    print(f"[pce] Flujo {f.get('_id', '???')} usa ruta con nodos de ocupación entre {OCCUPANCY_LIMIT} y {ROUTER_LIMIT}")
            except nx.NetworkXNoPath:
                print(f"[pce] WARNING: No se encontró ruta para flujo {f.get('_id', '???')}")
                continue
        
        # Debug de ruta seleccionada solo si está habilitado
        if DEBUG_COSTS:
            costs = [G[u][v]["cost"] for u, v in zip(path, path[1:])]
            print(f"[pce] Ruta seleccionada: {path}")
            print(f"[pce] Costes enlace a enlace: {costs}")
        
        # Obtener o crear tabla para esta ruta
        tid = get_or_create_table(tables, path)
        
        # Actualizar flujo: solo tabla, eliminar route redundante
        f.update({"table": tid})
        f.pop("route", None)  # Eliminar route si existe
        increment_version(f)
        modified = True
        metrics["routes_recalculated"] += 1
        metrics["flows_updated"] += 1
        
        subprocess.run([
            "python3", "/app/src.py",
            f"{f['_id']}", str(f.get("version", 1)), json.dumps(path)
        ], check=False)
    
    return flows, modified


def kafka_consumer_thread(router_id):
    topic = f"ML_{router_id}"
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=['kafka-service:9092'],
        auto_offset_reset='latest',
        value_deserializer=lambda m: json.loads(m.decode())
    )
    for msg in consumer:
        data = msg.value
        energy = None
        raw_out = next((m for m in data.get("output_ml_metrics", [])
                        if m.get("name") == "node_network_power_consumption_variation_rate_occupation"), None)
        if raw_out:
            val = raw_out.get("value")
            if isinstance(val, list) and val:
                val = val[0]
            try:
                energy = float(val) if ENERGYAWARE else 0.1
            except Exception:
                energy = None
        usage = None
        raw_in = next((m for m in data.get("input_ml_metrics", [])
                       if m.get("name") == "node_network_router_capacity_occupation"), None)
        if raw_in:
            val = raw_in.get("value")
            if isinstance(val, list) and val:
                val = val[0]
            try:
                usage = float(val) / 100.0
            except Exception:
                usage = None
        try:
            ts = float(data.get("epoch_timestamp", time.time()))
        except Exception:
            ts = time.time()
        if energy is not None and usage is not None:
            with state_lock:
                router_state[router_id] = {"energy": energy, "usage": usage, "ts": ts}


def start_kafka_consumers():
    with open("networkinfo.json") as f:
        nodes = json.load(f)["graph"]["nodes"]
    for n in nodes:
        if re.match(r"^r\d+$", n):
            t = threading.Thread(target=kafka_consumer_thread, args=(n,))
            t.daemon = True
            t.start()


def main():
    print("[pce] Iniciando PCE con optimizaciones...")
    print(f"[pce] ENERGYAWARE: {ENERGYAWARE}")
    print(f"[pce] DEBUG_COSTS: {DEBUG_COSTS}")
    print(f"[pce] OCCUPANCY_LIMIT: {OCCUPANCY_LIMIT}")
    print(f"[pce] ROUTER_LIMIT: {ROUTER_LIMIT}")
    
    start_kafka_consumers()
    while True:
        time.sleep(5)
        G = create_graph()
        flows, tables, router_util = read_flows()
        G, flows, removed, m1 = remove_inactive_nodes(G, flows)
        G = assign_node_costs(G)
        flows, m2 = recalc_routes(G, flows, tables, removed)
        if m1 or m2:
            write_flows(flows, tables, router_util, removed)

if __name__ == "__main__":
    main()