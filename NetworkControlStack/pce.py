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
    "nodes_restored": 0,
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
            initial = {"flows": [], "tables": {}, "inactive_routers": []}
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
            return [], {}, []
        latest_key = max(resp['Contents'], key=lambda o: o['LastModified'])['Key']
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=latest_key)
        flows_data = json.loads(obj['Body'].read().decode())
        if isinstance(flows_data, dict):
            return (flows_data.get("flows", []),
                    flows_data.get("tables", {}),
                    flows_data.get("inactive_routers", []))
        else:
            return flows_data, {}, []
    except Exception as e:
        print(f"[pce][ERROR] read_flows: {e}")
        return [], {}, []


def write_flows(flows, tables, inactive):
    payload = {"flows": flows,
               "tables": tables,
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
    print(f"[pce] Buscando tabla para ruta: {route_str}")
    
    for tid, info in tables.items():
        table_route_str = "->".join(info.get("route", []))
        print(f"[pce] Comparando con tabla {tid}: {table_route_str}")
        if table_route_str == route_str:
            print(f"[pce] Encontrada tabla existente {tid} para ruta {path}")
            return tid, False  # False indica que no es nueva
    
    # Crear nueva tabla con ID numérico (evitando valores reservados: 0, 253, 254, 255)
    # Extraer número de tabla si existe o crear un nuevo ID
    table_ids = [int(tid[1:]) for tid in tables.keys() if tid.startswith('t') and tid[1:].isdigit()]
    next_id = max(table_ids, default=0) + 1
    
    # Asegurar que no usamos valores reservados del sistema
    reserved_ids = {0, 253, 254, 255}
    while next_id in reserved_ids:
        next_id += 1
    
    tid = f"t{next_id}"
    tables[tid] = {"route": path}
    metrics["tables_created"] += 1
    print(f"[pce] Nueva tabla {tid} creada para ruta {path}")
    return tid, True  # True indica que es una nueva tabla


def remove_inactive_nodes(G, flows, inactive_routers, tables):
    now = time.time()
    removed, modified = [], False
    
    # Primero verificar si nodos inactivos ahora están activos
    active_nodes = []
    with state_lock:
        for r in inactive_routers:
            if r in router_state:
                d = router_state[r]
                age = now - d.get("ts", 0)
                if age <= NODE_TIMEOUT:  # El nodo ha vuelto a estar activo
                    active_nodes.append(r)
                    metrics["nodes_restored"] += 1
                    print(f"[pce] El nodo {r} ha vuelto a estar activo")
        
        # Luego verificar si hay nuevos nodos inactivos
        for r, d in list(router_state.items()):
            age = now - d.get("ts", 0)
            if age > NODE_TIMEOUT and r in G and r not in inactive_routers:
                G.remove_node(r)
                removed.append(r)
                modified = True
                metrics["nodes_removed"] += 1
    
    # Actualizar lista de nodos inactivos
    for node in active_nodes:
        if node in inactive_routers:
            inactive_routers.remove(node)
            modified = True
    
    for node in removed:
        if node not in inactive_routers:
            inactive_routers.append(node)
    
    # Si hay nodos que se han caído, revisar solo los flujos que usan esos nodos
    if removed:
        removed_nodes = set(removed)
        print(f"[pce] Nodos caídos: {removed_nodes}")
        
        for f in flows:
            # Revisar si el flujo tiene tabla y la ruta pasa por nodos caídos
            if "table" in f and f["table"] in tables:
                route = tables[f["table"]].get("route", [])
                # Solo actualizar si la ruta pasa por algún nodo caído
                if any(node in removed_nodes for node in route):
                    print(f"[pce] Flujo {f.get('_id', '???')} afectado: ruta {route} pasa por nodos caídos")
                    #f.pop("route", None)  # Eliminar route si existe (redundancia) ya no tinen campo route
                    increment_version(f)
                    modified = True
                    metrics["flows_updated"] += 1
                else:
                    print(f"[pce] Flujo {f.get('_id', '???')} NO afectado: ruta {route} no pasa por nodos caídos")
    
    return G, flows, inactive_routers, modified


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
        return 'rg'
    if addr in ipaddress.IPv6Network('fd00:0:3::/64'):
        return 'rc'
    raise ValueError(f"Dirección IP de destino {dest_ip} no pertenece a ninguna red conocida")


def recalc_routes(G, flows, tables, inactive_routers):
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
                print(f"[pce] Flujo {f.get('_id', '???')} necesita recálculo: ruta inválida {current_route}")
        else:
            needs_recalc = True
            print(f"[pce] Flujo {f.get('_id', '???')} necesita recálculo: sin tabla o tabla inexistente")
        
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
        
        # Flag para indicar si estamos usando la ruta con nodos de ocupación entre OCCUPANCY_LIMIT y ROUTER_LIMIT
        using_high_occupancy = False
        
        # Intentar primero con el subgrafo más restrictivo (excluye nodos ≥ OCCUPANCY_LIMIT)
        try:
            path = nx.shortest_path(G2, source, target, weight="cost")
        except nx.NetworkXNoPath:
            print(f"[pce] No se encontró ruta en subgrafo con límite {OCCUPANCY_LIMIT}, intentando con límite {ROUTER_LIMIT}...")
            # Intentar con el segundo subgrafo menos restrictivo (excluye nodos ≥ ROUTER_LIMIT)
            try:
                path = nx.shortest_path(G3, source, target, weight="cost")
                if path:
                    using_high_occupancy = True
                    print(f"[pce] AVISO: Flujo {f.get('_id', '???')} usa ruta con nodos de ocupación entre {OCCUPANCY_LIMIT} y {ROUTER_LIMIT}")
            except nx.NetworkXNoPath:
                print(f"[pce] WARNING: No se encontró ruta para flujo {f.get('_id', '???')}")
                continue
        
        # Debug de ruta seleccionada solo si está habilitado
        if DEBUG_COSTS:
            costs = [G[u][v]["cost"] for u, v in zip(path, path[1:])]
            print(f"[pce] Ruta seleccionada: {path}")
            print(f"[pce] Costes enlace a enlace: {costs}")
        
        # Obtener o crear tabla para esta ruta
        tid, is_new_table = get_or_create_table(tables, path)
        
        print(f"[pce] Flujo {f.get('_id', '???')}: ruta calculada {path}")
        print(f"[pce] Flujo {f.get('_id', '???')}: tabla asignada {tid} (nueva: {is_new_table})")
        
        # Si el flujo ya tenía una tabla diferente, imprimir información
        if current_table and current_table != tid:
            print(f"[pce] Flujo {f.get('_id', '???')}: cambiando de tabla {current_table} a {tid}")
        
        # Extraer ID numérico de la tabla para pasar a src.py
        table_id = int(tid[1:]) if tid.startswith('t') and tid[1:].isdigit() else 0
        
        # Obtener la tabla anterior si existe
        old_table_id = None
        if current_table and current_table in tables and current_table != tid:
            if current_table.startswith('t') and current_table[1:].isdigit():
                old_table_id = int(current_table[1:])
        
        # Actualizar flujo: solo tabla, eliminar route redundante
        f.update({"table": tid})
        ### f.pop("route", None)  # Eliminar route si existe ya no
        increment_version(f)
        modified = True
        metrics["routes_recalculated"] += 1
        metrics["flows_updated"] += 1
        
        # Construir el comando para src.py con la información adicional
        cmd = [
            "python3", "/app/src.py",
            f"{f['_id']}", json.dumps(path),
            "--table-id", str(table_id)
        ]
        
        # Agregar flag si es tabla nueva
        if is_new_table:
            cmd.append("--new-table")
        
        # Agregar tabla antigua a eliminar si corresponde
        if old_table_id is not None:
            cmd.extend(["--delete-old", str(old_table_id)])
        
        # Agregar flag si estamos usando rutas con alta ocupación
        if using_high_occupancy:
            cmd.append("--high-occupancy")
        
        print(f"[pce] Ejecutando comando: {' '.join(cmd)}")
        subprocess.run(cmd, check=False)
    
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
            ts = float(data.get("epoch_timestamp"))
        except Exception:
            ts = None

        if energy is not None or usage is not None or ts is not None:
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
        flows, tables, inactive_routers = read_flows()
        G, flows, inactive_routers, m1 = remove_inactive_nodes(G, flows, inactive_routers, tables)
        G = assign_node_costs(G)
        flows, m2 = recalc_routes(G, flows, tables, inactive_routers)
        if m1 or m2:
            write_flows(flows, tables, inactive_routers)

if __name__ == "__main__":
    main()