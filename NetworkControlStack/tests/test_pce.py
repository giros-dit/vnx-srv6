import pytest
import json
import time
import networkx as nx
from unittest.mock import MagicMock

import pce

class DummyBody:
    def __init__(self, content):
        self._content = content
    def read(self):
        return self._content


def test_choose_destination():
    assert pce.choose_destination('fd00:0:2::1/64') == 'rg1'
    assert pce.choose_destination('fd00:0:3::1/64') == 'rg2'
    assert pce.choose_destination('2001:db8::1/64') == 'rg1'


def test_remove_inactive_nodes(monkeypatch):
    # Preparar grafo y flujo
    G = nx.DiGraph()
    G.add_nodes_from(['r1', 'r2'])
    flows = [ {'route': ['r1'], 'version': 1}, {'route': ['r2'], 'version': 1} ]

    # Simular tiempos
    base = 1000
    monkeypatch.setattr(pce, 'NODE_TIMEOUT', 10)
    monkeypatch.setattr(time, 'time', lambda: base + 20)
    with pce.state_lock:
        pce.router_state.clear()
        pce.router_state['r1'] = {'ts': base - 1}
        pce.router_state['r2'] = {'ts': base + 5}

    G2, flows2, removed, modified = pce.remove_inactive_nodes(G.copy(), flows.copy())
    assert 'r1' in removed
    assert 'r1' not in G2.nodes()
    # El flujo asociado a r1 pierde ruta y se incrementa versión
    assert 'route' not in flows2[0]
    assert flows2[0]['version'] == 2
    assert modified is True


def test_assign_node_costs(monkeypatch):
    G = nx.DiGraph()
    G.add_edge('u', 'v', cost=0)
    base = 1000
    monkeypatch.setattr(time, 'time', lambda: base)
    with pce.state_lock:
        pce.router_state.clear()
        pce.router_state['v'] = {'ts': base, 'energy': 5.0}

    G2 = pce.assign_node_costs(G.copy())
    assert G2['u']['v']['cost'] == 5.0

    # Simular stale
    monkeypatch.setattr(time, 'time', lambda: base + pce.NODE_TIMEOUT + 1)
    G3 = pce.assign_node_costs(G.copy())
    assert G3['u']['v']['cost'] == 9999


def test_recalc_routes(monkeypatch):
    # Grafo simple ru -> rg1
    G = nx.DiGraph()
    G.add_edge('ru', 'rg1', cost=1)
    flows = [{'_id': 'fd00:0:2::1/64'}]
    tables = {}
    removed = []
    fake_run = MagicMock()
    monkeypatch.setattr(pce.subprocess, 'run', fake_run)

    new_flows, modified = pce.recalc_routes(G, flows, tables, removed)
    assert modified is True
    assert new_flows[0]['route'] == ['ru', 'rg1']
    assert 'table' in new_flows[0]
    assert new_flows[0]['table'] in tables
    fake_run.assert_called_once()


def test_create_graph(tmp_path, monkeypatch):
    data = {"graph": {"nodes": ["a", "b"], "edges": [{"source": "a", "target": "b", "cost": 3}]}}
    (tmp_path / "networkinfo.json").write_text(json.dumps(data))
    monkeypatch.chdir(tmp_path)

    G = pce.create_graph()
    assert set(G.nodes()) == {"a", "b"}
    assert G['a']['b']['cost'] == 3


def test_read_flows_empty(monkeypatch):
    monkeypatch.setattr(pce.s3_client, 'list_objects_v2', lambda Bucket, Prefix: {})
    flows = pce.read_flows()
    assert flows == []


def test_read_flows_dict_and_list(monkeypatch):
    contents = [{'Key': 'flows/1', 'LastModified': 1}, {'Key': 'flows/2', 'LastModified': 2}]
    monkeypatch.setattr(pce.s3_client, 'list_objects_v2', lambda Bucket, Prefix: {'Contents': contents})
    dummy_dict = {"flows": [{'_id': '1'}]}
    monkeypatch.setattr(pce.s3_client, 'get_object', lambda Bucket, Key: {'Body': DummyBody(json.dumps(dummy_dict).encode())})

    flows = pce.read_flows()
    assert isinstance(flows, list)
    assert flows == dummy_dict['flows']


def test_write_flows(monkeypatch):
    calls = []
    monkeypatch.setattr(pce.s3_client, 'put_object', lambda Bucket, Key, Body: calls.append((Bucket, Key, Body)))
    sample = [{'_id': 'x'}]
    pce.write_flows(sample, [], {})
    assert calls
    bucket, key, body = calls[0]
    assert bucket == pce.S3_BUCKET
    assert key.startswith("flows/flows_")
    assert b'"_id": "x"' in body
