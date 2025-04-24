# tests_mynetworkx.py

import os
import sys
import types
import time
import pytest
import networkx as nx

# Definición del entorno de prueba y variables minimas para realizar pruebas sin acceso a S3
os.environ.setdefault('S3_ENDPOINT', '')
os.environ.setdefault('S3_ACCESS_KEY', '')
os.environ.setdefault('S3_SECRET_KEY', '')
os.environ.setdefault('S3_BUCKET', 'test-bucket')

mod_kafka = types.ModuleType('kafka')
mod_kafka.KafkaConsumer = lambda *args, **kwargs: None
sys.modules['kafka'] = mod_kafka

class DummyS3Client:
    def __init__(self, *args, **kwargs):
        pass
    def head_bucket(self, Bucket):
        return None
    def list_objects_v2(self, Bucket, Prefix=None):
        return {}  # Simula carpeta vacía
    def put_object(self, Bucket, Key=None, Body=None):
        return None
    def get_object(self, Bucket, Key):
        # Simula un objeto con cuerpo vacío de flows
        body = types.SimpleNamespace(read=lambda: b'{"flows": []}')
        return {'Body': body}

mod_boto3 = types.ModuleType('boto3')
mod_boto3.client = lambda *args, **kwargs: DummyS3Client()
sys.modules['boto3'] = mod_boto3

mod_botocore = types.ModuleType('botocore')
mod_botocore.exceptions = types.SimpleNamespace(ClientError=Exception)
sys.modules['botocore'] = mod_botocore
sys.modules['botocore.exceptions'] = mod_botocore.exceptions

# Importar el módulo a probar
from mynetworkx import (
    remove_inactive_nodes,
    assign_node_costs,
    recalc_routes,
    router_state,
    state_lock,
    OCCUPANCY_LIMIT,
    ROUTER_LIMIT,
    NODE_TIMEOUT
)

# Helper para inyectar estado en router_state
def set_router_state(state_dict):
    with state_lock:
        router_state.clear()
        for k, v in state_dict.items():
            router_state[k] = v

@pytest.fixture(autouse=True)
def reset_router_state():
    set_router_state({})
    yield
    set_router_state({})

# Grafos de ejemplo

def create_linear_graph():
    G = nx.DiGraph()
    G.add_nodes_from(["ru", "r1", "r2", "rg"])
    G.add_edge("ru", "r1", cost=1)
    G.add_edge("r1", "r2", cost=1)
    G.add_edge("r2", "rg", cost=1)
    return G

def create_square_graph():
    G = nx.DiGraph()
    G.add_nodes_from(["ru", "r1", "r2", "rg"])
    G.add_edge("ru", "r1", cost=1)
    G.add_edge("r1", "rg", cost=1)
    G.add_edge("ru", "r2", cost=1)
    G.add_edge("r2", "rg", cost=1)
    return G

# 1. Nodo activo, sin flujos afectados
def test_remove_inactive_nodes_sin_remociones():
    now = time.time()
    set_router_state({"r1": {"ts": now, "energy": 5, "usage": 0.2}})
    G = create_linear_graph()
    flows = [{"_id": "1", "version": 1, "route": ["ru", "r1", "r2", "rg"]}]
    G2, flows2, removed, modified = remove_inactive_nodes(G, flows)
    assert removed == []
    assert not modified
    assert nx.has_path(G2, "ru", "rg")

# 2. Nodo inactivo y reasignación via r2 con versión actualizada

def test_remove_inactive_nodes_and_reassign_route_on_inactive_node():
    import time
    # Simula r1 inactivo y r2 activo
    old_ts = time.time() - (NODE_TIMEOUT + 1)
    fresh_ts = time.time()
    set_router_state({
        "r1": {"ts": old_ts, "energy": 5, "usage": 0.2},
        "r2": {"ts": fresh_ts, "energy": 3, "usage": 0.2}
    })
    # Grafo cuadrado con dos rutas posibles: ru→r1→rg y ru→r2→rg
    G = create_square_graph()
    # Flujo inicial asignado vía r1
    flows = [{"_id": "2", "version": 1, "route": ["ru", "r1", "rg"]}]

    # 2.1 Eliminación de r1 y aumento de versión
    G2, flows2, removed, mod1 = remove_inactive_nodes(G, flows)
    assert removed == ["r1"]
    assert mod1 is True
    assert "route" not in flows2[0]
    assert flows2[0]["version"] == 2

    # 2.2 Reasignación de ruta tras la eliminación
    G_costed = assign_node_costs(G2)
    flows3, mod2 = recalc_routes(G_costed, flows2, removed)
    assert mod2 is True
    # Ahora solo puede ir vía r2
    assert flows3[0]["route"] == ["ru", "r2", "rg"]
    # La versión permanece en 2 tras la reasignación
    assert flows3[0]["version"] == 2


# 3. Selección de ruta de menor coste en grafo con dos caminos
def test_recalc_routes_multiple_paths_elige_camino_mas_barato():
    now = time.time()
    set_router_state({
        "r1": {"ts": now, "energy": 2, "usage": 0.1},
        "r2": {"ts": now, "energy": 5, "usage": 0.1}
    })
    G = create_square_graph()
    flows = [{"_id": "3", "version": 1}]
    G_costed = assign_node_costs(G)
    flows2, modified = recalc_routes(G_costed, flows, removed=[])
    assert modified
    assert flows2[0]["route"] == ["ru", "r1", "rg"]

# 4. Cálculo de rutas dentro de umbrales
def test_recalc_routes_bajo_umbrales():
    now = time.time()
    set_router_state({
        "r1": {"ts": now, "energy": 1, "usage": OCCUPANCY_LIMIT - 0.1},
        "r2": {"ts": now, "energy": 1, "usage": OCCUPANCY_LIMIT - 0.1}
    })
    G = create_linear_graph()
    flows = [{"_id": "4", "version": 1}]
    flows2, modified = recalc_routes(assign_node_costs(G), flows, removed=[])
    assert modified
    assert flows2[0]["route"] == ["ru", "r1", "r2", "rg"]

# 5. Cálculo con sobrepaso primer umbral pero dentro del segundo
def test_recalc_routes_entre_umbrales():
    now = time.time()
    set_router_state({
        "r1": {"ts": now, "energy": 1, "usage": OCCUPANCY_LIMIT + 0.05},
        "r2": {"ts": now, "energy": 1, "usage": ROUTER_LIMIT - 0.05}
    })
    G = create_linear_graph()
    flows = [{"_id": "5", "version": 1}]
    flows2, modified = recalc_routes(assign_node_costs(G), flows, removed=[])
    assert modified
    assert flows2[0]["route"] == ["ru", "r1", "r2", "rg"]

# 6. No hay ruta posible (todos superan segundo umbral)
def test_recalc_routes_sin_ruta():
    now = time.time()
    set_router_state({
        "r1": {"ts": now, "energy": 1, "usage": ROUTER_LIMIT + 0.01},
        "r2": {"ts": now, "energy": 1, "usage": ROUTER_LIMIT + 0.01}
    })
    G = create_linear_graph()
    flows = [{"_id": "6", "version": 1}]
    flows2, modified = recalc_routes(assign_node_costs(G), flows, removed=[])
    assert not modified
    assert "route" not in flows2[0]
