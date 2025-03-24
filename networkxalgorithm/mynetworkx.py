import json
import time
import networkx as nx

OCCUPANCY_LIMIT = 0.8
ROUTER_LIMIT = 0.95
NODE_TIMEOUT = 15
router_state = {}  

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

    if removed:
        print(f"[mynetworkx] remove_inactive_nodes: Removed inactive routers: {removed}")
        for f in flows:
            if "route" in f and any(r in f["route"] for r in removed):
                f.pop("route", None)
                f["version"] = f.get("version", 1) + 1
    return G, flows, removed

def read_routers_params():
    """
    Lee routers.json y actualiza uso de cada router.
    Estructura esperada:
    [
      {"router": "r1", "usage": 0.3}
    ]
    """
    try:
        with open("routers.json", "r") as f:
            data = json.load(f)
        for item in data:
            r = item.get("router")
            usage = item.get("usage", 0)
            energy = item.get("energy", 700)
            if r:
                router_state[r] = router_state.get(r, {})
                router_state[r]["usage"] = usage
                router_state[r]["energy"] = energy
                router_state[r]["ts"] = time.time()
                print(f"[mynetworkx] read_routers_params: Router {r} usage={usage}, energy={energy}")
    except:
        pass

def assign_node_costs(G):
    now = time.time()
    for u,v in G.edges():
        if v in router_state and (now - router_state[v].get("ts", 0)) <= NODE_TIMEOUT:
            G[u][v]["cost"] = router_state[v].get("energy", 9999)
        else:
            G[u][v]["cost"] = 9999
        print(f"[mynetworkx] assign_node_costs: Cost from {u} to {v} = {G[u][v]['cost']}")
    return G

def recalc_routes(G, flows, removed=None):
    for f in flows:
        route = f.get("route")
        # Solo recalcula si no existe ruta o la ruta contiene un nodo caído
        if route and removed and not any(r in route for r in removed):
            continue
        source, target = "ru", "rg"
        if not (G.has_node(source) and G.has_node(target)):
            continue

        # Crear subgrafo G2 excluyendo nodos que superan el 80% de uso
        excluded = [n for n, data in router_state.items() if data.get("usage", 0) >= OCCUPANCY_LIMIT]
        excluded_max = [n for n, data in router_state.items() if data.get("usage", 0) >= ROUTER_LIMIT]
        G2 = G.copy()
        G2.remove_nodes_from(excluded)
        G3 = G.copy()
        G3.remove_nodes_from(excluded_max)

        try:
            # Intentar ruta evitando nodos saturados
            path = nx.shortest_path(G2, source, target, weight="cost")
        except:
            print("No se encontró ruta en el subgrafo, intentando con G completo...")
            try:
                # Si no existe ruta en G2, usamos el grafo completo con nodos sin estar al limite
                path = nx.shortest_path(G3, source, target, weight="cost")
            except:
                print("WARNING: No se encontró ruta.")
                continue

        max_usage = max(router_state.get(node, {}).get("usage", 0.0) for node in path)
        if max_usage > OCCUPANCY_LIMIT:
            print(f"[mynetworkx] recalc_routes: Flow {f.get('_id','???')} usage above {OCCUPANCY_LIMIT}")
        print(f"[mynetworkx] recalc_routes: Assigned route {path} to flow {f.get('_id')}")
        f["route"] = path
    return flows

def main():
    while True:
        time.sleep(5)
        read_routers_params()

        G = create_graph()
        flows = read_flows()

        G, flows, removed = remove_inactive_nodes(G, flows)
        G = assign_node_costs(G)
        flows = recalc_routes(G, flows, removed)

        write_flows(flows)

if __name__ == "__main__":
    main()