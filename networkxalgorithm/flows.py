import json
import sys

def read_flows():
    try:
        with open("flows.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def write_flows(flows):
    with open("flows.json", "w") as f:
        json.dump(flows, f, indent=4)

def main():
    if len(sys.argv) != 2:
        print("Uso: flows.py <id>")
        sys.exit(1)

    flow_id = sys.argv[1]
    flows = read_flows()

    # Buscar si el flujo ya existe
    existing_flow = next((f for f in flows if f.get("_id") == flow_id), None)

    if existing_flow:
        # Si existe, eliminarlo
        flows = [f for f in flows if f.get("_id") != flow_id]
        print(f"Flujo con ID {flow_id} eliminado.")
    else:
        # Si no existe, agregarlo con versión 1
        new_flow = {"_id": flow_id, "version": 1}
        flows.append(new_flow)
        print(f"Flujo con ID {flow_id} añadido con versión 1.")

    write_flows(flows)

if __name__ == "__main__":
    main()
