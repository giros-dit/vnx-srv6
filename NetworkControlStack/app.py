#!/usr/bin/env python3
import json
import subprocess
import os
import urllib.parse
import threading
import time
import contextlib
import hashlib
from flask import Flask, request, jsonify
import logging
import boto3
from botocore.exceptions import ClientError

from pce import get_trigger_function

trigger_recalc = get_trigger_function()

app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variable de entorno
LOGTS = os.environ.get('LOGTS', 'false').lower() == 'true'

# Configuración S3 (Minio)
S3_ENDPOINT = os.environ.get('S3_ENDPOINT')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name='local'
)

class SimplifiedLock:
    """
    Lock simplificado con timeout más corto para operaciones de lectura
    """
    def __init__(self, name):
        self.name = name
        self.lock = threading.RLock()
        self.acquired_count = 0
    
    def acquire(self, blocking=True, timeout=None):
        """Acquire the lock"""
        try:
            acquired = self.lock.acquire(blocking=blocking, timeout=timeout or 10)  # Timeout más corto
            if acquired:
                self.acquired_count += 1
                logger.info(f"Lock '{self.name}' acquired (count: {self.acquired_count})")
            return acquired
        except Exception as e:
            logger.error(f"Error acquiring lock '{self.name}': {e}")
            return False
    
    def release(self):
        """Release the lock"""
        try:
            self.lock.release()
            self.acquired_count = max(0, self.acquired_count - 1)
            logger.info(f"Lock '{self.name}' released (count: {self.acquired_count})")
            return True
        except Exception as e:
            logger.error(f"Error releasing lock '{self.name}': {e}")
            return False

# Lock simplificado para operaciones de flows - ahora solo para coordinación API
api_coordination_lock = SimplifiedLock("api_coordination")

@contextlib.contextmanager
def acquire_api_lock(timeout=5):
    """
    Context manager para coordinar las APIs (timeout más corto)
    """
    acquired = api_coordination_lock.acquire(blocking=True, timeout=timeout)
    if not acquired:
        raise RuntimeError(f"No se pudo adquirir el lock de API en {timeout}s")
    
    try:
        yield
    finally:
        api_coordination_lock.release()

def decode_ip_from_url(encoded_ip):
    """Decodifica la IP de la URL"""
    try:
        decoded = encoded_ip.replace('_', '/')
        return urllib.parse.unquote(decoded)
    except Exception as e:
        logger.error(f"Error decodificando IP {encoded_ip}: {e}")
        return None

def encode_ip_for_url(ip):
    """Codifica la IP para usar en URL"""
    try:
        encoded = urllib.parse.quote(ip, safe='')
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
            cwd='/app',
            timeout=60  # Timeout de 60 segundos
        )
        
        logger.info(f"flows.py return code: {result.returncode}")
        if result.stdout:
            logger.info(f"flows.py stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"flows.py stderr: {result.stderr}")
            
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error("flows.py timeout después de 60 segundos")
        return False, "", "Timeout después de 60 segundos"
    except Exception as e:
        logger.error(f"Error ejecutando flows.py: {e}")
        return False, "", str(e)

def run_src_command(dest_prefix, route_json, replace=False):
    """Ejecuta el comando src.py para instalar rutas"""
    try:
        cmd = ['python3', '/app/src.py', dest_prefix, route_json]
        if replace:
            cmd.append('--replace')
            
        logger.info(f"Ejecutando src.py: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd='/app',
            timeout=60  # Timeout de 60 segundos
        )
        
        logger.info(f"src.py return code: {result.returncode}")
        if result.stdout:
            logger.info(f"src.py stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"src.py stderr: {result.stderr}")
        
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error("src.py timeout después de 60 segundos")
        return False, "", "Timeout después de 60 segundos"
    except Exception as e:
        logger.error(f"Error ejecutando src.py: {e}")
        return False, "", str(e)

def delete_route_from_ru(dest_ip):
    """Elimina la ruta del destino en RU usando ip -6 route del"""
    try:
        cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', 
               '-o', 'ConnectTimeout=10',
               'root@ru.across-tc32.svc.cluster.local', 
               f'PATH=$PATH:/usr/sbin:/sbin /usr/sbin/ip -6 route del {dest_ip}']
        
        logger.info(f"Eliminando ruta en RU: {' '.join(cmd[:-1])} '{cmd[-1]}'")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd='/app',
            timeout=30
        )
        
        logger.info(f"ip route del return code: {result.returncode}")
        if result.stdout:
            logger.info(f"ip route del stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"ip route del stderr: {result.stderr}")
            
        # Retornar True si no hay error, o si el error es que la ruta no existe
        return (result.returncode == 0 or 
                "No such file or directory" in result.stderr or 
                "No route to host" in result.stderr or
                "Network is unreachable" in result.stderr)
        
    except subprocess.TimeoutExpired:
        logger.error("SSH timeout eliminando ruta")
        return False
    except Exception as e:
        logger.error(f"Error eliminando ruta en RU: {e}")
        return False

def get_flows_data_with_debug():
    """Obtiene los datos actuales de flows con logging detallado"""
    try:
        success, stdout, stderr = run_flows_command(['--list'])
        logger.info(f"[DEBUG] flows.py --list success: {success}")
        
        if success and stdout:
            logger.info(f"[DEBUG] flows.py raw stdout:\n{stdout}")
            
            lines = stdout.split('\n')
            json_start = -1
            
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith('{'):
                    json_start = i
                    break
            
            if json_start >= 0:
                json_lines = lines[json_start:]
                json_text = '\n'.join(json_lines).strip()
                
                logger.info(f"[DEBUG] Extracted JSON text:\n{json_text}")
                
                try:
                    data = json.loads(json_text)
                    logger.info(f"[DEBUG] Parsed JSON successfully: {len(data.get('flows', []))} flows found")
                    
                    # Log cada flujo individualmente para debugging
                    for i, flow in enumerate(data.get('flows', [])):
                        logger.info(f"[DEBUG] Flow {i+1}: {flow.get('_id')} -> route: {flow.get('route')} (v{flow.get('version', 1)})")
                    
                    if not isinstance(data, dict):
                        logger.warning("[DEBUG] Data no es dict, retornando vacío")
                        return {"flows": []}
                    if "flows" not in data:
                        logger.warning("[DEBUG] No hay campo 'flows', añadiéndolo")
                        data["flows"] = []
                    
                    return data
                    
                except json.JSONDecodeError as e:
                    logger.error(f"[DEBUG] Error parseando JSON: {e}")
                    logger.error(f"[DEBUG] JSON text que falló: {repr(json_text)}")
                    return {"flows": []}
            else:
                logger.warning("[DEBUG] No se encontró inicio de JSON válido en stdout")
                logger.warning(f"[DEBUG] Todas las líneas: {lines}")
                return {"flows": []}
        else:
            logger.error(f"[DEBUG] Error obteniendo flows - success: {success}")
            if stderr:
                logger.error(f"[DEBUG] flows.py stderr: {stderr}")
            if stdout:
                logger.error(f"[DEBUG] flows.py stdout: {stdout}")
            return {"flows": []}
    except Exception as e:
        logger.error(f"[DEBUG] Excepción parseando flows data: {e}")
        return {"flows": []}

@app.route('/flows', methods=['GET'])
def list_flows():
    """GET /flows - Lista todos los flujos (solo lectura, sin cola)"""
    try:
        logger.info("[GET] Solicitando lista de flujos")
        
        # Para lectura, usar timeout muy corto y sin cola
        with acquire_api_lock(timeout=2):
            data = get_flows_data_with_debug()
            
        logger.info(f"[GET] Datos obtenidos exitosamente: {len(data.get('flows', []))} flujos")
        return jsonify(data), 200
    except RuntimeError as e:
        logger.error(f"[GET] Error adquiriendo lock en GET /flows: {e}")
        return jsonify({"error": "Sistema ocupado, reintente en unos momentos"}), 503
    except Exception as e:
        logger.error(f"[GET] Error en GET /flows: {e}")
        return jsonify({"error": "Error interno del servidor", "flows": []}), 500

@app.route('/flows/<encoded_ip>', methods=['POST'])
def create_flow(encoded_ip):
    """POST /flows/<ip> - Crea un nuevo flujo usando cola FIFO"""
    try:
        # Capturar timestamp de la API inmediatamente
        api_timestamp = time.time() if LOGTS else None
        
        # Decodificar la IP
        ip = decode_ip_from_url(encoded_ip)
        if not ip:
            return jsonify({"error": "IP inválida"}), 400
        
        # Obtener datos del body (si existe)
        data = request.get_json() if request.is_json else {}
        route = data.get('route', [])
        
        logger.info(f"[CREATE] Iniciando creación de flujo para IP: {ip}")
        
        # Solo coordinación ligera de API, el flows.py maneja la cola
        with acquire_api_lock(timeout=3):
            logger.info(f"[CREATE] Lock de API adquirido para IP: {ip}")
            
            # Preparar argumentos para flows.py
            cmd_args = [ip, '--add']
            
            if route:
                route_json = json.dumps(route)
                cmd_args.extend(['--route', route_json])
            
            # Añadir timestamp de API si LOGTS está habilitado
            if api_timestamp is not None:
                cmd_args.extend(['--api-timestamp', str(api_timestamp)])
                logger.info(f"Pasando timestamp de API: {api_timestamp}")
            
            # Crear flujo con flows.py (ahora usa cola interna)
            success, stdout, stderr = run_flows_command(cmd_args)
            
            if not success:
                logger.error(f"[CREATE] Error en flows.py: {stderr}")
                if "ya existe" in stderr:
                    return jsonify({"error": f"El flujo {ip} ya existe"}), 409
                return jsonify({"error": f"Error creando flujo: {stderr}"}), 500
            
            logger.info(f"[CREATE] Flujo {ip} encolado exitosamente")
        
        # El lock se libera aquí automáticamente
        
        # Verificación post-creación (fuera del lock)
        time.sleep(0.1)  # Breve pausa para que se procese la cola
        logger.info(f"[CREATE] === VERIFICACIÓN POST-CREACIÓN {ip} ===")
        debug_data = get_flows_data_with_debug()
        our_flow = next((f for f in debug_data.get('flows', []) if f.get('_id') == ip), None)
        if our_flow:
            logger.info(f"[CREATE] ✅ CONFIRMADO: Flujo {ip} creado correctamente")
        else:
            logger.warning(f"[CREATE] ⚠️  Flujo {ip} aún procesándose en cola")
        
        # Si no tiene ruta, forzar recálculo
        if not route:
            trigger_recalc()
            logger.info(f"[CREATE] Recálculo forzado para flujo {ip} sin ruta")
        
        # Si tiene ruta, ejecutar src.py para instalar la ruta
        if route:
            dest_prefix = f"{ip}/64" if '/' not in ip else ip
            route_json = json.dumps(route)
            
            src_success, src_stdout, src_stderr = run_src_command(dest_prefix, route_json)
            if not src_success:
                logger.warning(f"[CREATE] Flujo creado pero error instalando ruta: {src_stderr}")
                return jsonify({
                    "message": f"Flujo {ip} creado pero error instalando ruta",
                    "warning": src_stderr
                }), 201
        
        logger.info(f"[CREATE] Proceso completado exitosamente para {ip}")
        return jsonify({"message": f"Flujo {ip} creado exitosamente"}), 201
        
    except RuntimeError as e:
        logger.error(f"[CREATE] Error adquiriendo lock: {e}")
        return jsonify({"error": "Sistema ocupado, reintente en unos momentos"}), 503
    except Exception as e:
        logger.error(f"[CREATE] Error inesperado: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/flows/<encoded_ip>', methods=['PUT'])
def update_flow(encoded_ip):
    """PUT /flows/<ip> - Actualiza la ruta de un flujo usando cola FIFO"""
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
        
        logger.info(f"[UPDATE] Iniciando actualización de flujo para IP: {ip}")
        
        # Solo coordinación ligera de API
        with acquire_api_lock(timeout=3):
            logger.info(f"[UPDATE] Lock de API adquirido para IP: {ip}")
            
            # Actualizar flujo con flows.py (ahora usa cola interna)
            route_json = json.dumps(route)
            success, stdout, stderr = run_flows_command([ip, '--update', '--route', route_json])
            
            if not success:
                logger.error(f"[UPDATE] Error en flows.py: {stderr}")
                if "no encontrado" in stderr:
                    return jsonify({"error": f"El flujo {ip} no existe"}), 404
                return jsonify({"error": f"Error actualizando flujo: {stderr}"}), 500
            
            logger.info(f"[UPDATE] Flujo {ip} encolado para actualización")
        
        # Verificación post-actualización (fuera del lock)
        time.sleep(0.1)  # Breve pausa para que se procese la cola
        logger.info(f"[UPDATE] === VERIFICACIÓN POST-ACTUALIZACIÓN {ip} ===")
        debug_data = get_flows_data_with_debug()
        our_flow = next((f for f in debug_data.get('flows', []) if f.get('_id') == ip), None)
        if our_flow:
            logger.info(f"[UPDATE] ✅ CONFIRMADO: Flujo {ip} actualizado")
        else:
            logger.warning(f"[UPDATE] ⚠️  Flujo {ip} aún procesándose en cola")
        
        # Ejecutar src.py con --replace para actualizar la ruta
        dest_prefix = f"{ip}/64" if '/' not in ip else ip
        src_success, src_stdout, src_stderr = run_src_command(dest_prefix, route_json, replace=True)
        
        if not src_success:
            logger.warning(f"[UPDATE] Flujo actualizado pero error instalando ruta: {src_stderr}")
            return jsonify({
                "message": f"Flujo {ip} actualizado pero error instalando ruta",
                "warning": src_stderr
            }), 200
        
        logger.info(f"[UPDATE] Proceso completado exitosamente para {ip}")
        return jsonify({"message": f"Flujo {ip} actualizado exitosamente"}), 200
        
    except RuntimeError as e:
        logger.error(f"[UPDATE] Error adquiriendo lock: {e}")
        return jsonify({"error": "Sistema ocupado, reintente en unos momentos"}), 503
    except Exception as e:
        logger.error(f"[UPDATE] Error inesperado: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/flows/<encoded_ip>', methods=['DELETE'])
def delete_flow(encoded_ip):
    """DELETE /flows/<ip> - Elimina un flujo usando cola FIFO"""
    try:
        # Decodificar la IP
        ip = decode_ip_from_url(encoded_ip)
        if not ip:
            return jsonify({"error": "IP inválida"}), 400
        
        logger.info(f"[DELETE] Iniciando eliminación de flujo: {ip}")

        # Solo coordinación ligera de API
        with acquire_api_lock(timeout=3):
            logger.info(f"[DELETE] Lock de API adquirido para IP: {ip}")
            
            # Eliminar flujo con flows.py (ahora usa cola interna)
            success, stdout, stderr = run_flows_command([ip, '--delete'])
            logger.info(f"[DELETE] Resultado eliminación flujo: success={success}")
            
            flow_existed = True
            if not success:
                if "no encontrado" in stderr or "no encontrado" in stdout:
                    flow_existed = False
                    logger.info(f"[DELETE] Flujo {ip} no existía en el registro")
                else:
                    logger.error(f"[DELETE] Error eliminando flujo: {stderr}")
                    return jsonify({
                        "error": f"Error eliminando flujo: {stderr or stdout or 'desconocido'}"
                    }), 500
            else:
                logger.info(f"[DELETE] Flujo {ip} encolado para eliminación")
        
        # Verificación post-eliminación (fuera del lock)
        time.sleep(0.1)  # Breve pausa para que se procese la cola
        logger.info(f"[DELETE] === VERIFICACIÓN POST-ELIMINACIÓN {ip} ===")
        debug_data = get_flows_data_with_debug()
        our_flow = next((f for f in debug_data.get('flows', []) if f.get('_id') == ip), None)
        if our_flow:
            logger.warning(f"[DELETE] ⚠️  Flujo {ip} aún en cola de procesamiento")
        else:
            logger.info(f"[DELETE] ✅ CONFIRMADO: Flujo {ip} eliminado correctamente")
        
        # Eliminar la ruta en RU (fuera del lock)
        dest_ip = ip if '/' not in ip else ip.split('/')[0]
        logger.info(f"[DELETE] Eliminando ruta en RU para: {dest_ip}")
        route_deleted = delete_route_from_ru(dest_ip)
        logger.info(f"[DELETE] Resultado eliminación ruta: {route_deleted}")
        
        # Preparar respuesta basada en los resultados
        if flow_existed and route_deleted:
            return jsonify({"message": f"Flujo {ip} y su ruta eliminados exitosamente"}), 200
        elif flow_existed and not route_deleted:
            return jsonify({
                "message": f"Flujo {ip} eliminado del registro",
                "warning": "Advertencia: no se pudo eliminar ruta en RU"
            }), 200
        elif not flow_existed and route_deleted:
            return jsonify({
                "message": f"Ruta eliminada de RU, pero flujo {ip} no existía en el registro"
            }), 200
        else:
            return jsonify({
                "message": f"Flujo {ip} no existía y no había ruta que eliminar"
            }), 404

    except RuntimeError as e:
        logger.error(f"[DELETE] Error adquiriendo lock: {e}")
        return jsonify({"error": "Sistema ocupado, reintente en unos momentos"}), 503
    except Exception as e:
        logger.exception(f"[DELETE] Excepción inesperada al eliminar flujo {encoded_ip}")
        return jsonify({"error": f"Excepción: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/locks/status', methods=['GET'])
def locks_status():
    """Endpoint para verificar el estado de los locks (para debugging)"""
    try:
        status = {
            "local_lock_locked": api_coordination_lock.acquired_count > 0,
            "local_lock_count": api_coordination_lock.acquired_count,
            "lock_type": "simplified_threading_lock",
            "lock_name": api_coordination_lock.name
        }
        
        return jsonify(status), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/queue/status', methods=['GET'])
def queue_status():
    """Endpoint para verificar el estado de la cola (para debugging)"""
    try:
        # Importar flows para acceder a la cola
        import flows
        
        status = {
            "queue_size": flows.write_queue.qsize() if hasattr(flows, 'write_queue') else 0,
            "worker_running": flows.write_worker_running if hasattr(flows, 'write_worker_running') else False,
            "api_lock_count": api_coordination_lock.acquired_count,
            "queue_dir_exists": os.path.exists("/tmp/flows_queue")
        }
        
        return jsonify(status), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    
    # Lanzar pce.py como subproceso
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

    logger.info("Iniciando Flask API con sistema de cerrojos simplificados...")
    app.run(host='0.0.0.0', port=5000, debug=False)