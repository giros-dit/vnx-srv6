import json
import time
import os
import threading
import networkx as nx
import re
from kafka import KafkaConsumer

# Parámetros globales
OCCUPANCY_LIMIT = 0.8
ROUTER_LIMIT = 0.95
NODE_TIMEOUT = 15  # Si el timestamp es mayor a 15 seg, el router se considera caído.
router_state = {}
state_lock = threading.Lock()  # Lock para proteger router_state

# ----------------- ALGORITMO DE RUTAS -----------------

def create_graph():
    with open("networkx_graph.json") as f:
        data = json.load(f)
    G = nx.DiGraph()
    for node in data["nodes"]:
        G.add_node(node)
    for edge in data["edges"]:
        G.add_edge(edge["source"], edge["target"], cost=edge["cost"])
    return G

def read_flows():
    try:
        with open("flows.json", "r") as f:
            data = json.load(f)
            if isinstance(data, dict) and "flows" in data:
                return data["flows"]
            elif isinstance(data, list):
                return data
            else:
                return []
    except Exception as e:
        print(f"[mynetworkx] read_flows: Error reading flows.json: {e}")
        return []

def write_flows(flows, inactive_routers, router_utilization):
    data_to_write = {
        "flows": flows,
        "inactive_routers": inactive_routers,
        "router_utilization": router_utilization
    }
    with open("flows.json", "w") as f:
        json.dump(data_to_write, f, indent=4)

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

def read_routers_params():
    # Ahora el estado se actualiza vía Kafka, por lo que simplemente se muestra el estado actual.
    with state_lock:
        print("[mynetworkx] read_routers_params: Estado actual de los routers:")
        for r, data in router_state.items():
            print(f"  Router {r}: usage={data.get('usage')}, energy={data.get('energy')}, ts={data.get('ts')}")

def assign_node_costs(G):
    now = time.time()
    with state_lock:
        for u, v in G.edges():
            if v in router_state and (now - router_state[v].get("ts", 0)) <= NODE_TIMEOUT:
                G[u][v]["cost"] = router_state[v].get("energy", 9999)
            else:
                G[u][v]["cost"] = 9999
            print(f"[mynetworkx] assign_node_costs: Cost from {u} to {v} = {G[u][v]['cost']}")
    return G

def recalc_routes(G, flows, removed):
    for f in flows:
        route = f.get("route")
        # Si ya existe una ruta y ninguno de los routers caídos está en ella, se conserva.
        if route and not any(r in route for r in removed):
            continue
        source, target = "ru", "rg"
        if not (G.has_node(source) and G.has_node(target)):
            continue

        # Se generan subgrafos excluyendo routers con utilización alta.
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
    return flows

def routing_algorithm_loop():
    while True:
        time.sleep(5)
        read_routers_params()  # Imprime el estado actual de los routers (actualizado vía Kafka)
        G = create_graph()
        flows = read_flows()
        G, flows, removed = remove_inactive_nodes(G, flows)
        G = assign_node_costs(G)
        flows = recalc_routes(G, flows, removed)
        with state_lock:
            router_utilization = {r: router_state[r].get("usage", 0.0) for r in router_state}
        write_flows(flows, removed, router_utilization)

# ----------------- CONSUMIDORES DE KAFKA -----------------

def kafka_consumer_thread(router_id):
    topic = f"ML_{router_id}"
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=['kafka-service.across-tc32.svc.cluster.local:9092'],
        auto_offset_reset='latest',
        group_id=f"group_{router_id}",
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
            print(f"Router {router_id} actualizado: energy={energy}, usage={usage}, ts={router_state[router_id]['ts']}")

def start_kafka_consumers():
    # Extraer nodos desde networkx_graph.json y filtrar aquellos que se llamen "rX" con X único.
    with open("networkx_graph.json", "r") as f:
        data = json.load(f)
    all_nodes = data.get("nodes", [])
    routers = [node for node in all_nodes if re.match(r"^r\d$", node)]
    threads = []
    for r in routers:
        t = threading.Thread(target=kafka_consumer_thread, args=(r,))
        t.daemon = True
        t.start()
        threads.append(t)
    return threads

# ----------------- INTEGRACIÓN -----------------

def main():
    start_kafka_consumers()  # Inicia las hebras consumidoras de Kafka
    routing_algorithm_loop() # Ejecuta el algoritmo de rutas en el hilo principal

if __name__ == "__main__":
    main()
