import json
import os

# Ruta del archivo JSON
json_file_path = 'VLANtunnels.json'

# Cargar contenido del JSON si existe
if os.path.exists(json_file_path):
    with open(json_file_path, 'r') as f:
        config = json.load(f)
else:
    config = {}

def main():
    while True:
        vlan = input("Introduce el valor de la VLAN (o 'q' para salir, 'c' para borrar el contenido): ")

        if vlan.lower() == 'q':
            print("Saliendo del programa.")
            break
        elif vlan.lower() == 'c':
            config.clear()  # Borrar contenido del JSON
            print("Contenido del JSON borrado.")
            continue

        # Preguntar si el camino de vuelta es el mismo que el de ida
        same_path_input = input("¿El camino de vuelta es el mismo que el de ida? (t para True, cualquier otra tecla para False): ")
        same_path = same_path_input.lower() == 't'

        # Pedir las direcciones fw
        fw_routers_input = input("Introduce los identificadores de los routers desde UPF al GNB separados por espacios: ")
        fw_routersid = [fw.strip() for fw in fw_routers_input.split(' ') if fw.strip()]
        fw_routersip = [f'fcff:{fwid}::1' for fwid in fw_routersid] if fw_routersid else []

        # Si el camino de vuelta no es el mismo, pedir las direcciones rt
        rt_list = []
        if not same_path:
            rt_routers_input = input("Introduce los identificadores de los routers desde GNB al UPF separados por espacios: ")
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

if __name__ == "__main__":
    main()
