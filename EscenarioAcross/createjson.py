import json
import os

# Ruta del archivo JSON
json_file_path = 'VLANtunnels.json'
json_file_path_old = 'VLANtunnelsold.json'
# Cargar contenido del JSON si existe
if os.path.exists(json_file_path):
    with open(json_file_path, 'r') as f:
        config = json.load(f)
else:
    config = {}

def main():
    if os.path.exists(json_file_path) and not os.path.exists(json_file_path_old):
        os.system("cp VLANtunnels.json VLANtunnelsold.json")
    elif os.path.exists(json_file_path) and os.path.exists(json_file_path_old):
        with open('VLANtunnelsold.json', 'r') as old_file:
            old_config = json.load(old_file)
        for vlan_id, vlan_data in config.items():
            old_config[vlan_id] = vlan_data
        with open('VLANtunnelsold.json', 'w') as old_file:
            json.dump(old_config, old_file, indent=4)
        for vlan_id in config:
            if vlan_id not in old_config:
                old_config[vlan_id] = config[vlan_id]
    
    while True:
        vlan = input("Introduce VLAN id  (or 'q' for exit, 'c' to delete json content  ): ")

        if vlan.lower() == 'q':
            print("Exiting...")
            break
        elif vlan.lower() == 'c':
            config.clear()  
            print("JSON content deleted")
            continue

        # Preguntar si el camino de vuelta es el mismo que el de ida
        same_path_input = input(" DOes the package follows the same path between gnBX and UPF? (t if True, any other key if False): ")
        same_path = same_path_input.lower() == 't'

        # Pedir las direcciones fw
        fw_routers_input = input("Introduce the identifiers separated by spaces, in the same order that they would follow from UPF to GNB: ")
        fw_routersid = [fw.strip() for fw in fw_routers_input.split(' ') if fw.strip()]
        fw_routersip = [f'fcff:{fwid}::1' for fwid in fw_routersid] if fw_routersid else []

        # Si el camino de vuelta no es el mismo, pedir las direcciones rt
        rt_list = []
        if not same_path:
            rt_routers_input = input("Introduce the identifiers separated by spaces, in the same order that they would follow from GNB to UPF: ")
            rt_routersid = [rt.strip() for rt in rt_routers_input.split(' ') if rt.strip()]
            rt_list = [f'fcff:{rtid}::1' for rtid in rt_routersid] if rt_routersid else []

        # Actualizar o crear el JSON
        config[vlan] = {
            "fw": fw_routersip,
            "rt": rt_list,
            "same_path": same_path
        }

        # Guardar el JSON actualizado
        with open(json_file_path, 'w') as f:
            json.dump(config, f, indent=4)

    os.system("python3 tunnelmaker.py")

if __name__ == "__main__":
    main()
