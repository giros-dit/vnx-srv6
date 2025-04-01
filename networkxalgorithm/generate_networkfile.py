#!/usr/bin/env python3
import os
import yaml
import json
import re
import argparse
from collections import defaultdict
import logging

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

def create_full_graph(yaml_file, full_filter):
    logging.debug("Loading YAML topology from %s", yaml_file)
    with open(yaml_file, "r") as f:
        topology = yaml.safe_load(f)
    nodes_dict = topology.get("topology", {}).get("nodes", {})
    links = topology.get("topology", {}).get("links", [])
    # Filtrar todos los nodos que empiecen con "r" (incluye especiales)
    full_nodes = {node for node in nodes_dict.keys() if re.fullmatch(full_filter, node, re.IGNORECASE)}
    logging.debug("Full filtered nodes: %s", full_nodes)
    net_to_nodes = defaultdict(set)
    for link in links:
        endpoints = link.get("endpoints", [])
        nets = [ep for ep in endpoints if ep.startswith("multus:")]
        nodes_in_link = []
        for ep in endpoints:
            node = ep.split(":", 1)[0]
            if node in full_nodes:
                nodes_in_link.append(node)
        for net in nets:
            for node in nodes_in_link:
                net_to_nodes[net].add(node)
    logging.debug("Net to nodes mapping: %s", dict(net_to_nodes))
    edges_set = set()
    for net, nodes in net_to_nodes.items():
        nodes = list(nodes)
        if len(nodes) >= 2:
            for i in range(len(nodes)):
                for j in range(i+1, len(nodes)):
                    edges_set.add((nodes[i], nodes[j]))
                    edges_set.add((nodes[j], nodes[i]))
    logging.debug("Full edges set: %s", edges_set)
    full_graph = {
        "nodes": list(full_nodes),
        "edges": [{"source": s, "target": t, "cost": 0.0} for (s, t) in edges_set]
    }
    logging.debug("Full graph generated: %s", full_graph)
    return full_graph, topology, net_to_nodes

def filter_final_graph(full_graph, final_filter):
    final_nodes = [node for node in full_graph["nodes"] if re.fullmatch(final_filter, node, re.IGNORECASE)]
    final_edges = [edge for edge in full_graph["edges"]
                   if edge["source"] in final_nodes and edge["target"] in final_nodes]
    final_graph = {"nodes": final_nodes, "edges": final_edges}
    logging.debug("Final graph (filtered) generated: %s", final_graph)
    return final_graph

def extract_extremos_by_net(net_to_nodes, final_filter, final_nodes):
    """
    Se recorre cada segmento (net). Si, tras aplicar final_filter, en esa red hay un único nodo final y
    en el conjunto original de esa red aparece un indicador especial, se considera candidato para extremo.
    
    Indicadores:
      - PF: si en la red aparece "rupf" o algún nodo que empiece por "hupf"
      - gNB: si en la red aparece un nodo que cumpla "rgnb\d*" o sea "rg"
    
    Si no se obtiene ningún candidato PF de ninguna red, se asigna como PF el nodo final de mayor valor numérico.
    """
    pf_pattern = re.compile(r"^(rupf|hupf.*)$", re.IGNORECASE)
    gnb_pattern = re.compile(r"^(rgnb\d*|rg)$", re.IGNORECASE)
    pf_candidates = set()
    gnb_candidates = set()
    for net, nodes in net_to_nodes.items():
        final_in_net = {n for n in nodes if re.fullmatch(final_filter, n, re.IGNORECASE)}
        if len(final_in_net) == 1:
            candidate = next(iter(final_in_net))
            # Si en el conjunto original aparece un PF especial, se asigna candidato PF
            if any(pf_pattern.fullmatch(x) for x in nodes):
                pf_candidates.add(candidate)
                logging.debug("Net %s: PF indicator found, candidate: %s", net, candidate)
            # Si aparece un indicador gNB, se asigna candidato gNB
            if any(gnb_pattern.fullmatch(x) for x in nodes):
                gnb_candidates.add(candidate)
                logging.debug("Net %s: gNB indicator found, candidate: %s", net, candidate)
    def num_val(x):
        m = re.search(r"\d+", x)
        return int(m.group()) if m else 0
    if pf_candidates:
        PF_extreme = max(pf_candidates, key=num_val)
    else:
        # Si no se obtuvieron candidatos PF, asignar el nodo final de mayor valor numérico de todos
        PF_extreme = max(final_nodes, key=num_val) if final_nodes else None
    logging.debug("PF candidates: %s, chosen PF: %s", pf_candidates, PF_extreme)
    logging.debug("gNB candidates: %s", gnb_candidates)
    return {"origen": PF_extreme, "destinos": sorted(list(gnb_candidates))}

def extract_loopback_from_file(filepath):
    logging.debug("Extracting loopback from file: %s", filepath)
    loopback = None
    in_lo = False
    try:
        with open(filepath, "r") as f:
            for line in f:
                lstrip = line.strip()
                if lstrip.startswith("interface") and "lo" in lstrip:
                    in_lo = True
                    logging.debug("Found 'interface lo' in %s", filepath)
                elif in_lo and lstrip.startswith("interface"):
                    break
                elif in_lo and "ipv6 address" in lstrip:
                    parts = lstrip.split()
                    if len(parts) >= 3:
                        loopback = parts[2]
                        logging.debug("Loopback address found: %s", loopback)
                        break
    except Exception as e:
        logging.error("Error reading file %s: %s", filepath, e)
    return loopback

def extract_loopbacks(base_dir, node_list):
    logging.debug("Extracting loopbacks from base directory: %s", base_dir)
    loopbacks = {}
    for node in node_list:
        zebra_path = os.path.join(base_dir, "conf", node, "zebra.conf")
        logging.debug("Processing node %s, file: %s", node, zebra_path)
        addr = extract_loopback_from_file(zebra_path)
        if addr:
            loopbacks[node] = addr
    logging.debug("Extracted loopbacks: %s", loopbacks)
    return loopbacks

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera un JSON final con grafo (nodos y enlaces), extremos y loopbacks a partir de una topología containerlab")
    # full_filter: se incluyen todos los nodos que comienzan con "r"
    parser.add_argument("yaml_file", help="Ruta al archivo YAML de containerlab")
    parser.add_argument("--full_filter", default=r"^(r.*)$",
                        help="Regex para filtrar nodos para el grafo completo (por defecto: '^(r.*)$')")
    # final_filter: por ejemplo, para 10 nodos: "^(r\d+)$", para 6 nodos: "^(r\d+|ru|rg)$"
    parser.add_argument("--final_filter", default=r"^(r\d+)$",
                        help="Regex para filtrar nodos en la salida final")
    parser.add_argument("--output", default="final_output.json", help="Archivo de salida JSON final")
    args = parser.parse_args()

    full_graph, topology, net_to_nodes = create_full_graph(args.yaml_file, args.full_filter)
    final_graph = filter_final_graph(full_graph, args.final_filter)
    final_nodes = final_graph["nodes"]
    extremos = extract_extremos_by_net(net_to_nodes, args.final_filter, set(final_nodes))
    base_dir = os.path.dirname(os.path.abspath(args.yaml_file))
    loopbacks = extract_loopbacks(base_dir, final_nodes)

    final_json = {
        "graph": final_graph,
        "extremos": extremos,
        "loopbacks": loopbacks
    }

    with open(args.output, "w") as f:
        json.dump(final_json, f, indent=2)
    logging.info("JSON final guardado en %s", args.output)
