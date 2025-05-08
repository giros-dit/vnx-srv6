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

# Configuración MinIO/S3 desde env
S3_ENDPOINT   = os.environ.get('S3_ENDPOINT')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET     = os.environ.get('S3_BUCKET')

# Si usamos el valor real de energía (True) o fijamos a 0.1 (False)
ENERGYAWARE = os.environ.get('ENERGYAWARE', 'true').lower() == 'true'

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
            initial = {"flows": [], "inactive_routers": [], "router_utilization": {}}
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
            return []
        latest = max(resp['Contents'], key=lambda o: o['LastModified'])['Key']
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=latest)
        flows_data = json.loads(obj['Body'].read().decode())
        return flows_data.get("flows", flows_data) if isinstance(flows_data, dict) else flows_data
    except Exception as e:
        print(f"[pce][ERROR] read_flows: {e}")
        return []

def write_flows(flows, inactive):
    payload = {"flows": flows, "inactive_routers": inactive}
    ts = time.strftime("%Y%m%d_%H%M%S")
    key = f"flows/flows_{ts}.json"
    s3_client.put_object(Bucket=S3_BUCKET, Key=key,
                         Body=json.dumps(payload, indent=4).encode())
    print(f"[pce] write_flows: guardado {key}")

def remove_inactive_nodes(G, flows):
    now = time.time()
    removed, modified = [], False
    with state_lock:
        for r, d in list(router_state.items()):
            if now - d.get("ts", 0) > NODE_TIMEOUT and r in G:
                G.remove_node(r)
                removed.append(r)
                modified = True
    if removed:
        print(f"[pce] remove_inactive_nodes: routers caídos {removed}")
        for f in flows:
            if "route" in f and any(r in f["route"] for r in removed):
                f.pop("route", None)
                f["version"] = f.get("version", 1) + 1
                modified = True
    return G, flows, removed, modified

def assign_node_costs(G):
    now = time.time()
    with state_lock:
        for u, v in G.edges():
            energy = router_state.get(v, {}).get("energy", 9999)
            cost = energy if ENERGYAWARE else 0.1
            if v in router_state and (now - router_state[v].get("ts", 0)) <= NODE_TIMEOUT:
                G[u][v]["cost"] = cost
            else:
                G[u][v]["cost"] = 9999
    return G

def choose_destination(dest_ip):
    addr = ipaddress.IPv6Address(dest_ip.split('/')[0])
    if addr in ipaddress.IPv6Network('fd00:0:2::/64'):
        return 'rg1'
    if addr in ipaddress.IPv6Network('fd00:0:3::/64'):
        return 'rg2'
    return 'rg1'

def recalc_routes(G, flows, removed):
    modified = False

    # 1) Mostrar coste de todos los enlaces de la red
    print("[pce] Costes de todos los enlaces en la red:")
    for u, v, data in G.edges(data=True):
        cost = data.get("cost", None)
        print(f"  {u} -> {v}: {cost}")

    # 2) Para cada flujo pendiente o con ruta invalidada
    for f in flows:
        route = f.get("route")
        if route and not any(r in route for r in removed):
            continue

        source = "ru"
        target = choose_destination(f["_id"])
        print(f"[pce][DEBUG] Intentando ruta de {source} a {target} para flujo {f['_id']}")

        if not (G.has_node(source) and G.has_node(target)):
            print(f"[pce][DEBUG] Nodo faltante: source {'OK' if G.has_node(source) else 'MISSING'}, "
                  f"target {'OK' if G.has_node(target) else 'MISSING'}")
            continue

        # Excluir nodos saturados
        with state_lock:
            excluded     = [n for n,d in router_state.items() if d.get("usage",0) >= OCCUPANCY_LIMIT]
            excluded_max = [n for n,d in router_state.items() if d.get("usage",0) >= ROUTER_LIMIT]
        G2 = G.copy(); G2.remove_nodes_from(excluded)
        G3 = G.copy(); G3.remove_nodes_from(excluded_max)

        try:
            path = nx.shortest_path(G2, source, target, weight="cost")
        except Exception:
            print("[pce] No se encontró ruta en subgrafo, intentando con G completo...")
            try:
                path = nx.shortest_path(G3, source, target, weight="cost")
            except Exception:
                print("[pce] WARNING: No se encontró ruta.")
                continue

        # 3) Calcular costes por salto y total
        costs = [G[u][v]["cost"] for u, v in zip(path, path[1:])]
        total_cost = sum(costs)
        print(f"[pce] recalc_routes: Assigned route {path} a flujo {f['_id']} "
              f"con costes por salto {costs} (total={total_cost})")

        # 4) Guardar ruta y disparar src.py
        f["route"] = path
        modified = True

        cmd = [
            "python3", "/app/src.py",
            f"{f['_id']}", str(f.get("version", 1)), json.dumps(path)
        ]
        print(f"[pce] Llamada a src.py: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"[src stdout]\n{result.stdout}")
        if result.stderr:
            print(f"[src stderr]\n{result.stderr}")

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
        energy = usage = None
        ts = None
        for m in data.get("output_ml_metrics", []):
            if m.get("name") == "node_network_power_consumption_variation_rate_occupation":
                energy = float(m.get("value", 0)) if ENERGYAWARE else 0.1
                break
        for m in data.get("input_ml_metrics", []):
            if m.get("name") == "node_network_router_capacity_occupation":
                usage = float(m.get("value", 0)) / 100.0
                break
        try:
            ts = float(data.get("epoch_timestamp", 0))
        except:
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
    start_kafka_consumers()
    while True:
        time.sleep(5)
        G = create_graph()
        flows = read_flows()
        G, flows, removed, m1 = remove_inactive_nodes(G, flows)
        G = assign_node_costs(G)
        flows, m2 = recalc_routes(G, flows, removed)
        if m1 or m2:
            write_flows(flows, removed)

if __name__ == "__main__":
    main()
