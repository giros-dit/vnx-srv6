import json
import time
import networkx as nx

OCCUPANCY_LIMIT = 0.8
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

def remove_inactive_nodes(G, flows, inactive_routers):
    removed = []
    for r in inactive_routers:
        if r in G:
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

def recalc_routes_if_router_down(G, flows, removed=None):
    # Recalculate route only if existing route contains a removed router
    for f in flows:
        route = f.get("route")
        if route and removed and any(r in route for r in removed):
            source, target = "ru", "rg"
            if not (G.has_node(source) and G.has_node(target)):
                continue

            # Crear subgrafo G2 excluyendo nodos que superan el 80% de uso
            excluded = [n for n, data in router_state.items() if data.get("usage", 0) >= OCCUPANCY_LIMIT]
            G2 = G.copy()
            G2.remove_nodes_from(excluded)

            try:
                # Intentar ruta evitando nodos saturados
                path = nx.shortest_path(G2, source, target, weight="cost")
            except:
                print("No se encontró ruta sin usar nodos debajo del 80%, uso por encima del 80%...")
                try:
                    # Si no existe ruta en G2, usamos el grafo completo
                    path = nx.shortest_path(G, source, target, weight="cost")
                except:
                    print("No hay camino posible.")
                    continue

            max_usage = max(router_state.get(node, {}).get("usage", 0.0) for node in path)
            if max_usage > OCCUPANCY_LIMIT:
                print(f"[mynetworkx] recalc_routes: Flow {f.get('_id','???')} usage above {OCCUPANCY_LIMIT}")
            print(f"[mynetworkx] recalc_routes: Assigned route {path} to flow {f.get('_id')}")
            f["route"] = path
    return flows

def assign_routes_if_missing(G, flows):
    # Assign route only if none is assigned
    for f in flows:
        route = f.get("route")
        if not route:
            source, target = "ru", "rg"
            if not (G.has_node(source) and G.has_node(target)):
                continue

            # Crear subgrafo G2 excluyendo nodos que superan el 80% de uso
            excluded = [n for n, data in router_state.items() if data.get("usage", 0) >= OCCUPANCY_LIMIT]
            G2 = G.copy()
            G2.remove_nodes_from(excluded)

            try:
                # Intentar ruta evitando nodos saturados
                path = nx.shortest_path(G2, source, target, weight="cost")
            except:
                print("No se encontró ruta en el subgrafo, intentando con G completo...")
                try:
                    # Si no existe ruta en G2, usamos el grafo completo
                    path = nx.shortest_path(G, source, target, weight="cost")
                except:
                    print("No hay camino posible.")
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
        flows = read_flows()

        now = time.time()
        inactive_routers = [r for r, data in router_state.items() if (now - data.get("ts", 0)) > NODE_TIMEOUT]
        for r, data in router_state.items():
            ts_diff = now - data.get("ts", 0)
            print(f"[mynetworkx] Router {r} ts difference: {ts_diff}")
        missing_routes = any(not f.get("route") for f in flows)

        if not inactive_routers and not missing_routes:
            print("[No flows missing routes and no inactive routers, skipping iteration.")
            continue

        G = create_graph()
        G, flows, removed = remove_inactive_nodes(G, flows, inactive_routers)
        G = assign_node_costs(G)
        if removed:
            flows = recalc_routes_if_router_down(G, flows, removed)
        flows = assign_routes_if_missing(G, flows)
        write_flows(flows)

if __name__ == "__main__":
    main()