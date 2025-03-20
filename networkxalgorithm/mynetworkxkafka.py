import json
import time
import threading
import networkx as nx

OCCUPANCY_LIMIT = 0.8
NODE_TIMEOUT = 15
router_state = {}  # Ej. {"r2": {"cost": 0.5, "usage": 0.1, "ts": 1660000000}}


def create_graph():
    G = nx.DiGraph()
    for r in ["r1","r2","r3","r4","ru","rg"]:
        G.add_node(r)
    edges = [
        ("r1", "rg"), ("rg", "r1"),
        ("r3", "rg"), ("rg", "r3"),
        ("r1", "r2"), ("r2", "r1"),
        ("r3", "r4"), ("r4", "r3"),
        ("r2", "ru"), ("ru", "r2"),
        ("r4", "ru"), ("ru", "r4")
    ]
    for e in edges:
        G.add_edge(*e, cost=0.0)
    return G

def read_flows():
    try:
        with open("flows.json", "r") as f:
            return json.load(f)
    except:
        return []

def write_flows(flows):
    with open("flows.json", "w") as f:
        json.dump(flows, f, indent=4)

def remove_inactive_nodes(G, flows):
    now = time.time()
    removed = []
    for r, data in router_state.items():
        if (now - data.get("ts", 0)) > NODE_TIMEOUT and r in G:
            G.remove_node(r)
            removed.append(r)

    # Invalida la ruta de cada flujo que pase por los nodos removidos
    if removed:
        for f in flows:
            if "route" in f and any(r in f["route"] for r in removed):
                f.pop("route", None)
                f["version"] = f.get("version", 1) + 1
    return G, flows

def read_routers_params():
    """
    Lee routers.json y actualiza el estado de uso e incremento de cada router (r1, r2, r3, r4).
    Estructura esperada en routers.json:
    [
      {"router": "r1", "usage": 0.3, "increment": 0.05},
      {"router": "r2", "usage": 0.2, "increment": 0.03},
      ...
    ]
    """
    try:
        with open("routers.json", "r") as f:
            data = json.load(f)
        for item in data:
            r = item.get("router")
            usage = item.get("usage", 0)
            inc = item.get("increment", 0)
            if r:
                router_state[r] = router_state.get(r, {})
                router_state[r]["usage"] = usage
                router_state[r]["increment"] = inc
                # actualizar timestamp para evitar que se vea inactivo
                router_state[r]["ts"] = time.time()
    except:
        pass

def assign_node_costs(G):
    now = time.time()
    for u,v in G.edges():
        if v in router_state and (now - router_state[v].get("ts", 0)) <= NODE_TIMEOUT:
            G[u][v]["cost"] = router_state[v].get("cost", 9999)
        else:
            G[u][v]["cost"] = 9999
    return G

def recalc_routes(G, flows):
    link_usage = {e: 0 for e in G.edges()}
    # Reconstruir ocupación previa
    for f in flows:
        if "route" in f:
            for i in range(len(f["route"])-1):
                link_usage[(f["route"][i], f["route"][i+1])] += f["caudal"]

    # Para cada flujo sin ruta, calcula el camino y revisa si supera 80%
    for f in flows:
        if "route" in f:
            continue
        source, target = "ru", "rg"
        if not (G.has_node(source) and G.has_node(target)):
            continue
        try:
            path = nx.shortest_path(G, source, target, weight="cost")
        except:
            continue
        max_occ = 0
        for i in range(len(path)-1):
            e = (path[i], path[i+1])
            occ = (link_usage[e] + f["caudal"]) / CAPACITY
            max_occ = max(max_occ, occ)
        if max_occ > OCCUPANCY_LIMIT:
            print(f"WARNING: Flow {f.get('_id','???')} supera el 80% de ocupación.")
        # Asignar ruta
        f["route"] = path
        for i in range(len(path)-1):
            link_usage[(path[i], path[i+1])] += f["caudal"]
    return flows

def kafka_listener():
    """Hilo que escucha Kafka y actualiza router_state cada vez que llega un mensaje."""
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda x: json.loads(x.decode("utf-8"))
    )
    for msg in consumer:
        data = msg.value
        router = data.get("node_exporter", "rX").split("-service")[0]
        cost = data.get("ml_pc_dbw", 9999)
        usage = 0
        for m in data.get("ml_metrics", []):
            if m.get("name") == "node_network_router_capacity_occupation":
                usage = m.get("value", 0)
                break
        ts = float(data.get("epoch_timestamp", time.time()))
        router_state[router] = {
            "cost": cost,
            "usage": usage,
            "ts": ts
        }

def network_manager():
    """Hilo que cada cierto tiempo revisa routers inactivos, recalcula rutas y guarda cambios en MinIO."""
    while True:
        time.sleep(5)
        # Agregar la lectura de routers.json para actualizar uso
        read_routers_params()
        
        G = create_graph()
        flows = read_flows()

        G, flows = remove_inactive_nodes(G, flows)
        G = assign_node_costs(G)
        flows = recalc_routes(G, flows)

        write_flows(flows)

def main():
    t1 = threading.Thread(target=kafka_listener, daemon=True)
    t2 = threading.Thread(target=network_manager, daemon=True)
    t1.start()
    t2.start()
    # Mantener el hilo principal vivo
    while True:
        time.sleep(1)

if __name__=="__main__":
    main()
