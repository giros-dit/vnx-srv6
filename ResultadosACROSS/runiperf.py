#!/usr/bin/env python3
import subprocess
import time

TARGETS = [
    {"name": "hgnb-h1", "ip": "fd00:0:2::2", "cidr": "fd00:0:2::2/64", "bw": "20M"},
    {"name": "hgnb-h2", "ip": "fd00:0:2::3", "cidr": "fd00:0:2::3/64", "bw": "20M"},
    {"name": "hgnb-h3", "ip": "fd00:0:2::4", "cidr": "fd00:0:2::4/64", "bw": "50M"},
    {"name": "hgnb-h4", "ip": "fd00:0:2::5", "cidr": "fd00:0:2::5/64", "bw": "20M"},
    {"name": "hgnb-h5", "ip": "fd00:0:2::6", "cidr": "fd00:0:2::6/64", "bw": "40M"},
    {"name": "hgnb-h6", "ip": "fd00:0:2::7", "cidr": "fd00:0:2::7/64", "bw": "25M"},
    {"name": "hgnb-h7", "ip": "fd00:0:2::8", "cidr": "fd00:0:2::8/64", "bw": "17M"},
]

def run(cmd):
    print("> " + " ".join(cmd))
    return subprocess.run(cmd, check=True)

def start_detached(cmd):
    print("> " + " ".join(cmd))
    return subprocess.run(cmd, check=True)

def main():
    for tgt in TARGETS:
        input(f"\nPresiona Enter para iniciar test contra {tgt['name']} ({tgt['ip']})…")

        # 1) Flows
        print("-> Ejecutando flows.py en networkstack")
        run([
            "kubectl", "exec", "deploy/networkstack", "--",
            "python3", "flows.py", tgt["cidr"]
        ])

        # 2) Espera
        print("-> Esperando 3 segundos")
        time.sleep(3)

        # 3) Servidor iperf3 en hgnb-hX (detached en Docker)
        print(f"-> Lanzando iperf3 UDP server en {tgt['name']} enlazado a {tgt['ip']}")
        start_detached([
            "kubectl", "exec", f"deploy/{tgt['name']}", "--",
            "docker", "exec", "-d", tgt["name"],
            "iperf3", "-s", "-V", "-u", "-B", tgt["ip"]
        ])

        # 4) Cliente iperf3 en hupf-h1 (detached en Docker)
        print("-> Lanzando iperf3 UDP client en hupf-h1")
        start_detached([
            "kubectl", "exec", "deploy/hupf-h1", "--",
            "docker", "exec", "-d", "hupf-h1",
            "iperf3", "-c", tgt["ip"],
            "-V", "-u", "-b", tgt["bw"],
            "-l", "1000", "-t", "600"
        ])

        print(f"✓ Test para {tgt['name']} lanzado (corriendo en background).")

if __name__ == "__main__":
    main()
