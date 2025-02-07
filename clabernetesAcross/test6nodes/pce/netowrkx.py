import networkx as nx
from pymongo import MongoClient

def create_graph(G):
    for i in range(4):
        G.add_node(f"r{i+1}")

    G.add_node("ru")
    G.add_node("rg")
    G.add_edge("r1", "rg", directed=True)
    G.add_edge("rg", "r1", directed=True)
    G.add_edge("r3", "rg", directed=True)
    G.add_edge("rg", "r3", directed=True)
    G.add_edge("r1", "r2", directed=True)
    G.add_edge("r2", "r1", directed=True)
    G.add_edge("r3", "r4", directed=True)
    G.add_edge("r4", "r3", directed=True)
    G.add_edge("r2", "ru", directed=True)
    G.add_edge("ru", "r2", directed=True)
    G.add_edge("r4", "ru", directed=True)
    G.add_edge("ru", "r4", directed=True)


def fetch_energy():
    client = MongoClient("mongodb://mongo:27017/")
    db = client.across
    collection = db.power
    energy_consumption = {}
    for router in ["r1", "r2", "r3", "r4"]:
        document = collection.find_one({"router": router})
        if document:
            energy_consumption[router] = document.get("energy", 0)
        else:
            energy_consumption[router] = 0

    return energy_consumption

def assign_costs(G, energy_consumption):
    for u, v in G.edges():
        if v in energy_consumption:
            G[u][v]["cost"] = energy_consumption[v]
        else:
            G[u][v]["cost"] = 0
    
    return G

def main():
    G = nx.DiGraph()
    G = create_graph(G)
    energy_consumption = fetch_energy(G)
    G = assign_costs(G, energy_consumption)
    print(G.edges(data=True))


