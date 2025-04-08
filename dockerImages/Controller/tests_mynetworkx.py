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
    # def test_recalcroute_after_node_remove(self):
    #     initial_route = ["ru", "r2", "r1", "rg"]
    #     flows = [self.create_flow("flow1", route=initial_route, version=1)]
    #     G = mynetworkx.create_graph()
        
    #     # Simulación caida de nodo
    #     if G.has_node("r1"):
    #         G.remove_node("r1")
    #     removed = ["r1"]

    #     G = mynetworkx.assign_node_costs(G)
    #     updated_flows = mynetworkx.recalc_routes(G, flows, removed)
    #     #Comprobar que la ruta es distinta
    #     self.assertNotEqual(updated_flows[0].get("route", None), initial_route)
    #     #Se ha aumentado la versión
    #     self.assertEqual(updated_flows[0]["version"], 2)
    #     #Comprobar que la nueva ruta es válida y no contiene r1
    #     self.assertNotIn("r1", updated_flows[0]["route"])
    #     self.assertEqual(updated_flows[0]["route"][0], "ru")
    #     self.assertEqual(updated_flows[0]["route"][-1], "rg")

    def test_threshold_usage_scenario_A(self):
        """
        Escenario A: Todos los nodos tienen una utilización baja (0.5, por ejemplo),
        por lo que la ruta calculada debería tener uso máximo de 0.5.
        """
        for n in mynetworkx.router_state:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        max_usage = max(mynetworkx.router_state[node]["usage"] for node in route if node in mynetworkx.router_state)
        self.assertLessEqual(max_usage, 0.5)

    def test_threshold_usage_scenario_B(self):
        """
        Escenario B: Un nodo (r1) tiene utilización 0.85 (por encima de 0.8),
        lo que provoca que se excluya de G2 y se escoja una ruta que lo evite.
        Se espera que la ruta calculada no incluya r1.
        """
        mynetworkx.router_state["r1"]["usage"] = 0.85
        for n in ["r2", "r3", "r4", "ru", "rg"]:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        self.assertNotIn("r1", route)
        self.assertEqual(route[0], "ru")
        self.assertEqual(route[-1], "rg")

    def test_threshold_usage_scenario_C(self):
        """
        Escenario C: Dos posibles rutas tienen nodos con utilización entre 0.8 y 0.95.
        Se simula que r1 y r4 tienen utilización 0.85, de modo que G2 los excluye y
        se utiliza G3 para calcular la ruta, permitiendo su inclusión.
        Se comprueba que la ruta final incluya al menos uno de esos nodos y que el uso máximo sea 0.85.
        """
        mynetworkx.router_state["r1"]["usage"] = 0.85
        mynetworkx.router_state["r4"]["usage"] = 0.85
        for n in ["r2", "r3", "ru", "rg"]:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        # Al menos uno de r1 o r4 debe aparecer (vía G3).
        self.assertTrue("r1" in route or "r4" in route)
        max_usage = max(mynetworkx.router_state[node]["usage"] for node in route if node in mynetworkx.router_state)
        self.assertAlmostEqual(max_usage, 0.85)

    def test_threshold_usage_scenario_D(self):
        """
        Escenario D: Se simula que una ruta contiene un nodo con utilización baja y la otra con utilización por encima del segundo umbral.
        Por ejemplo, r1 con 0.5 y r4 con 0.97. En G2 se excluirá r4, por lo que se deberá elegir la ruta que incluya r1.
        """
        mynetworkx.router_state["r1"]["usage"] = 0.5
        mynetworkx.router_state["r4"]["usage"] = 0.97
        for n in ["r2", "r3", "ru", "rg"]:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        # Se espera que la ruta no incluya r4, ya que está por encima del primer umbral.
        self.assertNotIn("r4", route)
        self.assertIn("r1", route)
        self.assertEqual(route[0], "ru")
        self.assertEqual(route[-1], "rg")

    def test_threshold_usage_scenario_E(self):
        """
        Escenario E: Todos los nodos (excepto ru y rg) tienen utilización por encima del segundo umbral (0.95),
        lo que imposibilita encontrar una ruta válida.
        Se espera que el flujo no reciba ruta.
        """
        for n in ["r1", "r2", "r3", "r4"]:
            mynetworkx.router_state[n]["usage"] = 0.97
        mynetworkx.router_state["ru"]["usage"] = 0.0
        mynetworkx.router_state["rg"]["usage"] = 0.0
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        self.assertNotIn("route", updated_flows[0])
    

    #####################################################################################
    #####################################################################################
    #####################################################################################

    # ------------------------------------------------------------
    # Pruebas de límites en el timestamp (NODE_TIMEOUT = 15s)
    # ------------------------------------------------------------
    def test_timestamp_boundary_exact(self):
        """
        Caso en el que la diferencia es exactamente 15 s: 
        (now - ts == 15) => no se considera caído, ya que la condición es '>'
        """
        mynetworkx.router_state["r1"]["ts"] = self.current_time - 15.0

        original_time = time.time
        try:
            time.time = lambda: self.current_time
            G = mynetworkx.create_graph()
            flows = [self.create_flow("flow1", route=["ru", "r1", "rg"], version=1)]
            G, flows, removed = mynetworkx.remove_inactive_nodes(G, flows)
            self.assertNotIn("r1", removed)
            self.assertIn("r1", G.nodes())
            self.assertEqual(flows[0]["route"], ["ru", "r1", "rg"])
            self.assertEqual(flows[0]["version"], 1)
        finally:
            time.time = original_time

    def test_timestamp_boundary_slightly_less(self):
        """
        Caso en el que la diferencia es 14.9 s, debe seguir activo.
        """
        mynetworkx.router_state["r1"]["ts"] = self.current_time - 14.9
        original_time = time.time
        try:
            time.time = lambda: self.current_time
            G = mynetworkx.create_graph()
            flows = [self.create_flow("flow1", route=["ru", "r1", "rg"], version=1)]
            G, flows, removed = mynetworkx.remove_inactive_nodes(G, flows)
            self.assertNotIn("r1", removed)
            self.assertIn("r1", G.nodes())
            self.assertEqual(flows[0]["route"], ["ru", "r1", "rg"])
            self.assertEqual(flows[0]["version"], 1)
        finally:
            time.time = original_time

    def test_timestamp_boundary_slightly_greater(self):
        """
        Caso en el que la diferencia es 15.1 s, el router se debe considerar caído.
        """
        mynetworkx.router_state["r1"]["ts"] = self.current_time - 15.1
        original_time = time.time
        try:
            time.time = lambda: self.current_time
            G = mynetworkx.create_graph()
            flows = [self.create_flow("flow1", route=["ru", "r1", "rg"], version=1)]
            G, flows, removed = mynetworkx.remove_inactive_nodes(G, flows)
            self.assertIn("r1", removed)
            self.assertNotIn("r1", G.nodes())
            self.assertNotIn("route", flows[0])
            self.assertEqual(flows[0]["version"], 2)
        finally:
            time.time = original_time

    # ------------------------------------------------------------
    # Pruebas de integración del flujo completo
    # ------------------------------------------------------------
    def test_integration_full_cycle(self):
        """
        Simula un ciclo completo: asigna un flujo, luego simula que un router
        deja de actualizarse (cambio de timestamp) y se verifica que se recalcule la ruta.
        """
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        flows = mynetworkx.recalc_routes(G, flows, removed)
        initial_route = flows[0].get("route")
        self.assertIsNotNone(initial_route)
        self.assertEqual(initial_route[0], "ru")
        self.assertEqual(initial_route[-1], "rg")
        version_initial = flows[0]["version"]

        mynetworkx.router_state["r2"]["ts"] = self.current_time - 16
        G = mynetworkx.create_graph()
        original_time = time.time
        try:
            time.time = lambda: self.current_time
            G, flows, removed = mynetworkx.remove_inactive_nodes(G, flows)
            G = mynetworkx.assign_node_costs(G)
            flows = mynetworkx.recalc_routes(G, flows, removed)
            self.assertNotIn("route", flows[0])
            self.assertEqual(flows[0]["version"], version_initial + 1)
        finally:
            time.time = original_time

    def test_multiple_flows_integration(self):
        """
        Prueba el escenario en el que se agregan nuevos flujos mientras ya existen otros.
        Verifica que la asignación y actualización se comporta correctamente para todos.
        """
        flows = [self.create_flow("flow1"), self.create_flow("flow2")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        flows = mynetworkx.recalc_routes(G, flows, removed)
        for f in flows:
            self.assertIn("route", f)
            self.assertEqual(f["route"][0], "ru")
            self.assertEqual(f["route"][-1], "rg")
        version_f1 = flows[0]["version"]
        version_f2 = flows[1]["version"]

        mynetworkx.router_state["r3"]["ts"] = self.current_time - 16
        G = mynetworkx.create_graph()
        original_time = time.time
        try:
            time.time = lambda: self.current_time
            G, flows, removed = mynetworkx.remove_inactive_nodes(G, flows)
            G = mynetworkx.assign_node_costs(G)
            flows = mynetworkx.recalc_routes(G, flows, removed)
            for f in flows:
                if "r3" in f.get("route", []):
                    self.fail("La ruta recalculada no debe incluir al nodo caído 'r3'.")
                if version_f1 != f["version"] or version_f2 != f["version"]:
                    self.assertGreater(f["version"], 1)
        finally:
            time.time = original_time

    # ------------------------------------------------------------
    # Pruebas de rutas múltiples y selección según umbrales
    # ------------------------------------------------------------
    def test_threshold_usage_scenario_A(self):
        for n in mynetworkx.router_state:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        max_usage = max(mynetworkx.router_state[node]["usage"] for node in route if node in mynetworkx.router_state)
        self.assertLessEqual(max_usage, 0.5)

    def test_threshold_usage_scenario_B(self):
        mynetworkx.router_state["r1"]["usage"] = 0.85
        for n in ["r2", "r3", "r4", "ru", "rg"]:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        self.assertNotIn("r1", route)
        self.assertEqual(route[0], "ru")
        self.assertEqual(route[-1], "rg")

    def test_threshold_usage_scenario_C(self):
        mynetworkx.router_state["r1"]["usage"] = 0.85
        mynetworkx.router_state["r4"]["usage"] = 0.85
        for n in ["r2", "r3", "ru", "rg"]:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        self.assertTrue("r1" in route or "r4" in route)
        max_usage = max(mynetworkx.router_state[node]["usage"] for node in route if node in mynetworkx.router_state)
        self.assertAlmostEqual(max_usage, 0.85)

    def test_threshold_usage_scenario_D(self):
        mynetworkx.router_state["r1"]["usage"] = 0.5
        mynetworkx.router_state["r4"]["usage"] = 0.97
        for n in ["r2", "r3", "ru", "rg"]:
            mynetworkx.router_state[n]["usage"] = 0.5
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        route = updated_flows[0]["route"]
        self.assertNotIn("r4", route)
        self.assertIn("r1", route)
        self.assertEqual(route[0], "ru")
        self.assertEqual(route[-1], "rg")

    def test_threshold_usage_scenario_E(self):
        for n in ["r1", "r2", "r3", "r4"]:
            mynetworkx.router_state[n]["usage"] = 0.97
        mynetworkx.router_state["ru"]["usage"] = 0.0
        mynetworkx.router_state["rg"]["usage"] = 0.0
        flows = [self.create_flow("flow1")]
        G = mynetworkx.create_graph()
        G = mynetworkx.assign_node_costs(G)
        removed = []
        updated_flows = mynetworkx.recalc_routes(G, flows, removed)
        self.assertNotIn("route", updated_flows[0])



if __name__ == '__main__':
    unittest.main()
