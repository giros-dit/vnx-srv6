#!/usr/bin/env python3
import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import json
import time
import os
import threading
import networkx as nx
import ipaddress
import boto3
from botocore.exceptions import ClientError

# Importar el módulo a probar
# Importamos selectivamente para poder hacer mock de las dependencias externas
with patch.dict('sys.modules', {
    'boto3': MagicMock(),
    'kafka': MagicMock(),
    'ipaddress': ipaddress,
}):
    import pce

class TestPCENoTables(unittest.TestCase):
    
    def setUp(self):
        # Reset estado global antes de cada test
        pce.router_state = {}
        pce.metrics = {
            "routes_recalculated": 0,
            "nodes_removed": 0,
            "nodes_restored": 0,
            "flows_updated": 0
        }
        # Configurar variables de entorno para tests
        os.environ['S3_ENDPOINT'] = 'http://localhost:9000'
        os.environ['S3_ACCESS_KEY'] = 'minioadmin'
        os.environ['S3_SECRET_KEY'] = 'minioadmin'
        os.environ['S3_BUCKET'] = 'test-bucket'
        os.environ['ENERGYAWARE'] = 'true'
        os.environ['DEBUG_COSTS'] = 'false'
        
        # TOPOLOGÍA UNIFICADA: Enlaces unidireccionales en ambas direcciones
        # ru <-> r1, ru <-> r2, r1 <-> r3, r2 <-> r3, r3 <-> rg, r3 <-> rc
        self.network_info = {
            "graph": {
                "nodes": ["ru", "r1", "r2", "r3", "rg", "rc"],
                "edges": [
                    # ru <-> r1
                    {"source": "ru", "target": "r1", "cost": 1},
                    {"source": "r1", "target": "ru", "cost": 1},
                    # ru <-> r2
                    {"source": "ru", "target": "r2", "cost": 1},
                    {"source": "r2", "target": "ru", "cost": 1},
                    # r1 <-> r3
                    {"source": "r1", "target": "r3", "cost": 1},
                    {"source": "r3", "target": "r1", "cost": 1},
                    # r2 <-> r3
                    {"source": "r2", "target": "r3", "cost": 1},
                    {"source": "r3", "target": "r2", "cost": 1},
                    # r3 <-> rg
                    {"source": "r3", "target": "rg", "cost": 1},
                    {"source": "rg", "target": "r3", "cost": 1},
                    # r3 <-> rc
                    {"source": "r3", "target": "rc", "cost": 1},
                    {"source": "rc", "target": "r3", "cost": 1}
                ]
            }
        }
        
        # Datos de prueba para flujos (sin tablas)
        self.test_flows = [
            {"_id": "fd00:0:2::1/128", "version": 1, "route": ["ru", "r1", "r3", "rg"]},
            {"_id": "fd00:0:3::1/128", "version": 1}
        ]
        
        # Router state para pruebas - usando la topología unificada
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": time.time()},
                "r2": {"energy": 0.3, "usage": 0.9, "ts": time.time()},
                "r3": {"energy": 0.4, "usage": 0.6, "ts": time.time()}
            }
    
    def create_unified_graph(self):
        """Crea el grafo unificado para todos los tests con enlaces unidireccionales"""
        G = nx.DiGraph()
        G.add_nodes_from(["ru", "r1", "r2", "r3", "rg", "rc"])
        # Enlaces unidireccionales en ambas direcciones
        G.add_edges_from([
            # ru <-> r1
            ("ru", "r1", {"cost": 1}),
            ("r1", "ru", {"cost": 1}),
            # ru <-> r2
            ("ru", "r2", {"cost": 1}),
            ("r2", "ru", {"cost": 1}),
            # r1 <-> r3
            ("r1", "r3", {"cost": 1}),
            ("r3", "r1", {"cost": 1}),
            # r2 <-> r3
            ("r2", "r3", {"cost": 1}),
            ("r3", "r2", {"cost": 1}),
            # r3 <-> rg
            ("r3", "rg", {"cost": 1}),
            ("rg", "r3", {"cost": 1}),
            # r3 <-> rc
            ("r3", "rc", {"cost": 1}),
            ("rc", "r3", {"cost": 1})
        ])
        return G
    
    # Test 1: Creación de grafo
    @patch('builtins.open', new_callable=mock_open)
    def test_create_graph(self, mock_file):
        # Preparar el mock para leer networkinfo.json
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Llamar a la función
        G = pce.create_graph()
        
        # Verificar que el grafo se crea correctamente con la topología unificada
        self.assertEqual(len(G.nodes), 6)
        self.assertEqual(len(G.edges), 12)  # 12 enlaces unidireccionales (6 pares bidireccionales)
        # Verificar enlaces en ambas direcciones
        self.assertTrue(G.has_edge("ru", "r1"))
        self.assertTrue(G.has_edge("r1", "ru"))
        self.assertTrue(G.has_edge("ru", "r2"))
        self.assertTrue(G.has_edge("r2", "ru"))
        self.assertTrue(G.has_edge("r1", "r3"))
        self.assertTrue(G.has_edge("r3", "r1"))
        self.assertTrue(G.has_edge("r2", "r3"))
        self.assertTrue(G.has_edge("r3", "r2"))
        self.assertTrue(G.has_edge("r3", "rg"))
        self.assertTrue(G.has_edge("rg", "r3"))
        self.assertTrue(G.has_edge("r3", "rc"))
        self.assertTrue(G.has_edge("rc", "r3"))
        self.assertEqual(G["ru"]["r1"]["cost"], 1)
    
    # Test 2.1: Incremento versión - flujo nuevo
    def test_increment_version_new_flow(self):
        flow = {"_id": "test"}
        new_version = pce.increment_version(flow)
        self.assertEqual(new_version, 2)
        self.assertEqual(flow["version"], 2)
    
    # Test 2.2: Incremento versión - flujo existente
    def test_increment_version_existing_flow(self):
        flow = {"_id": "test", "version": 5}
        new_version = pce.increment_version(flow)
        self.assertEqual(new_version, 6)
        self.assertEqual(flow["version"], 6)
    
    # Test 3.1: Validación ruta válida
    def test_is_route_valid_valid_route(self):
        G = self.create_unified_graph()
        
        # Ruta válida: ru -> r1 -> r3 -> rg
        self.assertTrue(pce.is_route_valid(G, ["ru", "r1", "r3", "rg"]))
        # Ruta válida: ru -> r2 -> r3 -> rc
        self.assertTrue(pce.is_route_valid(G, ["ru", "r2", "r3", "rc"]))
    
    # Test 3.2: Validación ruta inválida
    def test_is_route_valid_invalid_route(self):
        G = self.create_unified_graph()
        
        # Ruta con enlace directo que no existe: ru -> r3
        self.assertFalse(pce.is_route_valid(G, ["ru", "r3", "rg"]))
        # Ruta con enlace directo que no existe: r1 -> rg
        self.assertFalse(pce.is_route_valid(G, ["ru", "r1", "rg"]))
        # Ruta con nodo que no existe
        self.assertFalse(pce.is_route_valid(G, ["ru", "r4", "rg"]))
    
    # Test 3.3: Validación ruta vacía
    def test_is_route_valid_empty_route(self):
        G = self.create_unified_graph()
        
        self.assertFalse(pce.is_route_valid(G, []))
        self.assertFalse(pce.is_route_valid(G, ["ru"]))
    
    # Test 4.1: Nodo activo reciente
    def test_remove_inactive_nodes_active_node(self):
        G = self.create_unified_graph()
        
        flows = [{"_id": "f1", "version": 1, "route": ["ru", "r1", "r3", "rg"]}]
        inactive_routers = []
        
        # r1 activo (timestamp reciente)
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": time.time()},
            }
        
        G_new, flows_new, inactive_new, modified = pce.remove_inactive_nodes(G, flows, inactive_routers)
        
        self.assertTrue(G_new.has_node("r1"))
        self.assertFalse(modified)
        self.assertEqual(pce.metrics["nodes_removed"], 0)
    
    # Test 4.2: Nodo inactivo timeout
    def test_remove_inactive_nodes_timeout(self):
        G = self.create_unified_graph()
        
        flows = [{"_id": "f1", "version": 1, "route": ["ru", "r1", "r3", "rg"]}]
        inactive_routers = []
        
        # r1 inactivo (timestamp viejo)
        old_time = time.time() - pce.NODE_TIMEOUT - 5
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": old_time},
            }
        
        G_new, flows_new, inactive_new, modified = pce.remove_inactive_nodes(G, flows, inactive_routers)
        
        self.assertFalse(G_new.has_node("r1"))
        self.assertEqual(inactive_new, ["r1"])
        self.assertTrue(modified)
        self.assertEqual(pce.metrics["nodes_removed"], 1)
    
    # Test 4.3: Actualización de flujos cuando un nodo se vuelve inactivo
    def test_remove_inactive_nodes_flow_update(self):
        G = self.create_unified_graph()
        
        flows = [
            {"_id": "f1", "version": 1, "route": ["ru", "r1", "r3", "rg"]},
            {"_id": "f2", "version": 1, "route": ["ru", "r2", "r3", "rc"]}
        ]
        
        inactive_routers = []
        
        # r1 inactivo
        old_time = time.time() - pce.NODE_TIMEOUT - 5
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": old_time},
                "r2": {"energy": 0.3, "usage": 0.9, "ts": time.time()},
                "r3": {"energy": 0.4, "usage": 0.6, "ts": time.time()}
            }
        
        G_new, flows_new, inactive_new, modified = pce.remove_inactive_nodes(G, flows, inactive_routers)
        
        self.assertEqual(flows_new[0]["version"], 2)  # Flujo 1 usa r1, actualizado
        self.assertEqual(flows_new[1]["version"], 1)  # Flujo 2 usa r2, no actualizado
        self.assertNotIn("route", flows_new[0])  # Ruta eliminada para forzar recálculo
        self.assertIn("route", flows_new[1])  # Ruta mantenida
        self.assertEqual(pce.metrics["flows_updated"], 1)
    
    # Test 5.1: Costes energy-aware
    def test_assign_node_costs_energy_aware(self):
        G = self.create_unified_graph()
        
        current_time = time.time()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": current_time},
                "r2": {"energy": 0.3, "usage": 0.9, "ts": current_time},
                "r3": {"energy": 0.4, "usage": 0.6, "ts": current_time}
            }
        
        pce.ENERGYAWARE = True
        G = pce.assign_node_costs(G)
        
        self.assertEqual(G["ru"]["r1"]["cost"], 0.5)
        self.assertEqual(G["ru"]["r2"]["cost"], 0.3)
        self.assertEqual(G["r1"]["r3"]["cost"], 0.4)
        self.assertEqual(G["r2"]["r3"]["cost"], 0.4)
    
    # Test 5.2: Costes energy-disabled
    def test_assign_node_costs_fixed(self):
        G = self.create_unified_graph()
        
        current_time = time.time()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": current_time},
                "r2": {"energy": 0.3, "usage": 0.9, "ts": current_time},
                "r3": {"energy": 0.4, "usage": 0.6, "ts": current_time}
            }
        
        pce.ENERGYAWARE = False
        G = pce.assign_node_costs(G)
        
        self.assertEqual(G["ru"]["r1"]["cost"], 0.1)
        self.assertEqual(G["ru"]["r2"]["cost"], 0.1)
    
    # Test 6.1: Destino red rg
    def test_choose_destination_rg(self):
        dest = pce.choose_destination("fd00:0:2::10/128")
        self.assertEqual(dest, "rg")
    
    # Test 6.2: Destino red rc
    def test_choose_destination_rc(self):
        dest = pce.choose_destination("fd00:0:3::20/128")
        self.assertEqual(dest, "rc")
    
    # Test 6.3: Destino red desconocida
    def test_choose_destination_unknown(self):
        with self.assertRaises(ValueError):
            pce.choose_destination("fd00:0:4::30/128")
    
    # Test 7.1: Lectura flujos S3
    @patch('boto3.client')
    def test_read_flows_success(self, mock_boto3_client):
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        pce.s3_client = mock_s3
        
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'flows/flows_1.json', 'LastModified': '2023-01-01'},
                {'Key': 'flows/flows_2.json', 'LastModified': '2023-01-02'}
            ]
        }
        
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "flows": self.test_flows,
            "inactive_routers": ["r4"]
        }).encode()
        mock_s3.get_object.return_value = {'Body': mock_body}
        
        flows, inactive = pce.read_flows()
        
        self.assertEqual(len(flows), 2)
        self.assertEqual(flows[0]["_id"], "fd00:0:2::1/128")
        self.assertEqual(flows[0]["route"], ["ru", "r1", "r3", "rg"])
        self.assertEqual(inactive, ["r4"])
    
    # Test 7.2: Lectura S3 vacío
    @patch('boto3.client')
    def test_read_flows_empty(self, mock_boto3_client):
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        pce.s3_client = mock_s3
        
        mock_s3.list_objects_v2.return_value = {}
        
        flows, inactive = pce.read_flows()
        
        self.assertEqual(flows, [])
        self.assertEqual(inactive, [])
    
    # Test 7.3: Escritura flujos S3
    @patch('boto3.client')
    def test_write_flows(self, mock_boto3_client):
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        pce.s3_client = mock_s3
        
        pce.write_flows(self.test_flows, ["r4"])
        
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args[1]
        
        self.assertTrue('Key' in call_args)
        self.assertTrue('Body' in call_args)
        self.assertTrue(call_args['Key'].startswith('flows/flows_'))
        
        body_json = call_args['Body'].decode()
        body_dict = json.loads(body_json)
        self.assertEqual(body_dict["flows"], self.test_flows)
        self.assertEqual(body_dict["inactive_routers"], ["r4"])
    
    # Test 8.1: Cálculo ruta normal (usar r2 por menor energía)
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_normal(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": time.time()},
                "r2": {"energy": 0.3, "usage": 0.7, "ts": time.time()},  # Menor energía
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        inactive_routers = []
        
        pce.OCCUPANCY_LIMIT = 0.8
        pce.ROUTER_LIMIT = 0.95
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertTrue(modified)
        self.assertEqual(flows[0]["version"], 2)
        self.assertTrue("route" in flows[0])
        
        # Verificar que se usó r2 por menor coste energético
        expected_route = ["ru", "r2", "r3", "rg"]
        self.assertEqual(flows[0]["route"], expected_route)
    
    # Test 8.2: Ruta con congestión (evitar r2 congestionado)
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_congestion(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.7, "ts": time.time()},
                "r2": {"energy": 0.1, "usage": 0.9, "ts": time.time()},  # Por encima de OCCUPANCY_LIMIT
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        inactive_routers = []
        
        pce.OCCUPANCY_LIMIT = 0.8
        pce.ROUTER_LIMIT = 0.95
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertTrue(modified)
        # Debería usar r1 en lugar de r2 congestionado
        expected_route = ["ru", "r1", "r3", "rg"]
        self.assertEqual(flows[0]["route"], expected_route)
    
    # Test 8.3: Verificar flag replace cuando flujo tiene ruta previa
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_with_existing_route(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r2": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r3": {"energy": 0.1, "usage": 0.3, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        # Flujo con ruta previa
        flows = [{"_id": "fd00:0:2::1/128", "version": 1, "route": ["ru", "r1", "r3", "rg"]}]
        inactive_routers = []
        
        # Hacer que la ruta actual sea inválida
        G.remove_edge("r1", "r3")
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertTrue(modified)
        # Verificar que se llamó con flag --replace
        mock_subprocess.assert_called_once()
        cmd_args = mock_subprocess.call_args[0][0]
        self.assertIn("--replace", cmd_args)
    
    # Test 8.4: Sin flag replace para flujo nuevo
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_new_flow_no_replace(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r2": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r3": {"energy": 0.1, "usage": 0.3, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        # Flujo sin ruta previa
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        inactive_routers = []
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertTrue(modified)
        # Verificar que NO se llamó con flag --replace
        mock_subprocess.assert_called_once()
        cmd_args = mock_subprocess.call_args[0][0]
        self.assertNotIn("--replace", cmd_args)
    
    # Test 9: Restauración de nodos inactivos
    def test_restore_inactive_nodes(self):
        G = self.create_unified_graph()
        
        flows = []
        inactive_routers = ["r1"]  # r1 estaba inactivo
        
        # Configurar router_state para que r1 ahora esté activo
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": time.time()},  # Ahora activo
                "r2": {"energy": 0.3, "usage": 0.9, "ts": time.time()},
                "r3": {"energy": 0.4, "usage": 0.6, "ts": time.time()}
            }
        
        # Llamar a la función
        G_new, flows_new, inactive_new, modified = pce.remove_inactive_nodes(G, flows, inactive_routers)
        
        # Verificar que r1 se restauró
        self.assertEqual(inactive_new, [])
        self.assertTrue(modified)
        self.assertEqual(pce.metrics["nodes_restored"], 1)
    
    # Test 10: Consumidor Kafka
    def test_kafka_consumer_thread(self):
        mock_consumer = MagicMock()
        mock_msg = MagicMock()
        
        mock_msg.value = {
            "epoch_timestamp": time.time(),
            "output_ml_metrics": [
                {"name": "node_network_power_consumption_variation_rate_occupation", "value": [0.5]}
            ],
            "input_ml_metrics": [
                {"name": "node_network_router_capacity_occupation", "value": [70.0]}
            ]
        }
        
        with patch('kafka.KafkaConsumer', return_value=mock_consumer):
            mock_consumer.__iter__.return_value = [mock_msg]
            
            pce.ENERGYAWARE = True
            pce.kafka_consumer_thread("r1")
            
            with pce.state_lock:
                self.assertTrue("r1" in pce.router_state)
                self.assertEqual(pce.router_state["r1"]["energy"], 0.5)
                self.assertEqual(pce.router_state["r1"]["usage"], 0.7)
                self.assertTrue("ts" in pce.router_state["r1"])
    
    # Test 11: Creación threads para routers intermedios
    @patch('threading.Thread')
    @patch('builtins.open', new_callable=mock_open)
    def test_start_kafka_consumers(self, mock_file, mock_thread):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        pce.start_kafka_consumers()
        
        # Solo routers intermedios (r1, r2, r3) deberían tener consumidores Kafka
        expected_calls = [
            call(target=pce.kafka_consumer_thread, args=("r1",)),
            call(target=pce.kafka_consumer_thread, args=("r2",)),
            call(target=pce.kafka_consumer_thread, args=("r3",)),
        ]
        
        mock_thread.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(mock_thread.call_count, 3)
        
        self.assertEqual(mock_thread.return_value.daemon, True)
        self.assertEqual(mock_thread.return_value.start.call_count, 3)
    
    # Test 12: Múltiples destinos (rg y rc)
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_multiple_destinations(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r2": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r3": {"energy": 0.1, "usage": 0.3, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        flows = [
            {"_id": "fd00:0:2::1/128", "version": 1},  # Destino rg
            {"_id": "fd00:0:3::1/128", "version": 1}   # Destino rc
        ]
        inactive_routers = []
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertTrue(modified)
        
        route1 = flows[0]["route"]
        route2 = flows[1]["route"]
        self.assertEqual(route1[-1], "rg")
        self.assertEqual(route2[-1], "rc")
        
        # Ambas rutas deben pasar por r3 que es el único camino a los destinos
        self.assertIn("r3", route1)
        self.assertIn("r3", route2)
    
    # Test 13: Caída de nodo modifica ruta
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_node_failure(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        
        current_time = time.time()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.3, "ts": current_time},
                "r2": {"energy": 0.1, "usage": 0.3, "ts": current_time},
                "r3": {"energy": 0.1, "usage": 0.3, "ts": current_time}
            }
        
        flows = [{"_id": "fd00:0:2::1/128", "version": 1, "route": ["ru", "r1", "r3", "rg"]}]
        inactive_routers = []
        
        # Simular caída de r1
        old_time = current_time - pce.NODE_TIMEOUT - 5
        with pce.state_lock:
            pce.router_state["r1"]["ts"] = old_time
        
        G, flows, inactive_routers, _ = pce.remove_inactive_nodes(G, flows, inactive_routers)
        
        G = pce.assign_node_costs(G)
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertTrue(modified)
        # La versión es 3 porque: 1->2 cuando se detecta el nodo caído, 2->3 cuando se recalcula
        self.assertEqual(flows[0]["version"], 3)
        new_route = flows[0]["route"]
        self.assertNotIn("r1", new_route)
        self.assertIn("r2", new_route)  # Debe usar r2 como alternativa
        # Ruta esperada: ru -> r2 -> r3 -> rg
        self.assertEqual(new_route, ["ru", "r2", "r3", "rg"])
    
    # Test 14: Balanceador de carga básico
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_load_balancing(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.2, "usage": 0.3, "ts": time.time()},  # Mayor energía
                "r2": {"energy": 0.1, "usage": 0.3, "ts": time.time()},  # Menor energía
                "r3": {"energy": 0.1, "usage": 0.3, "ts": time.time()}
            }
        
        pce.ENERGYAWARE = True
        G = pce.assign_node_costs(G)
        
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        inactive_routers = []
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        # Debería preferir r2 por menor coste energético
        route = flows[0]["route"]
        self.assertEqual(route, ["ru", "r2", "r3", "rg"])
    
    # Test 15: Fallo en enlace específico
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_specific_link_failure(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        # Simular fallo del enlace r2->r3
        G.remove_edge("r2", "r3")
        
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.3, "ts": time.time()},  # Mayor energía
                "r2": {"energy": 0.1, "usage": 0.3, "ts": time.time()},  # Menor energía pero sin enlace
                "r3": {"energy": 0.1, "usage": 0.3, "ts": time.time()}
            }
        
        pce.ENERGYAWARE = True
        G = pce.assign_node_costs(G)
        
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        inactive_routers = []
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        # Debe usar r1 porque r2 no puede llegar a r3
        route = flows[0]["route"]
        self.assertEqual(route, ["ru", "r1", "r3", "rg"])
        self.assertNotIn("r2", route)
    
    # Test 16: Flujo con alta ocupación
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_flow_exceeding_first_threshold_warning(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.92, "ts": time.time()},  # Entre umbrales
                "r2": {"energy": 0.1, "usage": 0.91, "ts": time.time()},  # Entre umbrales
                "r3": {"energy": 0.1, "usage": 0.3, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        inactive_routers = []
        
        with patch('builtins.print') as mock_print:
            flows, modified = pce.recalc_routes(G, flows, inactive_routers)
            
            aviso_impreso = False
            for call in mock_print.call_args_list:
                if "AVISO" in str(call) and "ocupación entre" in str(call):
                    aviso_impreso = True
                    break
            self.assertTrue(aviso_impreso)
        
        mock_subprocess.assert_called_once()
        cmd_args = mock_subprocess.call_args[0][0]
        self.assertIn("--high-occupancy", cmd_args)
    
    # Test 17: Sin flujos
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_no_flows(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        
        flows = []
        inactive_routers = []
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertFalse(modified)
        self.assertEqual(len(flows), 0)
        
        mock_subprocess.assert_not_called()
    
    # Test 18: Sin ruta por congestión extrema
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_no_path_congestion(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.96, "ts": time.time()},  # Por encima de ROUTER_LIMIT
                "r2": {"energy": 0.1, "usage": 0.98, "ts": time.time()},  # Por encima de ROUTER_LIMIT
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        inactive_routers = []
        
        pce.OCCUPANCY_LIMIT = 0.8
        pce.ROUTER_LIMIT = 0.95
        
        # Remover r1 y r2 del grafo para simular que están bloqueados por congestión
        G.remove_node("r1")
        G.remove_node("r2")
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        self.assertFalse(modified)
        self.assertEqual(flows[0]["version"], 1)
        self.assertFalse("route" in flows[0])
    
    # Test 19: Ruta existente válida (no necesita recálculo)
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_valid_existing_route(self, mock_file, mock_subprocess):
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        G = pce.create_graph()
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r2": {"energy": 0.1, "usage": 0.3, "ts": time.time()},
                "r3": {"energy": 0.1, "usage": 0.3, "ts": time.time()}
            }
        G = pce.assign_node_costs(G)
        
        # Flujo con ruta válida existente
        flows = [{"_id": "fd00:0:2::1/128", "version": 1, "route": ["ru", "r1", "r3", "rg"]}]
        inactive_routers = []
        
        flows, modified = pce.recalc_routes(G, flows, inactive_routers)
        
        # No debe modificar nada si la ruta es válida
        self.assertFalse(modified)
        self.assertEqual(flows[0]["version"], 1)
        self.assertEqual(flows[0]["route"], ["ru", "r1", "r3", "rg"])
        
        mock_subprocess.assert_not_called()


if __name__ == '__main__':
    unittest.main()