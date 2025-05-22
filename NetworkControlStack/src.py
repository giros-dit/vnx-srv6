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


def validate_table_id(tid):
    """
    Valida que el ID de tabla no use valores reservados del sistema.
    Valores reservados en /etc/iproute2/rt_tables:
    255 = local, 254 = main, 253 = default, 0 = unspec
    """
    reserved_ids = {0, 253, 254, 255}
    if tid in reserved_ids:
        raise ValueError(f"Table ID {tid} es un valor reservado del sistema. "
                        f"Valores reservados: {reserved_ids}")


def main():
    p = argparse.ArgumentParser(description="Instala rutas SRv6 en RU usando iproute2 y reglas ip6.")
    p.add_argument("dest_prefix", help="Prefijo IPv6 del flujo, p.ej. fd00:0:2::2/64")
    p.add_argument("version", type=int, help="Versión del flujo")
    p.add_argument("path_json", help="JSON-encoded list de nodos de la ruta")
    p.add_argument("--table-id", type=int, required=True, help="ID numérico de la tabla a usar")
    p.add_argument("--new-table", action="store_true", help="Indica si la tabla es nueva")
    p.add_argument("--delete-old", type=int, help="ID de tabla antigua a eliminar regla (opcional)")
    p.add_argument("--high-occupancy", action="store_true", help="Indica si la ruta usa nodos con alta ocupación")
    args = p.parse_args()

    # Validar que el table_id no sea un valor reservado
    try:
        validate_table_id(args.table_id)
    except ValueError as e:
        print(f"[src][ERROR] {e}")
        return 1

    # Validar también delete_old si se proporciona
    if args.delete_old is not None:
        try:
            validate_table_id(args.delete_old)
        except ValueError as e:
            print(f"[src][ERROR] Tabla antigua {e}")
            return 1

    # Debug logging de argumentos de entrada
    print(f"[src] Args: dest_prefix={args.dest_prefix}, version={args.version}, table_id={args.table_id}, "
          f"new_table={args.new_table}, delete_old={args.delete_old}, high_occupancy={args.high_occupancy}, "
          f"path_json={args.path_json}")

    dest = args.dest_prefix.split('/')[0]
    tid = args.table_id
    path = json.loads(args.path_json)

    # Mostrar aviso si la ruta usa nodos con alta ocupación
    if args.high_occupancy:
        print(f"[src] AVISO: La ruta para {dest} usa nodos con alta ocupación (entre 80% y 95%)")

    print(f"[src] Cargando /app/networkinfo.json...")
    lbs = load_loopbacks()
    print(f"[src] Loopbacks: {lbs}\n")

    # 1) Borrar regla antigua si se solicita y existe
    if args.delete_old is not None:
        old_tid = args.delete_old
        if rule_exists(dest, old_tid):
            print(f"[src] → Borrando regla antigua: tunnel{old_tid}")
            res = ssh_ru(f"/usr/sbin/ip -6 rule del to {dest}/64 lookup tunnel{old_tid}")
            print(f"[src]   return {res.returncode}, stderr: {res.stderr.decode().strip()}")

    # 2) Asegurar la entrada en rt_tables
    if args.new_table or not table_entry_exists(tid):
        line = f"{tid} tunnel{tid}"
        print(f"[src] → Añadiendo rt_tables: {line}")
        res = ssh_ru(f"sh -c \"echo {shlex.quote(line)} >> /etc/iproute2/rt_tables\"")
        print(f"[src]   return {res.returncode}, stderr: {res.stderr.decode().strip()}")

    # 3) Determinar método: add o replace según existencia previa
    use_replace = route_exists(dest, tid)
    method = "replace" if use_replace else "add"
    print(f"[src] → Determinando método de ruta: {'existía' if use_replace else 'no existía'}. Usando '{method}'")

    segs = ','.join(lbs[n] for n in path[1:])
    cmd_route = (
        f"/usr/sbin/ip -6 route {method} {dest}/64 "
        f"encap seg6 mode encap segs {segs} dev eth1 table tunnel{tid}"
    )
    print(f"[src] Instalando ruta: {cmd_route}")
    res_route = ssh_ru(cmd_route)
    print(f"[src]   return {res_route.returncode}, stdout: {res_route.stdout.decode().strip()}, stderr: {res_route.stderr.decode().strip()}")

    # 4) Añadir regla de lookup si no existe
    if not rule_exists(dest, tid):
        cmd_rule = f"/usr/sbin/ip -6 rule add to {dest}/64 lookup tunnel{tid}"
        print(f"[src] → Añadiendo regla: {cmd_rule}")
        res_rule = ssh_ru(cmd_rule)
        print(f"[src]   return {res_rule.returncode}, stderr: {res_rule.stderr.decode().strip()}")

    print(f"[src] Done: flow {dest} (v{args.version}) → tunnel{tid}, path={path}")

if __name__ == '__main__':
    main()