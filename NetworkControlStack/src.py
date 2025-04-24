import os
import sys
import json
import re
import subprocess

# Variables globales para la generación de comandos
ns = "across-tc32"

flowid_IPv6_gNB = {
    1: "fd00:0:2::2/64",
    2: "fd00:0:2::3/64",
    3: "fd00:0:2::4/64",
    4: "fd00:0:3::2/64",
    5: "fd00:0:3::3/64",
    6: "fd00:0:3::4/64"
}

def choose_destination(flow_id, destinos):
    if not destinos:
        return None
    if len(destinos) == 1:
        return destinos[0]
    if flow_id in [1, 2, 3]:
        return destinos[0]
    else:
        return destinos[1]

def createupf(flowid, extremos, method, id_to_ip, routersid):
    FLOWID = int(flowid)
    print(f"Creating UPF for flow ID: {FLOWID}")
    origin = extremos.get("origen")
    destinos = extremos.get("destinos", [])
    dest = choose_destination(FLOWID, destinos)
    print(f"Origin: {origin}, Destino: {dest}")
    # Se forman los segmentos usando la IP del origen y la del destino (quitando la máscara)
    segments = []
    if routersid:
        # Se omite el primer nodo (por ejemplo, "ru") y se usan el resto para formar los segmentos.
        routersid = routersid[1:]
        segments = [id_to_ip[r] for r in routersid]
    else:
        segments = [routersid["rg"]]
    print(f"Segments: {segments}")
    ipgNB = flowid_IPv6_gNB.get(FLOWID, "unknown")
    comandoupf = (
        f"ip -6 route {method} {ipgNB} encap seg6 mode encap segs "
        f"{','.join(segments)} dev eth1 table tunel{FLOWID}"
    )
    return comandoupf

def determine_method(version, routers):
    if not routers:
        return "delete"
    # Si la versión es 1 se usa "add", si es mayor se usa "replace"
    return "add" if version == 1 else "replace"

def main():
    if len(sys.argv) != 4:
        print("Uso: python tunnelmaker.py <flowid> <version> <ruta_json>")
        sys.exit(1)

    flowid = sys.argv[1]
    version = int(sys.argv[2])
    routersid = json.loads(sys.argv[3])
    method = determine_method(version, routersid)

    # Leer el archivo JSON final_output.json
    json_path = os.path.join(os.path.dirname(__file__), "final_output.json")
    with open(json_path, "r") as json_file:
        data = json.load(json_file)

    # Extraer el diccionario ID_to_IP a partir del campo "loopbacks" (quitando la máscara)
    ID_to_IP = {k: v.split("/")[0] for k, v in data.get("loopbacks", {}).items()}
    extremos = data.get("extremos", {})

    method = determine_method(version, extremos)
    print(f"Processing VLAN: {flowid} (version {version}) con método: {method}")

    command = createupf(flowid, extremos, method, ID_to_IP,routersid)
    print(f"Command for UPF: {command}")
    ssh_target = "root@ru.across-tc32.svc.cluster.local"
    ssh_command = ["ssh","-o", "StrictHostKeyChecking=no", ssh_target, command]
    print(f"SSH command: {' '.join(ssh_command)}")
    result = subprocess.run(ssh_command, capture_output=True, text=True)

    print("Salida del comando SSH:")
    print(result.stdout)
    if result.stderr:
        print("Errores:")
        print(result.stderr)
if __name__ == "__main__":
    main()
