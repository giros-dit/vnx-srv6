import networkx as nx
from pymongo import MongoClient

def create_graph(G):
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
        G.add_edge(*edge)

def fetch_energy():
    client = MongoClient("mongodb://mongo:27017/")
    db = client.across
    collection = db.energy
    energy_consumption = {}

    for router in ["r1", "r2", "r3", "r4", "ru", "rg"]:
        document = collection.find_one({"router": router})
        energy_consumption[router] = document.get("consumption", 0) if document else 0

    return energy_consumption

def assign_costs(G, energy_consumption):
    for u, v in G.edges():
        G[u][v]["cost"] = energy_consumption.get(v, 0)
    return G

def find_shortest_path(G, source, target):
    try:
        path = nx.shortest_path(G, source=source, target=target, weight="cost", method="dijkstra")
        print(" -> ".join(path))
    except nx.NetworkXNoPath:
        print("No path found")

def main():
    G = nx.DiGraph()
    create_graph(G)
    energy_consumption = fetch_energy()
    G = assign_costs(G, energy_consumption)
    find_shortest_path(G, "ru", "rg")

if __name__ == "__main__":
    main()
