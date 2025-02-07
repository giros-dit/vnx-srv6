#!/usr/bin/env python
import pymongo
import sys

def main():
    # Conectar a MongoDB (el host es el nombre del servicio definido en docker-compose)
    client = pymongo.MongoClient("mongodb://mongo:27017/")
    db = client["across"]
    routes_col = db["routes"]

    try:
        vlan = int(input("Ingrese el número de VLAN: "))
    except ValueError:
        print("El número de VLAN debe ser un entero.")
        sys.exit(1)

    routers_input = input("Ingrese los identificadores de los routers (separados por coma): ")
    routers = [r.strip() for r in routers_input.split(",") if r.strip()]

    # Verificar si ya existe un documento para esta VLAN
    existing = routes_col.find_one({"vlan": vlan})
    if existing:
        # Se actualiza la lista y se incrementa la versión
        new_version = existing.get("version", 1) + 1
        routes_col.update_one(
            {"vlan": vlan},
            {"$set": {"routers": routers, "version": new_version}}
        )
        print(f"Actualizado documento para VLAN {vlan} a versión {new_version}")
    else:
        # Se inserta un nuevo documento con versión 1
        document = {
            "vlan": vlan,
            "routers": routers,
            "version": 1
        }
        result = routes_col.insert_one(document)
        print(f"Insertado documento para VLAN {vlan} con versión 1, _id: {result.inserted_id}")

    energy_col = db["energy"]

    for router in routers:
        try:
            consumption = float(input(f"Ingrese el consumo de energía para el router {router}: "))
        except ValueError:
            print(f"El consumo de energía para el router {router} debe ser un número.")
            continue

        # Verificar si ya existe un documento para este router
        existing_energy = energy_col.find_one({"router": router})
        if existing_energy:
            # Se actualiza el consumo de energía
            energy_col.update_one(
                {"router": router},
                {"$set": {"consumption": consumption}}
            )
            print(f"Actualizado consumo de energía para el router {router}")
        else:
            # Se inserta un nuevo documento
            energy_document = {
                "router": router,
                "consumption": consumption
            }
            energy_col.insert_one(energy_document)
            print(f"Insertado documento de consumo de energía para el router {router}")

if __name__ == "__main__":
    main()
