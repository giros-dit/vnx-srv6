import unittest
import sys
import json
import os
from io import StringIO

# Se importa la función main() de tunnelmaker.py
from tunnelmaker import main as tunnelmaker_main

class TestTunnelMaker(unittest.TestCase):
    def setUp(self):
        # Ruta al archivo final_output.json
        self.final_output_path = "final_output.json"
        # Si ya existe, se respalda su contenido
        self.final_output_backup = None
        if os.path.exists(self.final_output_path):
            with open(self.final_output_path, "r") as f:
                self.final_output_backup = f.read()

        # Se escribe el contenido esperado de final_output.json
        final_output_data = {
            "graph": {
                "nodes": ["rg", "r4", "ru", "r3", "r2", "r1"],
                "edges": [
                    {"source": "r4", "target": "r3", "cost": 0.0},
                    {"source": "r3", "target": "rg", "cost": 0.0},
                    {"source": "r1", "target": "r2", "cost": 0.0},
                    {"source": "ru", "target": "r2", "cost": 0.0},
                    {"source": "ru", "target": "r4", "cost": 0.0},
                    {"source": "rg", "target": "r3", "cost": 0.0},
                    {"source": "r2", "target": "ru", "cost": 0.0},
                    {"source": "r3", "target": "r4", "cost": 0.0},
                    {"source": "r4", "target": "ru", "cost": 0.0},
                    {"source": "r1", "target": "rg", "cost": 0.0},
                    {"source": "r2", "target": "r1", "cost": 0.0},
                    {"source": "rg", "target": "r1", "cost": 0.0}
                ]
            },
            "extremos": {
                "origen": "ru",
                "destinos": ["rg"]
            },
            "loopbacks": {
                "rg": "fcff:6::1/32",
                "r4": "fcff:4::1/32",
                "ru": "fcff:5::1/32",
                "r3": "fcff:3::1/32",
                "r2": "fcff:2::1/32",
                "r1": "fcff:1::1/32"
            }
        }
        with open(self.final_output_path, "w") as f:
            json.dump(final_output_data, f, indent=4)

    def tearDown(self):
        # Se restaura el archivo final_output.json original, o se elimina si no existía previamente.
        if self.final_output_backup is not None:
            with open(self.final_output_path, "w") as f:
                f.write(self.final_output_backup)
        else:
            if os.path.exists(self.final_output_path):
                os.remove(self.final_output_path)

    def test_tunnelmaker_with_expected_route(self):
        # Se simulan los argumentos:
        # flowid = "1", version = "1" y routersid = JSON de ["ru", "r4", "r3", "rg"]
        test_args = ["tunnelmaker.py", "1", "1", json.dumps(["ru", "r4", "r3", "rg"])]
        sys.argv = test_args

        # Se captura la salida por stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            tunnelmaker_main()
        except SystemExit:
            # Si main() hace sys.exit, se captura la excepción
            pass

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Verificamos que la salida contenga los mensajes y comando esperados:
        self.assertIn("Creating UPF for flow ID: 1", output)
        self.assertIn("Origin: ru, Destino: rg", output)
        self.assertIn("Segments: ['fcff:4::1', 'fcff:3::1', 'fcff:6::1']", output)
        self.assertIn("Processing VLAN: 1 (version 1) con método: add", output)

        expected_command = (
            "kubectl exec -n across-tc32 deploy/ru -- docker exec ru "
            "ip -6 route add fd00:0:2::2/64 encap seg6 mode encap segs fcff:4::1,fcff:3::1,fcff:6::1 dev eth1 table1"
        )
        self.assertIn(expected_command, output)

if __name__ == "__main__":
    unittest.main()
