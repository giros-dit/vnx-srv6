#!/usr/bin/env python3
import yaml
import json
import re
import argparse
from collections import defaultdict

def create_networkx_json(yaml_file, node_filter_regex):
    # Cargar la topología desde el archivo YAML
    with open(yaml_file, "r") as f:
        topology = yaml.safe_load(f)

    nodes_dict = topology.get("topology", {}).get("nodes", {})
    links = topology.get("topology", {}).get("links", [])

    # Filtra los nodos que cumplen con el regex, por ejemplo, "r\d+" para r1, r2, …, r13.
    router_nodes = {node for node in nodes_dict.keys() if re.fullmatch(node_filter_regex, node)}

    # Diccionario que agrupa los routers por cada segmento de red (ej. "multus:net1001")
    net_to_routers = defaultdict(set)

    for link in links:
        endpoints = link.get("endpoints", [])
        # Se obtienen los endpoints que pertenecen a un segmento de red (aquellos que empiezan con "multus:")
        nets = [ep for ep in endpoints if ep.startswith("multus:")]
        # Se obtienen los endpoints que son routers (usando el filtro sobre el nombre antes del ":")
        routers = []
        for ep in endpoints:
            node = ep.split(":", 1)[0]
            if node in router_nodes:
                routers.append(node)
        # Para cada segmento (red) encontrado en este enlace, se asocian todos los routers de ese enlace.
        for net in nets:
            for router in routers:
                net_to_routers[net].add(router)

    # Generar las aristas: para cada segmento de red con 2 o más routers,
    # se crean aristas bidireccionales entre cada par.
    edges_set = set()
    for net, routers in net_to_routers.items():
        routers = list(routers)
        if len(routers) >= 2:
            for i in range(len(routers)):
                for j in range(i + 1, len(routers)):
                    edges_set.add((routers[i], routers[j]))
                    edges_set.add((routers[j], routers[i]))

    # Construir el JSON con la lista de nodos y aristas
    graph = {
        "nodes": list(router_nodes),
        "edges": [{"source": s, "target": t, "cost": 0.0} for (s, t) in edges_set]
    }
    return graph

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera un JSON para networkx a partir de una topología containerlab")
    parser.add_argument("yaml_file", help="Ruta al archivo YAML de containerlab")
    parser.add_argument("--filter", default=r"r\d+",
                        help="Regex para filtrar los nodos (por defecto: r\\d+). Por ejemplo, para 6-nodos: '^(r[1-4]|ru|rg)$'")
    parser.add_argument("--output", default="networkx_graph.json", help="Archivo de salida JSON")
    args = parser.parse_args()

    graph = create_networkx_json(args.yaml_file, args.filter)
    with open(args.output, "w") as f:
        json.dump(graph, f, indent=2)
    print(f"JSON del grafo guardado en {args.output}")
