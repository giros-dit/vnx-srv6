import unittest
import time
import networkx as nx
import json
import os
from unittest.mock import patch, mock_open


import mynetworkx

class TestMyNetworkx(unittest.TestCase):

    def setUp(self):
        mynetworkx.router_state.clear()
        self.current_time = time.time()
        routers = ["r1", "r2", "r3", "r4", "ru", "rg"]
        for r in routers:
            mynetworkx.router_state[r] = {"usage": 0.0, "energy": 700, "ts": self.current_time}
    
    def create_flow(self, flow_id="flow1", route=None, version=1):
        if route is not None:
            return {"_id": flow_id, "version": version, "route": route}
        return {"_id": flow_id, "version": version}

    def test_create_graph(self):
        G = mynetworkx.create_graph()
        self.assertTrue(isinstance(G, nx.DiGraph))
        self.assertEqual(len(G.nodes()), 6)  # r1, r2, r3, r4, ru, rg
        # Verifica  aristas
        self.assertTrue(G.has_edge("r1", "rg"))
        self.assertTrue(G.has_edge("r3", "r4"))
        self.assertTrue(G.has_edge("r2", "ru"))
        self.assertTrue(G.has_edge("ru", "r4"))
        self.assertTrue(G.has_edge("r1", "r2"))
        self.assertFalse(G.has_edge("r1", "r3"))
    
    #Probar que si la lista de flujos está vacía, no se actualice nada
    def test_no_flows(self):
        flows = []
        G = mynetworkx.create_graph()
        removed = []  # No hay nodos caídos.
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        self.assertEqual(updated_flows, [])

    #Probar que se eliminen los nodos inactivos y se actualicen los flujos
    @patch("mynetworkx.time.time", return_value=1000)
    def test_remove_inactive_nodes(self, mock_time):
        # Configura router_state con timestamps
        mynetworkx.router_state.update({
            "r1": {"usage": 0.1, "energy": 700, "ts": 980},  
            "r2": {"usage": 0.2, "energy": 700, "ts": 995} 
        })
        # Crea grafo y flujo de ejemplo
        G = nx.DiGraph()
        G.add_nodes_from(["r1", "r2"])
        flows = [{"_id": "flow1", "route": ["r1", "r2"], "version": 1}]
        G, flows, removed = mynetworkx.remove_inactive_nodes(G, flows)
        # Se espera que r1 sea suspendido
        self.assertNotIn("r1", G.nodes())
        self.assertIn("r1", removed)

        self.assertNotIn("route", flows[0])
        self.assertEqual(flows[0]["version"], 2)


    def test_write_and_read_flows(self):
        flows = [{"_id": "flow1", "route": ["r2", "r1"], "version": 1}]
        inactive_routers = ["r3"]
        router_utilization = {"r1": 0.1, "r2": 0.2, "r3": 0.0}
        temp_filename = "temp_flows.json"
        try:
            mynetworkx.write_flows(flows, inactive_routers, router_utilization)
            with open("flows.json", "r") as f:
                data = json.load(f)
            self.assertEqual(data["flows"], flows)
            self.assertEqual(data["inactive_routers"], inactive_routers)
            self.assertEqual(data["router_utilization"], router_utilization)
        finally:
            # Limpia el archivo creado
            if os.path.exists("flows.json"):
                os.remove("flows.json")

    #Prueba asignar ruta un flujo sin esta, con todos los nodos activos.
    def test_assign_flow_initial(self):
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        # Actualiza los costos de cada arista según el estado de los routers.
        G = mynetworkx.assign_node_costs(G)
        removed = []  # Estan todos los nodos activos.
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        # Comprobar que la ruta fue asignada
        self.assertIn("route", updated_flows[0])
        route = updated_flows[0]["route"]
        # Comprobar que la ruta es válida
        self.assertEqual(route[0], "ru")
        self.assertEqual(route[-1], "rg")
        # Verificar que la version sea 1 al ser un flujo nuevo
        self.assertEqual(updated_flows[0]["version"], 1)
    
    #Probar que no se recalcula la ruta si no hay nodos caídos
    def test_existing_flow_valid_route(self):
        initial_route = ["ru", "r4", "r3", "rg"]
        flows = [self.create_flow("flow1", route=initial_route, version=1)]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = [] 
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        # Comprobar que la ruta no cambió
        self.assertEqual(updated_flows[0]["route"], initial_route)
        # Verificar que la version no cambió
        self.assertEqual(updated_flows[0]["version"], 1)

    #Probar que si elimino un nodo del grafo, se recalcule la ruta
    def test_recalcroute_after_node_remove(self):
        initial_route = ["ru", "r2", "r1", "rg"]
        flows = [self.create_flow("flow1", route=initial_route, version=1)]
        G = mynetworkx.create_graph()
        
        # Simulación caida de nodo
        if G.has_node("r1"):
            G.remove_node("r1")
        removed = ["r1"]

        G = mynetworkx.assign_node_costs(G)
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        self.assertNotEqual(updated_flows[0].get("route", None), initial_route)
        self.assertEqual(updated_flows[0]["version"], 2)
        self.assertNotIn("r1", updated_flows[0]["route"])
        self.assertEqual(updated_flows[0]["route"][0], "ru")
        self.assertEqual(updated_flows[0]["route"][-1], "rg")

if __name__ == '__main__':
    unittest.main()
