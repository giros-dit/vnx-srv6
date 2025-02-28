import os
import sys
import pymongo
import json

# Variables globales para la generación de comandos
ns = "across-tc32"

flowid_IPv6_gNB = {
    1: "fd00:0:2::2/64",
    2: "fd00:0:2::3/64",
    3: "fd00:0:2::4/64"
}

ID_to_IP = {
    "r1": "fcff:1::1",
    "r2": "fcff:2::1",
    "r3": "fcff:3::1",
    "r4": "fcff:4::1",
    "ru": "fcff:5::1",
    "rg": "fcff:6::1"
}

def iniciafichero():
    # Se crean los directorios y se inicializan los ficheros de script
    os.makedirs('./conf', exist_ok=True)
    with open('./conf/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")

def createupf(flowid, routers, method):
    FLOWID = int(flowid)
    if routers:
        # Se omite el primer nodo (por ejemplo, "ru") y se usan el resto para formar los segmentos.
        routers = routers[1:]
        segments = [ID_to_IP[r] for r in routers]
    else:
        segments = [ID_to_IP["rg"]]

    ipgNB = flowid_IPv6_gNB.get(FLOWID, "unknown")
    comandoupf = (f"kubectl exec -n {ns} deploy/ru -- docker exec ru "
                  f"ip -6 route {method} {ipgNB} encap seg6 mode encap segs "
                  f"{','.join(segments)} dev eth1 table{FLOWID}")
    return comandoupf

def save(command, file):
    with open(file, 'a') as f:
        f.write(command + "\n")

def determine_method(version, routers):
    if not routers:
        return "delete"
    # Si la versión es 1 se usa "add", si es mayor se usa "replace"
    return "add" if version == 1 else "replace"

def main():
    iniciafichero()
    flowid = sys.argv[1]
    version = int(sys.argv[2])
    routersid = json.loads(sys.argv[3])

    method = determine_method(version, routersid)
    print(f"Processing VLAN: {flowid} (version {version}) con método: {method}")

    commandrupf = createupf(flowid, routersid, method)
    print(f"Command for rupf: {commandrupf}")
        
    scriptfile = './conf/script.sh'
    save(commandrupf, scriptfile)

    print("\nFichero de script generado en el volumen compartido.")
    print("Ejecuta los scripts en el host, por ejemplo:")
    print(" ./conf/script.sh")

if __name__ == "__main__":
    main()
