#!/usr/bin/env python3
import json
import subprocess
import shlex
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


def route_exists_for_dest(dest):
    """
    Comprueba remotamente si ya existe alguna ruta para el destino específico.
    """
    cmd = f"/usr/sbin/ip -6 route show to {shlex.quote(dest)}"
    proc = ssh_ru(cmd)
    
    print(f"[src] Verificando ruta existente para {dest}:")
    print(f"[src]   Comando: {cmd}")
    print(f"[src]   Return code: {proc.returncode}")
    print(f"[src]   Stdout: '{proc.stdout.decode().strip()}'")
    print(f"[src]   Stderr: '{proc.stderr.decode().strip()}'")
    
    if proc.returncode != 0:
        print(f"[src]   → Comando falló, asumiendo que no existe ruta")
        return False
    
    stdout = proc.stdout.decode().strip()
    exists = len(stdout) > 0
    print(f"[src]   → Ruta existe: {exists}")
    return exists


def main():
    p = argparse.ArgumentParser(description="Instala rutas SRv6 en RU usando iproute2 directamente.")
    p.add_argument("dest_prefix", help="Prefijo IPv6 del flujo, p.ej. fd00:0:2::2/64")
    p.add_argument("path_json", help="JSON-encoded list de nodos de la ruta")
    p.add_argument("--replace", action="store_true", help="Usar replace en lugar de add")
    p.add_argument("--high-occupancy", action="store_true", help="Indica si la ruta usa nodos con alta ocupación")
    args = p.parse_args()

    # Debug logging de argumentos de entrada
    print(f"[src] Args: dest_prefix={args.dest_prefix}, replace={args.replace}, "
          f"high_occupancy={args.high_occupancy}, path_json={args.path_json}")

    dest = args.dest_prefix.split('/')[0]
    path = json.loads(args.path_json)

    # Mostrar aviso si la ruta usa nodos con alta ocupación
    if args.high_occupancy:
        print(f"[src] AVISO: La ruta para {dest} usa nodos con alta ocupación (entre 80% y 95%)")

    print(f"[src] Cargando /app/networkinfo.json...")
    lbs = load_loopbacks()
    print(f"[src] Loopbacks: {lbs}\n")

    # Determinar método: add o replace
    # Si se pasa --replace O si ya existe una ruta para este destino, usar replace
    use_replace = args.replace or route_exists_for_dest(dest)
    method = "replace" if use_replace else "add"
    
    print(f"[src] → Determinando método de ruta:")
    print(f"[src]   - args.replace: {args.replace}")
    print(f"[src]   - route_exists_for_dest({dest}): {route_exists_for_dest(dest)}")
    print(f"[src]   - Método elegido: {method}")

    # Construir comando de ruta SRv6
    segs = ','.join(lbs[n] for n in path[1:])
    cmd_route = (
        f"/usr/sbin/ip -6 route {method} {dest} "
        f"encap seg6 mode encap segs {segs} dev eth1"
    )
    
    print(f"[src] Instalando ruta: {cmd_route}")
    res_route = ssh_ru(cmd_route)
    print(f"[src]   return {res_route.returncode}, stdout: {res_route.stdout.decode().strip()}, stderr: {res_route.stderr.decode().strip()}")

    # Si el comando falló con 'add' porque la ruta ya existe, intentar con 'replace'
    if res_route.returncode != 0 and method == "add" and "File exists" in res_route.stderr.decode():
        print(f"[src] → Comando 'add' falló porque ruta existe, reintentando con 'replace'")
        cmd_route_replace = (
            f"/usr/sbin/ip -6 route replace {dest} "
            f"encap seg6 mode encap segs {segs} dev eth1"
        )
        print(f"[src] Reintentando: {cmd_route_replace}")
        res_route = ssh_ru(cmd_route_replace)
        print(f"[src]   return {res_route.returncode}, stdout: {res_route.stdout.decode().strip()}, stderr: {res_route.stderr.decode().strip()}")

    print(f"[src] Done: flow {dest} → path={path}")

if __name__ == '__main__':
    main()