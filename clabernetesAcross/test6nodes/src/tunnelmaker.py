#!/usr/bin/env python
import os
import sys
import pymongo
import json

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

ID_to_IP = {
    "r1": "fcff:1::1",
    "r2": "fcff:2::1",
    "r3": "fcff:3::1",
    "r4": "fcff:4::1",
    "ru": "fcff:5::1",
    "rg": "fcff:6::1"
}

def iniciafichero():
    # Se crean los directorios y se inicializan los fichero de script
    os.makedirs('./conf', exist_ok=True)
    with open('./conf/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")



def createupf(vlan, routers, method):
    VLAN = int(vlan)
    if routers:
        routers = routers[1:]
    if 110 <= VLAN < 114:
        if routers:
            segments = [ID_to_IP.get(r, f"unknown_{r}") for r in routers]
        else:
            segments = [ID_to_IP['rg']]
    else:
        print("VLAN not supported")
        sys.exit(1)

    ipgNB = VLAN_IPv6_gNB.get(VLAN, "unknown")
    comandoupf = (f"kubectl exec -n {ns} deploy/ru -- docker exec ru "
                  f"ip -6 route {method} {ipgNB} encap seg6 mode encap segs "
                  f"{','.join(segments)} dev eth1.{VLAN}")
    return comandoupf

def creategnb(vlan, routers, method):
    VLAN = int(vlan)
    if routers:
        routers = routers[::-1][1:]
    if 110 <= VLAN < 114:
        if routers:
            segments = [ID_to_IP.get(r, f"unknown_{r}") for r in routers]
        else:
            segments = [ID_to_IP['ru']]
    else:
        print("VLAN not supported")
        sys.exit(1)
    
    ipUPF = VLAN_IPv6_UPF.get(VLAN, "unknown")
    comandognb = (f"kubectl exec -n {ns} deploy/rg -- docker exec rg "
                  f"ip -6 route {method} {ipUPF} encap seg6 mode encap segs "
                  f"{','.join(segments)} dev eth1.{VLAN}")
    return comandognb

def save(command, file):
    with open(file, 'a') as f:
        f.write(command + "\n")

def determine_method(version, routers):
    if not routers:
        return "delete"
    return "add" if version == 0 else "replace"

def main():
    iniciafichero()
    vlan = sys.argv[1]
    version = int(sys.argv[2])
    routersid = json.loads(sys.argv[3])

    method = determine_method(version, routersid)
    print(f"Processing VLAN: {vlan} (version {version}) con método: {method}")

    commandrupf = createupf(vlan, routersid, method)
    comandognb = creategnb(vlan, routersid, method)
    print(f"Command for rupf: {commandrupf}")
    print(f"Command for rgnb: {comandognb}")
        
    scriptfile = './conf/script.sh'
    save(commandrupf, scriptfile)
    save(comandognb, scriptfile)

    print("\nFichero de script generado en el volumen compartido.")
    print("Ejecuta los scripts en el host, por ejemplo:")
    print("  bash ./conf/script.sh")

if __name__ == "__main__":
    main()
