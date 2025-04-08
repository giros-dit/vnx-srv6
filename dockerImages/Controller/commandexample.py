#!/usr/bin/env python3
"""
Este script se ejecuta desde un pod en un cluster externo y permite ejecutar un comando en otro pod del mismo cluster.
El pod de destino pertenece a un deploy unipod llamado "ru" y su nombre completo varía (por ejemplo, "ru-88499f4f4-v46ms").
El script utiliza la API de Kubernetes para encontrar el pod y ejecutar el siguiente comando:

  docker exec ru ip -6 route add fd00:0:2::2 encap seg6 mode encap segs fcff:2::1,fcff:1::1,fcff:6::1 dev eth1 table tunel1
"""

from kubernetes import client, config, stream

def exec_command_in_ru():
    # Cargar la configuración in-cluster (se asume que el script se ejecuta dentro del cluster)
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    
    namespace = "across-tc32"
    
    # Listar los pods del namespace y buscar el pod cuyo nombre comienza por "ru-"
    pods = v1.list_namespaced_pod(namespace=namespace)
    ru_pod = None
    for pod in pods.items:
        if pod.metadata.name.startswith("ru-"):
            ru_pod = pod.metadata.name
            break
    
    if not ru_pod:
        print(f"No se encontró un pod del deploy 'ru' en el namespace {namespace}.")
        return
    
    # Comando a ejecutar en el pod encontrado
    command = [
        "docker", "exec", "ru", "ip", "-6", "route", "add",
        "fd00:0:2::2", "encap", "seg6", "mode", "encap", "segs",
        "fcff:2::1,fcff:1::1,fcff:6::1", "dev", "eth1", "table", "tunel1"
    ]
    
    print(f"Ejecutando comando en el pod: {ru_pod}")
    
    try:
        resp = stream.stream(
            v1.connect_get_namespaced_pod_exec,
            ru_pod,
            namespace,
            command=command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False
        )
        print("Salida del comando:")
        print(resp)
    except Exception as e:
        print("Error ejecutando el comando:")
        print(e)

if __name__ == '__main__':
    exec_command_in_ru()
