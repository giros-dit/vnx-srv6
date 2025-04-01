#!/usr/bin/env python3
import os
import sys
import pymongo
import json
import re

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

def iniciafichero():
    # Se crean los directorios y se inicializan los ficheros de script
    os.makedirs('./conf', exist_ok=True)
    with open('./conf/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")

def choose_destination(flow_id, destinos):
    """
    Ordena la lista de destinos (numéricamente) y:
      - Si flow_id es 1, 2 o 3, retorna el primero.
      - De lo contrario, retorna el segundo (si existe).
    """
    if not destinos:
        return None
    if len(destinos) == 1:
        return destinos[0]
    if flow_id in [1, 2, 3]:
        return destinos[0]
    else:
        return destinos[1]

def createupf(flowid, extremos, method, id_to_ip):
    FLOWID = int(flowid)
    origin = extremos.get("origen")
    destinos = extremos.get("destinos", [])
    dest = choose_destination(FLOWID, destinos)
    # Se forman los segmentos usando la IP del origen y la del destino extraídas del JSON
    segments = []
    if origin and origin in id_to_ip:
        segments.append(id_to_ip[origin])
    if dest and dest in id_to_ip:
        segments.append(id_to_ip[dest])
    ipgNB = flowid_IPv6_gNB.get(FLOWID, "unknown")
    comandoupf = (f"kubectl exec -n {ns} deploy/{origin} -- docker exec {origin} "
                  f"ip -6 route {method} {ipgNB} encap seg6 mode encap segs "
                  f"{','.join(segments)} dev eth1 table{FLOWID}")
    return comandoupf

def save(command, file):
    with open(file, 'a') as f:
        f.write(command + "\n")

def determine_method(version, extremos):
    if not extremos or not extremos.get("origen"):
        return "delete"
    return "add" if version == 1 else "replace"

def main():
    iniciafichero()
    # Se reciben tres argumentos:
    # 1) flowid, 2) version, 3) ruta al JSON final (por ejemplo, final_output.json)
    flowid = sys.argv[1]
    version = int(sys.argv[2])
    json_path = sys.argv[3]

    with open(json_path, 'r') as f:
        data = json.load(f)
    # Extraer dinámicamente el diccionario ID_to_IP a partir del campo "loopbacks" (quitando la máscara)
    ID_to_IP = {k: v.split("/")[0] for k, v in data.get("loopbacks", {}).items()}
    
    extremos = data.get("extremos", {})

    method = determine_method(version, extremos)
    print(f"Processing VLAN: {flowid} (version {version}) con método: {method}")

    command = createupf(flowid, extremos, method, ID_to_IP)
    print(f"Command for UPF: {command}")
        
    scriptfile = './conf/script.sh'
    save(command, scriptfile)

    print("\nFichero de script generado en el volumen compartido.")
    print("Ejecuta el script en el host, por ejemplo:")
    print(" ./conf/script.sh")

if __name__ == "__main__":
    main()
