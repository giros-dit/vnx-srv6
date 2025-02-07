import sys
import os
import json
ns = "across-tc32"

def iniciaficheros():
    os.makedirs('./conf/rgnb', exist_ok=True)
    with open('./conf/rgnb/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")

    os.makedirs('./conf/rupf', exist_ok=True)
    with open('./conf/rupf/script.sh', 'w') as f:
        f.write("#!/bin/bash\n")


def cargarjson(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data

VLAN_IPv6_gNB = {
    111: "fd00:0:2::/127",
    112: "fd00:0:2::2/127",
    113: "fd00:0:2::4/127"
}

VLAN_IPv6_UPF = {
    111: "fd00:0:1::/127",
    112: "fd00:0:1::2/127",
    113: "fd00:0:1::4/127",
}

def createupf(vlan, routers, method):
    
    VLAN = int(vlan)

    if VLAN < 114 and VLAN >= 110:
        if routers:
            segments = [r for r in routers] + [f'fcff:5::1'] + [f'fcff:7::1']
        else:
            segments = [f'fcff:5::1'] + [f'fcff:7::1']

    else:
        print("VLAN not supported")
        sys.exit(1)
    
    ipgNB=VLAN_IPv6_gNB[VLAN]

    
    comandoupf = f"kubectl exec -n {ns} deploy/rupf -- docker exec rupf ip -6 route {method} {ipgNB} encap seg6 mode encap segs {','.join(segments)} dev eth2.{VLAN}"
    
    return comandoupf

def creategnb(VLAN, routers ,method):
    
    if VLAN < 114 and VLAN >= 110:
        if routers:
            segments = [r for r in routers] + [f'fcff:6::1'] + [f'fcff:8::1']
        else:
            segments = [f'fcff:6::1'] + [f'fcff:8::1']
    
    else:
        print("VLAN not supported")
        sys.exit(1)
    
    ipUPF=VLAN_IPv6_UPF[VLAN]

    comandognb = f"kubectl exec -n {ns} deploy/rgnb -- docker exec rgnb ip -6 route {method} {ipUPF} encap seg6 mode encap segs {','.join(segments)} dev eth2.{VLAN}"
    return comandognb

def save(command, file):
    with open(file, 'a') as f:
        f.write(command + "\n")


def getMethod(conf_old, vlan, routers):
    if vlan not in conf_old:
        return "add"
    if not routers and conf_old[vlan]:
        return "delete"
    if conf_old[vlan] != routers:
        return "replace"

def execute():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.system(f"sudo chmod +x {script_dir}/conf/rgnb/script.sh")
    os.system(f"sudo chmod +x {script_dir}/conf/rupf/script.sh")
    #os.system(f"sudo {script_dir}/conf/rgnb/script.sh")
    #os.system(f"sudo {script_dir}/conf/rupf/script.sh")


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
        print(f"Processing VLAN: {vlan}")
        
        # Obtener VLAN y camino de routers del json de una VLAN
        VLAN = int(vlan)
        routersupfgnb = routers.get("fw", [])
        if routersupfgnb and routers.get("same_path", False):
            routersgnbupf = routersupfgnb[::-1]
        else:
            routersgnbupf = routers.get("rt", [])

        

        # Comprobar si la configuración ha cambiado
        if vlan not in conf_old or conf_old[vlan] != routers:
            # Crear comandos para cada fichero
            action = getMethod(conf_old, vlan, routers)
            commandrupf = createupf(VLAN, routersupfgnb, action)
            commandrgnb = creategnb(VLAN, routersgnbupf, action)
            print(f"Command for rupf: {commandrupf}")
            print(f"Command for rgnb: {commandrgnb}")
            #Crear ficheros script.sh
            scriptrupf = './conf/rupf/script.sh'
            scriptrgnb = f'./conf/rgnb/script.sh'
            print(f"Configuration changed for VLAN: {vlan}")
            save(commandrgnb, scriptrgnb)
            save(commandrupf, scriptrupf)
        else:
            print(f"No changes for VLAN: {vlan}")
        
    execute()

    # Borrar el contenido de los ficheros script.sh
    #directories = ['./conf/rgnb', './conf/rupf']
    #for directory in directories:
    #    script_path = os.path.join(directory, 'script.sh')
    #    if os.path.exists(script_path):
    #        with open(script_path, 'w') as script_file:
    #            script_file.write('')

if __name__ == "__main__":
    main()
