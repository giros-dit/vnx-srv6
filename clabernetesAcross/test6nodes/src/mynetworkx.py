import networkx as nx
from pymongo import MongoClient
import sys
import os
import subprocess
import json
import time

CAPACITY = 100  # Mbps
MAX_ATTEMPTS = 3

def create_graph():
    G = nx.DiGraph()
    nodes = ["r1", "r2", "r3", "r4", "ru", "rg"]
    for node in nodes:
        G.add_node(node)
    
    edges = [
        ("r1", "rg"), ("rg", "r1"),
        ("r3", "rg"), ("rg", "r3"),
        ("r1", "r2"), ("r2", "r1"),
        ("r3", "r4"), ("r4", "r3"),
        ("r2", "ru"), ("ru", "r2"),
        ("r4", "ru"), ("ru", "r4")
    ]
    
    for edge in edges:
        G.add_edge(*edge, cost=0, capacity=CAPACITY)
    
    return G

def fetch_energy():
    client = MongoClient("mongodb://mongo:27017/")
    db = client.across
    collection = db.energy
    energy_consumption = {}
    timestamp = {}
    
    for router in ["r1", "r2", "r3", "r4", "ru", "rg"]:
        document = collection.find_one({"router": router})
        energy_consumption[router] = document.get("consumption", 0) if document else 0
        timestamp[router] = document.get("timestamp", 0) if document else 0
    
    maxtimestamp = max(timestamp.values())
    for router in energy_consumption:
        if timestamp[router] < (maxtimestamp - 15):
            energy_consumption[router] = 0  # Apagar router temporalmente
    
    return energy_consumption

def assign_costs(G, energy_consumption):
    for u, v in G.edges():
        G[u][v]["cost"] = energy_consumption.get(v, 0)
    return G

def fetch_flows():
    client = MongoClient("mongodb://mongo:27017/")
    db = client.across
    collection = db.flows
    return list(collection.find())

def router_checkup(G, energy_consumption, flows):
    affected_flows = []
    # Solo se eliminan r1, r2, r3 y r4, se mantienen "ru" y "rg" pues son críticos.
    for router in ["r1", "r2", "r3", "r4"]:
        if energy_consumption.get(router, 0) == 0:
            for flow in flows:
                if "route" in flow and router in flow["route"]:
                    affected_flows.append(flow["_id"])
            if router in G.nodes():
                G.remove_node(router)
    return G, affected_flows

def update_flow_versions(affected_flows):
    client = MongoClient("mongodb://mongo:27017/")
    db = client.across
    collection = db.flows
    for flow_id in affected_flows:
        collection.update_one({"_id": flow_id}, {"$inc": {"version": 1}, "$unset": {"route": ""}})

def check_capacity(G, flows):
    link_usage = {edge: 0 for edge in G.edges()}
    for flow in flows:
        if "route" in flow:
            for i in range(len(flow["route"]) - 1):
                edge = (flow["route"][i], flow["route"][i+1])
                if edge in link_usage:
                    link_usage[edge] += flow["caudal"]
    for (u, v), usage in link_usage.items():
        if usage > CAPACITY:
            print(f"ALERT: Link {u}-{v} is 100% full, redirecting to least energy-consuming path.")
            G[u][v]["cost"] += 10000
    return G, link_usage

def assign_routes(G, flows, link_usage):
    client = MongoClient("mongodb://mongo:27017/")
    db = client.across
    collection = db.flows

    for flow in flows:
        flow_id = flow["_id"]
        flow_caudal = flow["caudal"]
        # Si el flujo ya tenía una ruta, quitar su contribución para recalcular
        if "route" in flow:
            for i in range(len(flow["route"]) - 1):
                edge = (flow["route"][i], flow["route"][i+1])
                if edge in link_usage:
                    link_usage[edge] = max(0, link_usage[edge] - flow_caudal)
        current_version = flow.get("version", 1)
        best_route = None
        best_max_util = float('inf')

        if not (G.has_node("ru") and G.has_node("rg")):
            print(f"No se puede calcular la ruta para el flujo {flow_id}: 'ru' o 'rg' ausente.")
            continue

        candidate = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                candidate = nx.shortest_path(G, source="ru", target="rg", weight="cost", method="dijkstra")
            except (nx.NodeNotFound, nx.NetworkXNoPath) as e:
                print(f"No path found for flow {flow_id}: {e}")
                candidate = None
                break

            candidate_max_util = 0
            for i in range(len(candidate) - 1):
                edge = (candidate[i], candidate[i+1])
                current_usage = link_usage.get(edge, 0)
                util = (current_usage + flow_caudal) / CAPACITY
                candidate_max_util = max(candidate_max_util, util)

            if candidate_max_util < 0.8:
                best_route = candidate
                best_max_util = candidate_max_util
                break
            else:
                if candidate_max_util < best_max_util:
                    best_max_util = candidate_max_util
                    best_route = candidate
                for i in range(len(candidate) - 1):
                    edge = (candidate[i], candidate[i+1])
                    current_usage = link_usage.get(edge, 0)
                    if (current_usage + flow_caudal) / CAPACITY >= 0.8:
                        G[candidate[i]][candidate[i+1]]["cost"] += 5000

        if not best_route:
            print(f"No se pudo asignar una ruta para el flujo {flow_id}")
            continue

        # Si el flujo ya tenía ruta y no ha cambiado, no se hace nada (ni logs, ni update, ni tunnelmaker)
        if "route" in flow and flow["route"] == best_route:
            # Reincorporar la contribución del flujo a link_usage
            for i in range(len(best_route) - 1):
                edge = (best_route[i], best_route[i+1])
                link_usage[edge] = link_usage.get(edge, 0) + flow_caudal
            continue

        # Si hay cambio (o es nueva asignación), se actualiza la versión y se ejecuta tunnelmaker
        if "route" in flow and flow["route"] != best_route:
            new_version = current_version + 1
        else:
            new_version = current_version

        if best_max_util < 0.8:
            msg = "Ruta asignada satisfactoriamente (bajo 80% de utilización)."
        elif best_max_util < 1.0:
            msg = "Ruta casi saturada (entre 80% y 100%)."
        else:
            msg = "Ruta saturada (excede 100%), se asigna con advertencia."

        collection.update_one({"_id": flow_id}, {"$set": {"route": best_route, "version": new_version}})
        print(f"Flow {flow_id} assigned: version {new_version}, route: {best_route} | {msg}")

        for i in range(len(best_route) - 1):
            edge = (best_route[i], best_route[i+1])
            link_usage[edge] = link_usage.get(edge, 0) + flow_caudal

        method = "add" if new_version == 1 else "replace"
        subprocess.run(["python3", "tunnelmaker.py", str(flow_id), str(new_version), json.dumps(best_route), method])

def main():
    while True:
        print("Updating network state...")
        G = create_graph()
        energy_consumption = fetch_energy()
        flows = fetch_flows()
        
        G, affected_flows = router_checkup(G, energy_consumption, flows)
        if affected_flows:
            update_flow_versions(affected_flows)
            flows = fetch_flows()
        
        G = assign_costs(G, energy_consumption)
        G, link_usage = check_capacity(G, flows)
        assign_routes(G, flows, link_usage)
        
        time.sleep(5)

if __name__ == "__main__":
    main()
