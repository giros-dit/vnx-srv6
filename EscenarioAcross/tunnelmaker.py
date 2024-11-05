import sys
import os
import json

def iniciaficheros():
    os.makedirs('./conf/r11', exist_ok=True)
    with open('./conf/r11/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")

    os.makedirs('./conf/r12', exist_ok=True)
    with open('./conf/r12/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")

    os.makedirs('./conf/r13', exist_ok=True)
    with open('./conf/r13/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")

def cargarjson(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data

VLAN_IPv6_gNB = {
    111: "fd00:0:2::/126",
    112: "fd00:0:2::4/126",
    113: "fd00:0:2::8/126",
    121: "fd00:0:3::/126",
    122: "fd00:0:3::4/126",
    123: "fd00:0:3::8/126"
}

VLAN_IPv6_UPF = {
    111: "fd00:0:1::/126",
    112: "fd00:0:1::4/126",
    113: "fd00:0:1::8/126",
    121: "fd00:0:1::c/126",
    122: "fd00:0:1::10/126",
    123: "fd00:0:1::14/126"
}

def createupfgnb(VLAN, routers):
    
    if routers:
        segments = [r for r in routers] + [f'fcff:11::1']
    else:
        segments = [f'fcff:11::1']
    
    ipgNB=VLAN_IPv6_gNB[VLAN]
    
    comandognbupf = f"ip -6 route add {ipgNB} encap seg6 mode encap segs {','.join(segments)} dev eth4.{VLAN}"
    
    return comandognbupf

def creategnbupf(VLAN, routers):
    
    if routers:
        segments = [r for r in routers] + [f'fcff:13::1']
    else:
        segments = [f'fcff:13::1']

    ipUPF=VLAN_IPv6_UPF[VLAN]
    
    comandoupfgnb = f"ip -6 route add {ipUPF} encap seg6 mode encap segs {','.join(segments)} dev eth4.{VLAN}"
    
    return comandoupfgnb

def save(command, file):
    
    with open(file, 'a') as f:
        f.write(command + "\n")

def getNombrefichero(VLAN):
    if(VLAN < 200):
        return "r11"
    elif(VLAN < 300):
        return "r12"

def execute():
    os.system("sudo vnx -f /home/alex/Escritorio/vnx-srv6/EscenarioAcross/escenario-across-vnx.xml -x createroute")

def main():
    iniciaficheros()
    conf = cargarjson('./VLANtunnels.json')
    
    # Intentar cargar VLANtunnelsold.json si existe
    if os.path.exists('./VLANtunnelsold.json'):
        conf_old = cargarjson('./VLANtunnelsold.json')
    else:
        conf_old = {}

    # Recorrer fichero json
    for vlan, routers in conf.items():
        # Obtener VLAN y camino de routers del json de una VLAN
        VLAN = int(vlan)
        routersupfgnb = routers.get("fw", [])
        if routersupfgnb and routers.get("same_path", False):
            routersgnbupf = routersupfgnb[::-1]
        else:
            routersgnbupf = routers.get("rt", [])

        # Decidir si es r11 o r12 el fichero a modificar
        routerAcceso = getNombrefichero(VLAN)

        # Crear comandos para cada fichero
        commandr13 = createupfgnb(VLAN, routersupfgnb)
        commandgnb = creategnbupf(VLAN, routersgnbupf)

        scriptr13 = './conf/r13/script.sh'
        scriptgnb = f'./conf/{routerAcceso}/script.sh'

        # Comprobar si la configuración ha cambiado
        if vlan not in conf_old or conf_old[vlan] != routers:
            save(commandgnb, scriptgnb)
            save(commandr13, scriptr13)
        
    execute()

if __name__ == "__main__":
    main()
