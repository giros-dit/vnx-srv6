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
    cmd = f"/usr/sbin/ip -6 rule show to {shlex.quote(dest)}/64"
    proc = ssh_ru(cmd)
    if proc.returncode != 0:
        return False
    return any(f"lookup tunnel{tid}" in line for line in proc.stdout.decode().splitlines())


def route_exists(dest, tid):
    """
    Comprueba remotamente si ya existe la ruta en la tabla `tunnel{tid}`.
    """
    cmd = f"/usr/sbin/ip -6 route show table tunnel{tid}"
    proc = ssh_ru(cmd)
    if proc.returncode != 0:
        return False
    return any(dest in line for line in proc.stdout.decode().splitlines())


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

    # Debug logging of input arguments
    print(f"[src] Args: dest_prefix={args.dest_prefix}, new_table_id={args.new_table_id}, delete_old={args.delete_old}, path_json={args.path_json}")

    dest = args.dest_prefix.split('/')[0]
    new_tid = args.new_table_id
    path = json.loads(args.path_json)

    print(f"[src] Cargando /app/networkinfo.json...")
    lbs = load_loopbacks()
    print(f"[src] Loopbacks: {lbs}\n")

    # 1) Borrar regla antigua si se solicita y existe
    if args.delete_old is not None:
        old = args.delete_old
        if rule_exists(dest, old):
            print(f"[src] → Borrando regla antigua: tunnel{old}")
            res = ssh_ru(f"/usr/sbin/ip -6 rule del to {dest}/64 lookup tunnel{old}")
            print(f"[src]   return {res.returncode}, stderr: {res.stderr.decode().strip()}")

    # 2) Asegurar la entrada en rt_tables
    if not table_entry_exists(new_tid):
        line = f"{new_tid} tunnel{new_tid}"
        print(f"[src] → Añadiendo rt_tables: {line}")
        res = ssh_ru(f"sh -c \"echo {shlex.quote(line)} >> /etc/iproute2/rt_tables\"")
        print(f"[src]   return {res.returncode}, stderr: {res.stderr.decode().strip()}")

    # 3) Determinar método: add o replace según existencia previa
    use_replace = route_exists(dest, new_tid)
    method = "replace" if use_replace else "add"
    print(f"[src] → Determinando método de ruta: {'existía' if use_replace else 'no existía'}. Usando '{method}'")

    segs = ','.join(lbs[n] for n in path[1:])
    cmd_route = (
        f"/usr/sbin/ip -6 route {method} {dest}/64 "
        f"encap seg6 mode encap segs {segs} dev eth1 table tunnel{new_tid}"
    )
    print(f"[src] Instalando ruta: {cmd_route}")
    res_route = ssh_ru(cmd_route)
    print(f"[src]   return {res_route.returncode}, stdout: {res_route.stdout.decode().strip()}, stderr: {res_route.stderr.decode().strip()}")

    # 4) Añadir regla de lookup si no existe
    if not rule_exists(dest, new_tid):
        cmd_rule = f"/usr/sbin/ip -6 rule add to {dest}/64 lookup tunnel{new_tid}"
        print(f"[src] → Añadiendo regla: {cmd_rule}")
        res_rule = ssh_ru(cmd_rule)
        print(f"[src]   return {res_rule.returncode}, stderr: {res_rule.stderr.decode().strip()}")

    print(f"[src] Done: flow {dest} → tunnel{new_tid}, path={path}")

if __name__ == '__main__':
    main()
