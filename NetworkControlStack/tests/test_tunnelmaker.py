import pytest
import json
import os
import sys
from subprocess import CompletedProcess
import tunnelmaker


def test_determine_method_no_routers():
    assert tunnelmaker.determine_method(1, []) == "delete"

def test_determine_method_add():
    assert tunnelmaker.determine_method(1, ["r1"]) == "add"

def test_determine_method_replace():
    assert tunnelmaker.determine_method(2, ["r1"]) == "replace"

def test_createupf_with_routers():
    flowid = 1
    extremos = {"origen": "ru", "destinos": ["d1", "d2"]}
    method = "add"
    id_to_ip = {"r1": "fe80::2", "rg": "fe80::3"}
    routersid = ["ru", "r1", "rg"]
    cmd = tunnelmaker.createupf(flowid, extremos, method, id_to_ip, routersid)
    assert "ip -6 route add" in cmd
    assert "segs fe80::2,fe80::3" in cmd

def test_createupf_no_routers_raises():
    # Con routersid = [], el código actual lanza TypeError
    with pytest.raises(TypeError):
        tunnelmaker.createupf(
            flowid=1,
            extremos={"origen": "ru", "destinos": []},
            method="delete",
            id_to_ip={},
            routersid=[]
        )

def test_main_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["tunnelmaker.py"])
    with pytest.raises(SystemExit) as se:
        tunnelmaker.main()
    assert se.value.code == 1
    out = capsys.readouterr().out
    assert "Uso: python tunnelmaker.py" in out

def test_main_success(monkeypatch, tmp_path, capsys):
    # Creamos un final_output.json de prueba
    data = {"loopbacks": {}, "extremos": {"origen": "ru", "destinos": ["d1"]}}
    file_path = tmp_path / "final_output.json"
    file_path.write_text(json.dumps(data))

    # Forzamos dirname para que busque en tmp_path
    monkeypatch.setattr(os.path, "dirname", lambda _: str(tmp_path))
    monkeypatch.setattr(sys, "argv", [
        "tunnelmaker.py", "1", "1", json.dumps(["ru", "rg"])
    ])

    # Stub de createupf y subprocess.run
    monkeypatch.setattr(tunnelmaker, "createupf", lambda *args, **kwargs: "MOCK_CMD")
    monkeypatch.setattr(tunnelmaker.subprocess, "run",
                        lambda *args, **kwargs: CompletedProcess(args, 0, stdout="OK\n", stderr=""))

    tunnelmaker.main()
    out = capsys.readouterr().out

    # Verificamos que se imprimen los mensajes clave
    assert "Processing VLAN: 1 (version 1) con método: add" in out
    assert "Command for UPF: MOCK_CMD" in out
    assert "SSH command:" in out