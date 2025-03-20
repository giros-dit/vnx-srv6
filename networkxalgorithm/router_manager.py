import json
import time
import threading
import os

router_state = {}  # Ej. {"r1": {"usage": 0.0, "energy": 700, "ts": 0.0}}
paused_routers = set()

def read_routers():
    try:
        with open("routers.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def write_routers(data):
    with open("routers.json", "w") as f:
        json.dump(data, f, indent=4)

def update_router_state():
    while True:
        for router, state in router_state.items():
            if router in paused_routers:
                # Skip updating paused routers
                continue
            usage = state.get("usage", 0.0)
            energy = 700 + usage * 20
            router_state[router]["energy"] = energy
            router_state[router]["ts"] = time.time()
        write_routers([
            {
                "router": r,
                "usage": s["usage"],
                "energy": s["energy"],
                "ts": s["ts"]
            }
            for r, s in router_state.items()
        ])
        time.sleep(5)

def handle_user_input():
    while True:
        try:
            user_input = input("Ingrese los routers separados por espacio (ej: 1 2): ").strip()
            if user_input == 'q':
                if os.path.exists("routers.json"):
                    os.remove("routers.json")
                print("Saliendo...")
                break
            elif user_input.startswith("p "):
                parts = user_input.split()
                if len(parts) > 1:
                    router_key = f"r{parts[1]}"
                    paused_routers.add(router_key)
            elif not user_input:
                continue
            else:
                routers = user_input.split()
                for router in routers:
                    router_key = f"r{router}"
                    if router_key not in router_state:
                        router_state[router_key] = {"usage": 0.0, "energy": 700, "ts": time.time()}
                    router_state[router_key]["usage"] += 0.21
                    router_state[router_key]["ts"] = time.time()
                    if router_state[router_key]["usage"] > 1.0:
                        router_state[router_key]["usage"] = 1.0  # Limitar al 100%
        except Exception as e:
            print(f"Error al procesar la entrada: {e}")

def main():
    # Inicializar estado de los routers
    for i in range(1, 5):  # r1, r2, r3, r4
        router_state[f"r{i}"] = {"usage": 0.0, "energy": 700, "ts": time.time()}

    # Leer estado inicial desde routers.json si existe
    initial_data = read_routers()
    for item in initial_data:
        router = item.get("router")
        usage = item.get("usage", 0.0)
        energy = 700 + usage * 20
        if router:
            router_state[router] = {"usage": usage, "energy": energy, "ts": time.time()}

    # Iniciar hilos para actualizar estado y manejar entrada del usuario
    threading.Thread(target=update_router_state, daemon=True).start()
    handle_user_input()

if __name__ == "__main__":
    main()
