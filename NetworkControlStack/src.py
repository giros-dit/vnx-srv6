import json
import sys
import os
import subprocess
import ipaddress

def load_loopbacks(path):
    with open(path) as f:
        data = json.load(f)
    # strip any mask
    return { n: lp.split('/')[0] for n, lp in data.get("loopbacks", {}).items() }

def ssh_ru(cmd):
    base = ["ssh", "-o", "StrictHostKeyChecking=no", "root@ru.across-tc32.svc.cluster.local"]
    full = base + [cmd]
    subprocess.run(full, check=True)

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("dest_prefix", help="IPv6 prefix of the flow")
    p.add_argument("new_table_id", help="ID of the table to install")
    p.add_argument("path_json", help="JSON-encoded list of nodes")
    p.add_argument("--delete-old", metavar="OLD_TID", help="remove old ip rule")
    args = p.parse_args()

    dest = args.dest_prefix.split('/')[0]
    new_tid = args.new_table_id
    path = json.loads(args.path_json)

    print(f"[src] Cargando /app/networkinfo.json")
    loopbacks = load_loopbacks("/app/networkinfo.json")
    print(f"[src] Loopbacks: {loopbacks}")

    # 1) If requested, delete old ip6 rule on RU
    if args.delete_old:
        old = args.delete_old
        print(f"[src] Borrando regla antigua: ip -6 rule del to {dest} lookup tunnel{old}")
        ssh_ru(f"ip -6 rule del to {dest} lookup tunnel{old}")

    # 2) Ensure table entry in rt_tables
    entry = f"{new_tid} tunnel{new_tid}"
    check_cmd = f"grep -qx '{entry}' /etc/iproute2/rt_tables"
    add_cmd   = f"echo '{entry}' >> /etc/iproute2/rt_tables"
    print(f"[src] Asegurando tabla: {entry}")
    ssh_ru(f"sh -c \"{check_cmd} || {add_cmd}\"")

    # 3) Build seg6 command: dest uses <dest> prefix, segments = loopback for each hop after 'ru'
    segs = [ loopbacks[n] for n in path[1:] ]
    segs_str = ",".join(segs)
    route_cmd = (
        f"ip -6 route add {dest}/64 "
        f"encap seg6 mode encap segs {segs_str} dev eth1 table tunnel{new_tid}"
    )
    print(f"[src] Instalando ruta: {route_cmd}")
    ssh_ru(route_cmd)

    # 4) Add IPv6 rule for lookup
    rule_cmd = f"ip -6 rule add to {dest}/64 lookup tunnel{new_tid}"
    print(f"[src] Añadiendo regla IPv6: {rule_cmd}")
    ssh_ru(rule_cmd)

    print(f"[src] Done: flow → tunnel{new_tid}, path: {path}")

if __name__ == "__main__":
    main()