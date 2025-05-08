import pytest
import json
import os
import sys
from subprocess import CompletedProcess
import src  # ← cambiamos la importación a src


def test_determine_method_no_routers():
    assert src.determine_method(1, []) == "delete"

def test_determine_method_add():
    assert src.determine_method(1, ["r1"]) == "add"

def test_determine_method_replace():
    assert src.determine_method(2, ["r1"]) == "replace"

def test_choose_destination_rg1():
    assert src.choose_destination("fd00:0:2::1/64") == "rg1"

def test_choose_destination_rg2():
    assert src.choose_destination("fd00:0:3::1/64") == "rg2"

def test_createupf_with_routers():
    dest_ip = "fd00:0:2::2/64"
    method = "add"
    ID_to_IP = {
        "rg1": "fd00:0:2::2/64",
        "r1": "fd00::1",
        "r2": "fd00::2"
    }
    routersid = ["ru", "r1", "r2"]
    command = src.createupf(dest_ip, method, ID_to_IP, routersid)
    assert "ip -6 route add fd00:0:2::2" in command
    assert "segs fd00::1,fd00::2" in command
    assert "dev eth1" in command
    assert "table tunnel_" in command

def test_createupf_no_routers():
    dest_ip = "fd00:0:2::2/64"
    method = "delete"
    ID_to_IP = {"rg1": "fd00:0:2::2/64"}
    routersid = []
    command = src.createupf(dest_ip, method, ID_to_IP, routersid)
    assert "segs" not in command
    assert "delete fd00:0:2::2" in command

def test_main_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["src.py"])
    with pytest.raises(SystemExit) as se:
        src.main()
    assert se.value.code == 1
    out = capsys.readouterr().out
    assert "Uso: python tunnelmaker.py" in out

def test_main_success(monkeypatch, tmp_path, capsys):
    # Crear un networkinfo.json simulado
    data = {
        "loopbacks": {
            "rg1": "fd00:0:2::2/64",
            "r1": "fd00::1/64",
            "r2": "fd00::2/64"
        }
    }
    file_path = tmp_path / "networkinfo.json"
    file_path.write_text(json.dumps(data))

    monkeypatch.setattr(os.path, "dirname", lambda _: str(tmp_path))
    monkeypatch.setattr(sys, "argv", [
        "src.py", "fd00:0:2::2/64", "1", json.dumps(["ru", "r1", "r2"])
    ])

    monkeypatch.setattr(src, "createupf", lambda *args, **kwargs: "MOCK_CMD")
    monkeypatch.setattr(src.subprocess, "run",
                        lambda *args, **kwargs: CompletedProcess(args, 0, stdout="OK\n", stderr=""))

    src.main()
    out = capsys.readouterr().out
    assert "Processing dest_ip: fd00:0:2::2/64, version: 1, method: add" in out
    assert "Command for UPF: MOCK_CMD" in out
    assert "SSH command:" in out
