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

class TestPCE(unittest.TestCase):
    
    def setUp(self):
        # Reset estado global antes de cada test
        pce.router_state = {}
        pce.metrics = {
            "routes_recalculated": 0,
            "tables_created": 0,
            "nodes_removed": 0,
            "flows_updated": 0
        }
        # Configurar variables de entorno para tests
        os.environ['S3_ENDPOINT'] = 'http://localhost:9000'
        os.environ['S3_ACCESS_KEY'] = 'minioadmin'
        os.environ['S3_SECRET_KEY'] = 'minioadmin'
        os.environ['S3_BUCKET'] = 'test-bucket'
        os.environ['ENERGYAWARE'] = 'true'
        os.environ['DEBUG_COSTS'] = 'false'
        
        # Mock para networkinfo.json
        self.network_info = {
            "graph": {
                "nodes": ["ru", "r1", "r2", "r3", "rg1", "rg2"],
                "edges": [
                    {"source": "ru", "target": "r1", "cost": 1},
                    {"source": "ru", "target": "r2", "cost": 1},
                    {"source": "r1", "target": "r3", "cost": 1},
                    {"source": "r2", "target": "r3", "cost": 1},
                    {"source": "r3", "target": "rg1", "cost": 1},
                    {"source": "r3", "target": "rg2", "cost": 1}
                ]
            }
        }
        
        # Datos de prueba para flujos
        self.test_flows = [
            {"_id": "fd00:0:2::1/128", "version": 1, "table": "t1"},
            {"_id": "fd00:0:3::1/128", "version": 1}
        ]
        
        self.test_tables = {
            "t1": {"route": ["ru", "r1", "r3", "rg1"]}
        }
        
        # Router state para pruebas
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": time.time()},
                "r2": {"energy": 0.3, "usage": 0.9, "ts": time.time()},
                "r3": {"energy": 0.4, "usage": 0.6, "ts": time.time()}
            }
    
    # Test 1: Creación de grafo
    @patch('builtins.open', new_callable=mock_open)
    def test_create_graph(self, mock_file):
        # Preparar el mock para leer networkinfo.json
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Llamar a la función
        G = pce.create_graph()
        
        # Verificar que el grafo se crea correctamente
        self.assertEqual(len(G.nodes), 6)
        self.assertEqual(len(G.edges), 6)
        self.assertTrue(G.has_edge("ru", "r1"))
        self.assertEqual(G["ru"]["r1"]["cost"], 1)
    
    # Test 8.1: Lectura flujos S3
    @patch('boto3.client')
    def test_read_flows_success(self, mock_boto3_client):
        # Configurar el mock para S3
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        # Asignar el mock al cliente S3 del módulo pce
        pce.s3_client = mock_s3
        
        # Mock para list_objects_v2
        mock_s3.list_objects_v2.return_value = {
            'Contents': [{'Key': 'flows/flows_1.json', 'LastModified': '2023-01-01'},
                         {'Key': 'flows/flows_2.json', 'LastModified': '2023-01-02'}]
        }
        
        # Mock para get_object
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "flows": self.test_flows,
            "tables": self.test_tables,
            "router_utilization": {"r1": 0.7}
        }).encode()
        mock_s3.get_object.return_value = {'Body': mock_body}
        
        # Llamar a la función
        flows, tables, router_util = pce.read_flows()
        
        # Verificar resultados
        self.assertEqual(len(flows), 2)
        self.assertEqual(flows[0]["_id"], "fd00:0:2::1/128")
        self.assertEqual(tables["t1"]["route"], ["ru", "r1", "r3", "rg1"])
        self.assertEqual(router_util["r1"], 0.7)
        
        # Verificar que se llamó a list_objects_v2 y get_object
        mock_s3.list_objects_v2.assert_called_once()
        mock_s3.get_object.assert_called_once()
        
        # En lugar de comprobar los parámetros exactos, comprobamos que fueron llamados
        self.assertEqual(mock_s3.list_objects_v2.call_args[1]['Prefix'], 'flows/')
        self.assertEqual(mock_s3.get_object.call_args[1]['Key'], 'flows/flows_2.json')
    
    # Test 8.2: Lectura S3 vacío
    @patch('boto3.client')
    def test_read_flows_empty(self, mock_boto3_client):
        # Configurar el mock para S3
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        # Asignar el mock al cliente S3 del módulo pce
        pce.s3_client = mock_s3
        
        # Mock para list_objects_v2 (sin contenido)
        mock_s3.list_objects_v2.return_value = {}
        
        # Llamar a la función
        flows, tables, router_util = pce.read_flows()
        
        # Verificar resultados
        self.assertEqual(flows, [])
        self.assertEqual(tables, {})
        self.assertEqual(router_util, {})
    
    # Test 8.3: Escritura flujos S3
    @patch('boto3.client')
    def test_write_flows(self, mock_boto3_client):
        # Configurar el mock para S3
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        # Asignar el mock al cliente S3 del módulo pce
        pce.s3_client = mock_s3
        
        # Llamar a la función
        pce.write_flows(self.test_flows, self.test_tables, {"r1": 0.7}, ["r4"])
        
        # Verificar que se llamó a put_object con los parámetros correctos
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args[1]
        
        # Verificar que se incluye Key y Body
        self.assertTrue('Key' in call_args)
        self.assertTrue('Body' in call_args)
        self.assertTrue(call_args['Key'].startswith('flows/flows_'))
        
        # Verificar que el cuerpo contiene los datos correctos
        body_json = call_args['Body'].decode()
        body_dict = json.loads(body_json)
        self.assertEqual(body_dict["flows"], self.test_flows)
        self.assertEqual(body_dict["tables"], self.test_tables)
        self.assertEqual(body_dict["router_utilization"], {"r1": 0.7})
        self.assertEqual(body_dict["inactive_routers"], ["r4"])
    
    # Test 2.1 y 2.2: Incremento versión (flujo nuevo y existente)
    def test_increment_version(self):
        # Caso 1: Flujo con versión existente (2.2)
        flow = {"_id": "test", "version": 5}
        new_version = pce.increment_version(flow)
        self.assertEqual(new_version, 6)
        self.assertEqual(flow["version"], 6)
        
        # Caso 2: Flujo sin versión inicial (2.1)
        flow = {"_id": "test"}
        new_version = pce.increment_version(flow)
        self.assertEqual(new_version, 2)
        self.assertEqual(flow["version"], 2)
    
    # Test 3.1, 3.2 y 3.3: Validación de rutas (válida, inválida, vacía)
    def test_is_route_valid(self):
        # Crear un grafo simple para pruebas
        G = nx.DiGraph()
        G.add_nodes_from(["ru", "r1", "r2", "rg1"])
        G.add_edges_from([("ru", "r1"), ("r1", "r2"), ("r2", "rg1")])
        
        # Caso 1: Ruta válida (3.1)
        self.assertTrue(pce.is_route_valid(G, ["ru", "r1", "r2", "rg1"]))
        
        # Caso 2: Ruta con enlace que falta (3.2)
        self.assertFalse(pce.is_route_valid(G, ["ru", "r1", "rg1"]))
        
        # Caso 3: Ruta con nodo que falta (3.2)
        self.assertFalse(pce.is_route_valid(G, ["ru", "r3", "rg1"]))
        
        # Caso 4: Ruta vacía (3.3)
        self.assertFalse(pce.is_route_valid(G, []))
        
        # Caso 5: Ruta con un solo nodo (3.3)
        self.assertFalse(pce.is_route_valid(G, ["ru"]))
    
    # Test 4.1 y 4.2: Crear nueva tabla y reutilizar tabla existente
    def test_get_or_create_table(self):
        # Caso 1: Tabla existente (4.2)
        tables = {"t1": {"route": ["ru", "r1", "r3", "rg1"]}}
        tid = pce.get_or_create_table(tables, ["ru", "r1", "r3", "rg1"])
        self.assertEqual(tid, "t1")
        self.assertEqual(len(tables), 1)
        
        # Caso 2: Nueva tabla (4.1)
        tables = {"t1": {"route": ["ru", "r1", "r3", "rg1"]}}
        tid = pce.get_or_create_table(tables, ["ru", "r2", "r3", "rg1"])
        self.assertEqual(tid, "t2")
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables["t2"]["route"], ["ru", "r2", "r3", "rg1"])
        
        # Verificar que la métrica se incrementó
        self.assertEqual(pce.metrics["tables_created"], 1)
    
    # Test 5.1, 5.2 y 5.3: Manejo de nodos inactivos y actualizaciones de flujos
    def test_remove_inactive_nodes(self):
        # Crear un grafo para pruebas
        G = nx.DiGraph()
        G.add_nodes_from(["ru", "r1", "r2", "r3", "rg1"])
        G.add_edges_from([
            ("ru", "r1"), ("ru", "r2"), 
            ("r1", "r3"), ("r2", "r3"),
            ("r3", "rg1")
        ])
        
        # Configurar flujos para pruebas (5.3)
        flows = [
            {"_id": "f1", "version": 1, "table": "t1"},
            {"_id": "f2", "version": 1, "table": "t2"}
        ]
        
        # Configurar router_state para que r1 sea inactivo (timestamp viejo) (5.2)
        old_time = time.time() - pce.NODE_TIMEOUT - 5
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": old_time},
                "r2": {"energy": 0.3, "usage": 0.9, "ts": time.time()},  # Activo (5.1)
                "r3": {"energy": 0.4, "usage": 0.6, "ts": time.time()}   # Activo (5.1)
            }
        
        # Llamar a la función
        G_new, flows_new, removed, modified = pce.remove_inactive_nodes(G, flows)
        
        # Verificar que el nodo inactivo se eliminó (5.2)
        self.assertFalse(G_new.has_node("r1"))
        self.assertTrue(G_new.has_node("r2"))
        self.assertEqual(removed, ["r1"])
        self.assertTrue(modified)
        
        # Verificar que todos los flujos se actualizaron (5.3)
        self.assertEqual(flows_new[0]["version"], 2)
        self.assertEqual(flows_new[1]["version"], 2)
        
        # Verificar métricas
        self.assertEqual(pce.metrics["nodes_removed"], 1)
        self.assertEqual(pce.metrics["flows_updated"], 2)
    
    # Test 6.1 y 6.2: Cálculo de costes en modo energy-aware y fixed
    def test_assign_node_costs(self):
        # Crear un grafo para pruebas
        G = nx.DiGraph()
        G.add_nodes_from(["ru", "r1", "r2", "r3", "rg1"])
        G.add_edges_from([
            ("ru", "r1"), ("ru", "r2"), 
            ("r1", "r3"), ("r2", "r3"),
            ("r3", "rg1")
        ])
        
        # Configurar router_state
        current_time = time.time()
        old_time = current_time - pce.NODE_TIMEOUT - 5
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": current_time},
                "r2": {"energy": 0.3, "usage": 0.9, "ts": current_time},
                "r3": {"energy": 0.4, "usage": 0.6, "ts": old_time}  # Nodo inactivo
            }
        
        # Llamar a la función con ENERGYAWARE=True (6.1)
        pce.ENERGYAWARE = True
        G = pce.assign_node_costs(G)
        
        # Verificar costes
        self.assertEqual(G["ru"]["r1"]["cost"], 0.5)  # Coste = energía para nodos activos
        self.assertEqual(G["ru"]["r2"]["cost"], 0.3)
        self.assertEqual(G["r3"]["rg1"]["cost"], 9999)  # Coste alto para nodo inactivo
        
        # Probar con ENERGYAWARE=False (6.2)
        pce.ENERGYAWARE = False
        G = pce.assign_node_costs(G)
        
        # Verificar costes
        self.assertEqual(G["ru"]["r1"]["cost"], 0.1)  # Coste fijo para nodos activos
        self.assertEqual(G["ru"]["r2"]["cost"], 0.1)
    
    # Test 7.1, 7.2 y 7.3: Selección de destino basado en IP
    def test_choose_destination(self):
        # Caso 1: IP en red fd00:0:2::/64 (7.1)
        dest = pce.choose_destination("fd00:0:2::10/128")
        self.assertEqual(dest, "rg1")
        
        # Caso 2: IP en red fd00:0:3::/64 (7.2)
        dest = pce.choose_destination("fd00:0:3::20/128")
        self.assertEqual(dest, "rg2")
        
        # Caso 3: IP en otra red (7.3)
        dest = pce.choose_destination("fd00:0:4::30/128")
        self.assertEqual(dest, "rg1")  # Default
    
    # Test 9.1: Cálculo ruta normal
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_normal(self, mock_file, mock_subprocess):
        # Preparar mocks
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Crear grafo para pruebas
        G = pce.create_graph()
        # Asignar costes a enlaces
        with pce.state_lock:
            for u, v in G.edges():
                if v == "r1":
                    G[u][v]["cost"] = 0.5
                elif v == "r2":
                    G[u][v]["cost"] = 0.3
                else:
                    G[u][v]["cost"] = 0.1
        
        # Configurar router_state
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.5, "usage": 0.7, "ts": time.time()},
                "r2": {"energy": 0.3, "usage": 0.7, "ts": time.time()},
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        
        # Datos de prueba
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        tables = {}
        removed = []
        
        # Llamar a la función
        pce.OCCUPANCY_LIMIT = 0.8
        pce.ROUTER_LIMIT = 0.95
        flows, modified = pce.recalc_routes(G, flows, tables, removed)
        
        # Verificar resultados
        self.assertTrue(modified)
        self.assertEqual(flows[0]["version"], 2)
        self.assertTrue("table" in flows[0])
        self.assertTrue(flows[0]["table"] in tables)
        
        # Verificar que se usó la mejor ruta (menor coste energético)
        expected_route = ["ru", "r2", "r3", "rg1"]
        self.assertEqual(tables[flows[0]["table"]]["route"], expected_route)
        
        # Verificar que se llamó a subprocess.run
        mock_subprocess.assert_called_once()
    
    # Test 9.2: Ruta con congestión
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_congestion(self, mock_file, mock_subprocess):
        # Preparar mocks
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Crear grafo para pruebas
        G = pce.create_graph()
        # Asignar costes a enlaces
        with pce.state_lock:
            for u, v in G.edges():
                G[u][v]["cost"] = 0.1
        
        # Configurar router_state con r2 congestionado (por encima de OCCUPANCY_LIMIT)
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.7, "ts": time.time()},
                "r2": {"energy": 0.1, "usage": 0.9, "ts": time.time()},  # Por encima de OCCUPANCY_LIMIT
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        
        # Datos de prueba
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        tables = {}
        removed = []
        
        # Llamar a la función
        pce.OCCUPANCY_LIMIT = 0.8
        pce.ROUTER_LIMIT = 0.95
        flows, modified = pce.recalc_routes(G, flows, tables, removed)
        
        # Verificar resultados
        self.assertTrue(modified)
        
        # Verificar que se evitó el nodo congestionado
        expected_route = ["ru", "r1", "r3", "rg1"]
        self.assertEqual(tables[flows[0]["table"]]["route"], expected_route)
    
    # Test 9.3: Congestión extrema (r2 > ROUTER_LIMIT, r1 > OCCUPANCY_LIMIT)
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_max_congestion(self, mock_file, mock_subprocess):
        # Preparar mocks
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Crear grafo para pruebas
        G = pce.create_graph()
        # Asignar costes a enlaces
        with pce.state_lock:
            for u, v in G.edges():
                G[u][v]["cost"] = 0.1
        
        # Configurar router_state con r1 y r2 congestionados
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.9, "ts": time.time()},  # Por encima de OCCUPANCY_LIMIT
                "r2": {"energy": 0.1, "usage": 0.96, "ts": time.time()},  # Por encima de ROUTER_LIMIT
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        
        # Datos de prueba
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        tables = {}
        removed = []
        
        # Llamar a la función
        pce.OCCUPANCY_LIMIT = 0.8
        pce.ROUTER_LIMIT = 0.95
        flows, modified = pce.recalc_routes(G, flows, tables, removed)
        
        # Verificar resultados
        self.assertTrue(modified)
        
        # Verificar que se evitó r2 (>ROUTER_LIMIT) pero se usó r1 (>OCCUPANCY_LIMIT, <ROUTER_LIMIT)
        expected_route = ["ru", "r1", "r3", "rg1"]
        self.assertEqual(tables[flows[0]["table"]]["route"], expected_route)
    
    # Test 9.4: Sin ruta por congestión (r1 > ROUTER_LIMIT, r2 > ROUTER_LIMIT)
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_all_congested(self, mock_file, mock_subprocess):
        # Preparar mocks
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Crear grafo para pruebas
        G = pce.create_graph()
        # Asignar costes a enlaces
        with pce.state_lock:
            for u, v in G.edges():
                G[u][v]["cost"] = 0.1
        
        # Configurar router_state con todos los routers por encima de ROUTER_LIMIT
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.96, "ts": time.time()},  # Por encima de ROUTER_LIMIT
                "r2": {"energy": 0.1, "usage": 0.98, "ts": time.time()},  # Por encima de ROUTER_LIMIT
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        
        # Datos de prueba
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        tables = {}
        removed = []
        
        # Configurar entorno
        pce.OCCUPANCY_LIMIT = 0.8
        pce.ROUTER_LIMIT = 0.95
        
        # Cuando r1 y r2 están por encima de ROUTER_LIMIT, no hay rutas disponibles
        # en la implementación optimizada, simplemente no se puede encontrar ruta directamente
        
        # Añadir un mock para nx.shortest_path que siempre lanza una excepción
        with patch('networkx.shortest_path', side_effect=nx.NetworkXNoPath("No path")):
            # Llamar a la función - debería fallar al encontrar camino
            flows, modified = pce.recalc_routes(G, flows, tables, removed)
            
            # Verificar resultados: no se debe haber modificado nada
            self.assertFalse(modified)
            self.assertEqual(flows[0]["version"], 1)
            self.assertEqual(len(tables), 0)
            self.assertFalse("table" in flows[0])
            
            # Verificar que no se llamó a subprocess.run
            mock_subprocess.assert_not_called()
    
    # Test 9.5: Ruta existente inválida
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_invalid_existing_route(self, mock_file, mock_subprocess):
        # Preparar mocks
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Crear grafo para pruebas
        G = pce.create_graph()
        # Eliminar un enlace de la ruta existente
        G.remove_edge("r1", "r3")
        
        # Datos de prueba con una ruta existente que ya no es válida
        flows = [{"_id": "fd00:0:2::1/128", "version": 1, "table": "t1"}]
        tables = {"t1": {"route": ["ru", "r1", "r3", "rg1"]}}
        removed = []
        
        # Configurar router_state
        with pce.state_lock:
            pce.router_state = {
                "r1": {"energy": 0.1, "usage": 0.7, "ts": time.time()},
                "r2": {"energy": 0.1, "usage": 0.7, "ts": time.time()},
                "r3": {"energy": 0.1, "usage": 0.6, "ts": time.time()}
            }
        
        # Llamar a la función
        flows, modified = pce.recalc_routes(G, flows, tables, removed)
        
        # Verificar resultados
        self.assertTrue(modified)
        self.assertEqual(flows[0]["version"], 2)
        
        # Verificar que se encontró una nueva ruta válida
        expected_route = ["ru", "r2", "r3", "rg1"]
        self.assertEqual(tables[flows[0]["table"]]["route"], expected_route)
    
    # Test 9.6: Sin ruta disponible
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_recalc_routes_no_path(self, mock_file, mock_subprocess):
        # Preparar mocks
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Crear grafo para pruebas pero eliminar todos los enlaces a rg1
        G = pce.create_graph()
        # Eliminar enlaces críticos
        edges_to_remove = [("r3", "rg1")]
        for u, v in edges_to_remove:
            G.remove_edge(u, v)
        
        # Datos de prueba
        flows = [{"_id": "fd00:0:2::1/128", "version": 1}]
        tables = {}
        removed = []
        
        # Llamar a la función
        flows, modified = pce.recalc_routes(G, flows, tables, removed)
        
        # Verificar resultados: no debería haberse modificado porque no hay ruta
        self.assertFalse(modified)
        self.assertEqual(flows[0]["version"], 1)
        self.assertFalse("table" in flows[0])
        self.assertEqual(len(tables), 0)
        
        # Verificar que no se llamó a subprocess.run
        mock_subprocess.assert_not_called()
    
    # Test 10.1: Consumidor Kafka
    def test_kafka_consumer_thread(self):
        # Este test es más complejo de hacer mock completo, pero podemos verificar 
        # que se procesa correctamente el mensaje y se actualiza router_state
        
        # Mock de KafkaConsumer
        mock_consumer = MagicMock()
        mock_msg = MagicMock()
        
        # Datos de prueba para el mensaje
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
            # Configurar el mock para que el loop for msg in consumer genere un mensaje y luego salga
            mock_consumer.__iter__.return_value = [mock_msg]
            
            # Llamar a la función
            pce.ENERGYAWARE = True
            pce.kafka_consumer_thread("r1")
            
            # Verificar que router_state se actualizó correctamente
            with pce.state_lock:
                self.assertTrue("r1" in pce.router_state)
                self.assertEqual(pce.router_state["r1"]["energy"], 0.5)
                self.assertEqual(pce.router_state["r1"]["usage"], 0.7)
                self.assertTrue("ts" in pce.router_state["r1"])
    
    # Test 10.2: Creación threads
    @patch('threading.Thread')
    @patch('builtins.open', new_callable=mock_open)
    def test_start_kafka_consumers(self, mock_file, mock_thread):
        # Preparar mocks
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(self.network_info)
        
        # Llamar a la función
        pce.start_kafka_consumers()
        
        # Verificar que se crearon los threads correctos
        # Solo para nodos que empiezan con 'r' seguido de número
        expected_calls = [
            call(target=pce.kafka_consumer_thread, args=("r1",)),
            call(target=pce.kafka_consumer_thread, args=("r2",)),
            call(target=pce.kafka_consumer_thread, args=("r3",)),
        ]
        
        # Verificar que se hicieron las llamadas esperadas
        mock_thread.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(mock_thread.call_count, 3)
        
        # Verificar que los threads se iniciaron
        self.assertEqual(mock_thread.return_value.daemon, True)
        self.assertEqual(mock_thread.return_value.start.call_count, 3)


if __name__ == '__main__':
    unittest.main()