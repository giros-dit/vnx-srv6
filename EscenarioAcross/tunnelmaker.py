import sys
import os

def createupfgnb(iphost, routers):
    via = 'fd00:0:4::2'
    
    if routers:
        segments = [f'fcff:{r}::1' for r in routers] + [f'fcff:11::1']
    else:
        segments = [f'fcff:11::1']
    
    comandognbupf = f"ip -6 route add {iphost} encap seg6 mode encap segs {','.join(segments)} via {via}"
    
    return comandognbupf

def creategnbupf(iphost, routers):
    
    if routers:
        segments = [f'fcff:{r}::1' for r in routers] + [f'fcff:13::1']
    else:
        segments = [f'fcff:13::1']
    
    comandoupfgnb = f"ip -6 route add fd00:0:4::/64 encap seg6 mode encap segs {','.join(segments)} via {iphost}"
    
    return comandoupfgnb

def save(command, file):
    
    with open(file, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(command + "\n")

def execute():
    os.system("sudo vnx -f /home/alex/Escritorio/vnx-srv6/EscenarioAcross/escenario-across-vnx.xml -x createroute")

def main():
    if len(sys.argv) < 2:
        print("Uso: python3 creatuneles.py <IP_HOST_NUMERO> [router1] [router2] ...")
        sys.exit(1)

    # Insertar el número del host directamente en la IP
    iphost_num = sys.argv[1]
    iphost = f'fd00:0:{iphost_num}::2/64'
    
    routersgnbupf = sys.argv[2:]
    routersupfgnb = routersgnbupf[::-1]  # Invertir el orden de los routers para la otra ruta

    # Crear scripts
    commandgnb = createupfgnb(iphost, routersgnbupf)
    commandr13 = creategnbupf(iphost, routersupfgnb)

    scriptgnb = './conf/gNB/script.sh'
    scriptr13 = './conf/r13/script.sh'
    
    save(commandgnb, scriptgnb)
    save(commandr13, scriptr13)
    
    print(f"Scripts generados y guardados en {scriptr13} y {scriptgnb}.")

    #execute()

if __name__ == "__main__":
    main()
