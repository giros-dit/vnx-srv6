#!/usr/bin/env python
import pymongo
import sys

def main():
    def menu():
        while True:
            option = input("Seleccione una opción (v: VLAN, e: Energía, q: Salir): ").lower()
            if option == 'v':
                handle_vlan()
            elif option == 'e':
                handle_energy()
            elif option == 'q':
                print("Saliendo del programa.")
                sys.exit(0)
            else:
                print("Opción no válida. Intente de nuevo.")

    def handle_vlan():
        client = pymongo.MongoClient("mongodb://mongo:27017/")
        db = client["across"]
        routes_col = db["routes"]

        try:
            vlan = int(input("Ingrese el número de VLAN (111, 112, 113): "))
            if vlan not in [111, 112, 113]:
                print("El número de VLAN debe ser 111, 112 o 113.")
                return
        except ValueError:
            print("El número de VLAN debe ser un entero.")
            return

        routers_input = input("Ingrese los identificadores de los routers (separados por coma): ")
        routers = [r.strip() for r in routers_input.split(",") if r.strip()]

        existing = routes_col.find_one({"vlan": vlan})
        if existing:
            new_version = existing.get("version", 1) + 1
            routes_col.update_one(
                {"vlan": vlan},
                {"$set": {"routers": routers, "version": new_version}}
            )
            print(f"Actualizado documento para VLAN {vlan} a versión {new_version}")
        else:
            document = {
                "vlan": vlan,
                "routers": routers,
                "version": 1
            }
            result = routes_col.insert_one(document)
            print(f"Insertado documento para VLAN {vlan} con versión 1, _id: {result.inserted_id}")

    def handle_energy():
        client = pymongo.MongoClient("mongodb://mongo:27017/")
        db = client["across"]
        energy_col = db["energy"]

        routers = ['r1', 'r2', 'r3', 'r4']

        for router in routers:
            try:
                consumption = float(input(f"Ingrese el consumo de energía para el router {router}: "))
            except ValueError:
                print(f"El consumo de energía para el router {router} debe ser un número.")
                continue

            existing_energy = energy_col.find_one({"router": router})
            if existing_energy:
                energy_col.update_one(
                    {"router": router},
                    {"$set": {"consumption": consumption}}
                )
                print(f"Actualizado consumo de energía para el router {router}")
            else:
                energy_document = {
                    "router": router,
                    "consumption": consumption
                }
                energy_col.insert_one(energy_document)
                print(f"Insertado documento de consumo de energía para el router {router}")

    menu()

if __name__ == "__main__":
    main()
