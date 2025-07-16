#!/usr/bin/env python3
import json
import subprocess
import os
import urllib.parse
from flask import Flask, request, jsonify
import time
import logging
import threading

from pce import get_trigger_function

trigger_recalc = get_trigger_function()


app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variable de entorno
LOGTS = os.environ.get('LOGTS', 'false').lower() == 'true'


def decode_ip_from_url(encoded_ip):
    """Decodifica la IP de la URL"""
    try:
        # Reemplazar caracteres seguros por los originales
        decoded = encoded_ip.replace('_', '/')
        # URL decode
        return urllib.parse.unquote(decoded)
    except Exception as e:
        logger.error(f"Error decodificando IP {encoded_ip}: {e}")
        return None

def encode_ip_for_url(ip):
    """Codifica la IP para usar en URL"""
    try:
        # URL encode
        encoded = urllib.parse.quote(ip, safe='')
        # Reemplazar caracteres problemáticos
        return encoded.replace('/', '_')
    except Exception as e:
        logger.error(f"Error codificando IP {ip}: {e}")
        return None

def run_flows_command(args):
    """Ejecuta el comando flows.py con los argumentos dados"""
    try:
        cmd = ['python3', '/app/flows.py'] + args
        logger.info(f"Ejecutando: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd='/app'
        )
        
        logger.info(f"flows.py return code: {result.returncode}")
        logger.info(f"flows.py stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"flows.py stderr: {result.stderr}")
            
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        logger.error(f"Error ejecutando flows.py: {e}")
        return False, "", str(e)

def delete_route_from_ru(dest_ip):
    """Elimina la ruta del destino en RU usando ip -6 route del"""
    try:
        # Construir el comando para eliminar la ruta
        cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', 'root@ru.across-tc32.svc.cluster.local', 
               f'/usr/sbin/ip -6 route del {dest_ip}']
        
        logger.info(f"Eliminando ruta en RU: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd='/app'
        )
        
        logger.info(f"ip route del return code: {result.returncode}")
        logger.info(f"ip route del stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"ip route del stderr: {result.stderr}")
            
        # Retornar True si no hay error, o si el error es que la ruta no existe
        return result.returncode == 0 or "No such file or directory" in result.stderr or "No route to host" in result.stderr
        
    except Exception as e:
        logger.error(f"Error eliminando ruta en RU: {e}")
        return False
    
def add_timestamp_to_flow(flow_data, event_type, counter=1):
    """Añade timestamp al flujo si LOGTS está habilitado"""
    if not LOGTS:
        return
    
    timestamp = time.time()
    base_key = f"ts_{event_type}"
    
    if counter > 1:
        key = f"{base_key}_{counter}"
    else:
        key = base_key
    
    if "timestamps" not in flow_data:
        flow_data["timestamps"] = {}
    
    flow_data["timestamps"][key] = timestamp
    logger.info(f"Timestamp añadido: {key} = {timestamp} para flujo {flow_data.get('_id', '???')}")
    
def get_flows_data():
    """Obtiene los datos actuales de flows"""
    try:
        success, stdout, stderr = run_flows_command(['--list'])
        logger.info(f"flows.py --list success: {success}")
        logger.info(f"flows.py --list stdout: {repr(stdout)}")
        
        if success:
            # Buscar el inicio del JSON (primera línea que empieza con {)
            lines = stdout.split('\n')
            json_start = -1
            
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith('{'):
                    json_start = i
                    break
            
            if json_start >= 0:
                # Tomar todas las líneas desde el inicio del JSON hasta el final
                json_lines = lines[json_start:]
                json_text = '\n'.join(json_lines).strip()
                
                logger.info(f"JSON text encontrado: {repr(json_text)}")
                
                try:
                    data = json.loads(json_text)
                    logger.info(f"JSON parseado exitosamente: {data}")
                    
                    # Asegurar que siempre tenga la estructura correcta
                    if not isinstance(data, dict):
                        logger.warning("Data no es dict, retornando vacío")
                        return {"flows": []}
                    if "flows" not in data:
                        logger.warning("No hay campo 'flows', añadiéndolo")
                        data["flows"] = []
                    
                    return data
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Error parseando JSON completo: {e}")
                    logger.error(f"JSON text: {json_text}")
                    return {"flows": []}
            else:
                logger.warning("No se encontró inicio de JSON válido")
                return {"flows": []}
        else:
            logger.error(f"Error obteniendo flows: {stderr}")
            return {"flows": []}
    except Exception as e:
        logger.error(f"Error parseando flows data: {e}")
        return {"flows": []}

@app.route('/flows', methods=['GET'])
def list_flows():
    """GET /flows - Lista todos los flujos"""
    try:
        logger.info("Solicitando lista de flujos")
        data = get_flows_data()
        logger.info(f"Datos obtenidos: {data}")
        return jsonify(data), 200
    except Exception as e:
        logger.error(f"Error en GET /flows: {e}")
        return jsonify({"error": "Error interno del servidor", "flows": []}), 500

@app.route('/flows/<encoded_ip>', methods=['POST'])
def create_flow(encoded_ip):
    """POST /flows/<ip> - Crea un nuevo flujo"""
    try:
        # Decodificar la IP
        ip = decode_ip_from_url(encoded_ip)
        if not ip:
            return jsonify({"error": "IP inválida"}), 400
        
        # Obtener datos del body (si existe)
        data = request.get_json() if request.is_json else {}
        route = data.get('route', [])
        
        logger.info(f"Creando flujo para IP: {ip} con ruta: {route}")
        
        # Crear flujo con flows.py
        if route:
            # Crear con ruta
            route_json = json.dumps(route)
            success, stdout, stderr = run_flows_command([ip, '--add', '--route', route_json])
        else:
            # Crear sin ruta
            success, stdout, stderr = run_flows_command([ip, '--add'])
            
            # Forzar recálculo si se crea SIN ruta
            trigger_recalc()
            logger.info(f"Recálculo inmediato forzado porque se creó flujo {ip} SIN ruta.")
 
        if not success:
            if "ya existe" in stderr:
                return jsonify({"error": f"El flujo {ip} ya existe"}), 409
            return jsonify({"error": f"Error creando flujo: {stderr}"}), 500
        
        if LOGTS:
            # Obtener el flujo recién creado y añadir timestamp
            flows_data = get_flows_data()
            for flow in flows_data.get("flows", []):
                if flow.get("_id") == ip:
                    add_timestamp_to_flow(flow, "api_created")
                    # Actualizar el flujo con el timestamp
                    timestamps_json = json.dumps(flow.get("timestamps", {}))
                    route_json_for_update = json.dumps(flow.get("route", []))
                    run_flows_command([ip, '--update', '--route', route_json_for_update, '--timestamps', timestamps_json])
                    break
        
        # Si tiene ruta, ejecutar src.py para instalar la ruta
        if route:
            # Asumir /64 por defecto si no se especifica
            dest_prefix = f"{ip}/64" if '/' not in ip else ip
            route_json = json.dumps(route)
            
            src_success, src_stdout, src_stderr = run_src_command(dest_prefix, route_json)
            if not src_success:
                logger.warning(f"Flujo creado pero error instalando ruta: {src_stderr}")
                return jsonify({
                    "message": f"Flujo {ip} creado pero error instalando ruta",
                    "warning": src_stderr
                }), 201
        
        return jsonify({"message": f"Flujo {ip} creado exitosamente"}), 201
        
    except Exception as e:
        logger.error(f"Error en POST /flows/{encoded_ip}: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/flows/<encoded_ip>', methods=['PUT'])
def update_flow(encoded_ip):
    """PUT /flows/<ip> - Actualiza la ruta de un flujo"""
    try:
        # Decodificar la IP
        ip = decode_ip_from_url(encoded_ip)
        if not ip:
            return jsonify({"error": "IP inválida"}), 400
        
        # Obtener datos del body
        if not request.is_json:
            return jsonify({"error": "Content-Type debe ser application/json"}), 400
        
        data = request.get_json()
        route = data.get('route')
        
        if not route or not isinstance(route, list):
            return jsonify({"error": "El campo 'route' es requerido y debe ser un array"}), 400
        
        logger.info(f"Actualizando flujo para IP: {ip} con nueva ruta: {route}")
        
        # Actualizar flujo con flows.py
        route_json = json.dumps(route)
        success, stdout, stderr = run_flows_command([ip, '--update', '--route', route_json])
        
        if not success:
            if "no encontrado" in stderr:
                return jsonify({"error": f"El flujo {ip} no existe"}), 404
            return jsonify({"error": f"Error actualizando flujo: {stderr}"}), 500
        
        # Ejecutar src.py con --replace para actualizar la ruta
        dest_prefix = f"{ip}/64" if '/' not in ip else ip
        src_success, src_stdout, src_stderr = run_src_command(dest_prefix, route_json, replace=True)
        
        if not src_success:
            logger.warning(f"Flujo actualizado pero error instalando ruta: {src_stderr}")
            return jsonify({
                "message": f"Flujo {ip} actualizado pero error instalando ruta",
                "warning": src_stderr
            }), 200
        
        return jsonify({"message": f"Flujo {ip} actualizado exitosamente"}), 200
        
    except Exception as e:
        logger.error(f"Error en PUT /flows/{encoded_ip}: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/flows/<encoded_ip>', methods=['DELETE'])
def delete_flow(encoded_ip):
    """DELETE /flows/<ip> - Elimina un flujo y su ruta en RU"""
    try:
        # Decodificar la IP
        ip = decode_ip_from_url(encoded_ip)
        if not ip:
            return jsonify({"error": "IP inválida"}), 400
        
        logger.info(f"Eliminando flujo para IP: {ip}")
        
        # Primero eliminar la ruta en RU
        dest_prefix = f"{ip}/64" if '/' not in ip else ip
        dest_ip = ip if '/' not in ip else ip.split('/')[0]
        
        route_deleted = delete_route_from_ru(dest_ip)
        if not route_deleted:
            logger.warning(f"No se pudo eliminar la ruta en RU para {dest_ip}")
        
        # Luego eliminar el flujo del registro
        success, stdout, stderr = run_flows_command([ip, '--delete'])
        
        if not success:
            if "no encontrado" in stderr:
                # Si la ruta se eliminó pero el flujo no existía
                if route_deleted:
                    return jsonify({"message": f"Ruta eliminada de RU, pero flujo {ip} no existía en el registro"}), 200
                else:
                    return jsonify({"error": f"El flujo {ip} no existe"}), 404
            return jsonify({"error": f"Error eliminando flujo: {stderr}"}), 500
        
        # Mensaje de éxito
        if route_deleted:
            return jsonify({"message": f"Flujo {ip} y su ruta eliminados exitosamente"}), 200
        else:
            return jsonify({"message": f"Flujo {ip} eliminado del registro (advertencia: no se pudo eliminar ruta de RU)"}), 200
        
    except Exception as e:
        logger.error(f"Error en DELETE /flows/{encoded_ip}: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Verificar que los archivos necesarios existen
    required_files = ['/app/flows.py', '/app/src.py', '/app/networkinfo.json']
    for file_path in required_files:
        if not os.path.exists(file_path):
            logger.error(f"Archivo requerido no encontrado: {file_path}")
            exit(1)
    
    # Verificar variables de entorno de S3
    required_env_vars = ['S3_ENDPOINT', 'S3_ACCESS_KEY', 'S3_SECRET_KEY', 'S3_BUCKET']
    for env_var in required_env_vars:
        if not os.environ.get(env_var):
            logger.error(f"Variable de entorno requerida no encontrada: {env_var}")
            exit(1)
    
    # Lanzar pce.py como un subproceso, redirigiendo su salida a los logs del proceso principal

    def stream_subprocess_output(pipe, log_func):
        for line in iter(pipe.readline, ''):
            if line:
                log_func(line.rstrip())
        pipe.close()

    pce_cmd = ['python3', '-u', '/app/pce.py']
    try:
        pce_proc = subprocess.Popen(
            pce_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd='/app'
        )

        # Hilos para redirigir stdout y stderr de pce.py a los logs
        threading.Thread(target=stream_subprocess_output, args=(pce_proc.stdout, logger.info), daemon=True).start()
        threading.Thread(target=stream_subprocess_output, args=(pce_proc.stderr, logger.error), daemon=True).start()
    except Exception as e:
        logger.error(f"Error lanzando pce.py: {e}")
        exit(1)

    logger.info("Iniciando Flask API para gestión de flujos...")
    app.run(host='0.0.0.0', port=5000, debug=False)