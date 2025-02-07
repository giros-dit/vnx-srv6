#!/usr/bin/env python
import os
import sys
import pymongo

# Variables globales para la generación de comandos
ns = "across-tc32"

VLAN_IPv6_gNB = {
    111: "fd00:0:2::/127",
    112: "fd00:0:2::2/127",
    113: "fd00:0:2::4/127"
}

VLAN_IPv6_UPF = {
    111: "fd00:0:1::/127",
    112: "fd00:0:1::2/127",
    113: "fd00:0:1::4/127"
}

def iniciaficheros():
    # Se crean los directorios y se inicializan los ficheros de script
    os.makedirs('./conf/rgnb', exist_ok=True)
    with open('./conf/rgnb/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")
    os.makedirs('./conf/rupf', exist_ok=True)
    with open('./conf/rupf/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")

def load_config_from_mongo():
    """Recupera la configuración desde Mongo.
       Se espera que cada documento tenga las claves 'vlan', 'routers' y 'version'."""
    client = pymongo.MongoClient("mongodb://mongo:27017/")
    db = client["across"]
    routes_col = db["routes"]

    config = {}
    for doc in routes_col.find():
        vlan = str(doc.get("vlan"))
        routers = doc.get("routers", [])
        version = doc.get("version", 1)
        config[vlan] = {"routers": routers, "version": version}
    return config

def createupf(vlan, routers, method):
    VLAN = int(vlan)
    if 110 <= VLAN < 114:
        segments = routers + ['fcff:5::1', 'fcff:7::1'] if routers else ['fcff:5::1', 'fcff:7::1']
    else:
        print("VLAN not supported")
        sys.exit(1)
    
    ipgNB = VLAN_IPv6_gNB.get(VLAN, "unknown")
    comandoupf = (f"kubectl exec -n {ns} deploy/rupf -- docker exec rupf "
                  f"ip -6 route {method} {ipgNB} encap seg6 mode encap segs "
                  f"{','.join(segments)} dev eth2.{VLAN}")
    return comandoupf

def creategnb(vlan, routers, method):
    VLAN = int(vlan)
    if 110 <= VLAN < 114:
        segments = routers + ['fcff:6::1', 'fcff:8::1'] if routers else ['fcff:6::1', 'fcff:8::1']
    else:
        print("VLAN not supported")
        sys.exit(1)
    
    ipUPF = VLAN_IPv6_UPF.get(VLAN, "unknown")
    comandognb = (f"kubectl exec -n {ns} deploy/rgnb -- docker exec rgnb "
                  f"ip -6 route {method} {ipUPF} encap seg6 mode encap segs "
                  f"{','.join(segments)} dev eth2.{VLAN}")
    return comandognb

def save(command, file):
    with open(file, 'a') as f:
        f.write(command + "\n")

def determine_method(version, routers):
    if not routers:
        return "delete"
    return "add" if version == 1 else "replace"

def main():
    iniciaficheros()
    config = load_config_from_mongo()

    for vlan, data in config.items():
        routers = data.get("routers", [])
        routers = [f"fcff:{router}::1" for router in data.get("routers", [])]
        version = data.get("version", 1)
        method = determine_method(version, routers)
        print(f"Processing VLAN: {vlan} (version {version}) con método: {method}")

        commandrupf = createupf(vlan, routers, method)
        comandognb = creategnb(vlan, routers, method)
        print(f"Command for rupf: {commandrupf}")
        print(f"Command for rgnb: {comandognb}")

        scriptfile = './conf/script.sh'
        save(commandrupf, scriptfile)
        save(comandognb, scriptfile)

    print("\nFicheros de script generados en el volumen compartido.")
    print("Ejecuta los scripts en el host, por ejemplo:")
    print("  bash ./conf/script.sh")

if __name__ == "__main__":
    main()
