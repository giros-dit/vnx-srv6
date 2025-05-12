#!/usr/bin/env python3
import json
import subprocess
import shlex
import ipaddress
import argparse


def ssh_ru(cmd):
    """
    Ejecuta un comando de shell en RU vía SSH, asegurando rutas a /usr/sbin y /sbin.
    Devuelve el objeto CompletedProcess con stdout y stderr.
    """
    remote_cmd = f"PATH=$PATH:/usr/sbin:/sbin {cmd}"
    proc = subprocess.run(
        ['ssh', '-o', 'StrictHostKeyChecking=no', 'root@ru.across-tc32.svc.cluster.local', remote_cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    return proc


def load_loopbacks(path='/app/networkinfo.json'):
    """
    Carga el JSON de networkinfo y retorna un dict nodo->loopback (sin máscara).
    """
    with open(path) as f:
        data = json.load(f)
    return {n: lp.split('/')[0] for n, lp in data.get('loopbacks', {}).items()}


def rule_exists(dest, tid):
    """
    Comprueba remotamente si existe una regla `ip -6 rule ... lookup tunnel{tid}` para el prefijo dest.
    """
    # Listar reglas para el destino
    cmd = f"/usr/sbin/ip -6 rule show to {shlex.quote(dest)}/64"
    proc = ssh_ru(cmd)
    if proc.returncode != 0:
        return False
    # Buscar en la salida la tabla correspondiente
    return any(f"lookup tunnel{tid}" in line for line in proc.stdout.decode().splitlines())


def table_entry_exists(tid):
    """
    Comprueba remotamente en /etc/iproute2/rt_tables si ya existe la entrada `tid tunnel{tid}`.
    """
    entry = f"{tid} tunnel{tid}"
    cmd = f"grep -qx {shlex.quote(entry)} /etc/iproute2/rt_tables"
    proc = ssh_ru(cmd)
    return proc.returncode == 0


def main():
    p = argparse.ArgumentParser(description="Instala rutas SRv6 en RU usando iproute2 y reglas ip6.")
    p.add_argument("dest_prefix", help="Prefijo IPv6 del flujo, p.ej. fd00:0:2::2/64")
    p.add_argument("new_table_id", type=int, help="ID de la tabla a usar (numérico)")
    p.add_argument("path_json", help="JSON-encoded list de nodos de la ruta")
    p.add_argument("--delete-old", metavar="OLD_TID", type=int,
                   help="ID de tabla antigua a eliminar regla (opcional)")
    args = p.parse_args()

    dest = args.dest_prefix.split('/')[0]
    new_tid = args.new_table_id
    path = json.loads(args.path_json)

    print(f"[src] Cargando /app/networkinfo.json... ")
    lbs = load_loopbacks()
    print(f"[src] Loopbacks: {lbs}\n")

    # 1) Borrar regla antigua si se solicita y existe
    if args.delete_old is not None:
        old = args.delete_old
        if rule_exists(dest, old):
            print(f"[src] → Borrando regla antigua: tunnel{old}")
            ssh_ru(f"/usr/sbin/ip -6 rule del to {dest}/64 lookup tunnel{old}")

    # 2) Asegurar la entrada en rt_tables
    if not table_entry_exists(new_tid):
        line = f"{new_tid} tunnel{new_tid}"
        print(f"[src] → Añadiendo rt_tables: {line}")
        # Usamos sh -c para redirigir correctamente
        ssh_ru(f"sh -c \"echo {shlex.quote(line)} >> /etc/iproute2/rt_tables\"")

    # 3) Instalar/actualizar la ruta con SRv6 segments
    segs = ','.join(lbs[n] for n in path[1:])
    cmd_route = (
        f"/usr/sbin/ip -6 route replace {dest}/64 "
        f"encap seg6 mode encap segs {segs} dev eth1 table tunnel{new_tid}"
    )
    print(f"[src] Instalando ruta: {cmd_route}")
    ssh_ru(cmd_route)

    # 4) Añadir regla de lookup si no existe
    if not rule_exists(dest, new_tid):
        cmd_rule = f"/usr/sbin/ip -6 rule add to {dest}/64 lookup tunnel{new_tid}"
        print(f"[src] → Añadiendo regla: {cmd_rule}")
        ssh_ru(cmd_rule)

    print(f"[src] Done: flow {dest} → tunnel{new_tid}, path={path}")


if __name__ == '__main__':
    main()
