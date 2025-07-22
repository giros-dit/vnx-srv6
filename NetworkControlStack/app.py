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

class DistributedLock:
    """
    Implementa un lock distribuido usando S3 como backend
    """
    def __init__(self, lock_name, s3_client, bucket, timeout=30):
        self.lock_name = lock_name
        self.s3_client = s3_client
        self.bucket = bucket
        self.timeout = timeout
        self.lock_key = f"locks/{lock_name}.lock"
        self.owner_id = f"{os.getpid()}_{threading.current_thread().ident}_{time.time()}"
        
    def acquire(self, blocking=True, timeout=None):
        """
        Intenta adquirir el lock distribuido
        """
        start_time = time.time()
        actual_timeout = timeout or self.timeout
        
        while True:
            try:
                # Intentar crear el lock atomicamente
                lock_data = {
                    "owner": self.owner_id,
                    "acquired_at": time.time(),
                    "expires_at": time.time() + self.timeout
                }
                
                # Usar IfNoneMatch='*' para crear solo si no existe
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=self.lock_key,
                    Body=json.dumps(lock_data).encode(),
                    Metadata={'owner': self.owner_id},
                    IfNoneMatch='*'  # Solo crear si no existe
                )
                
                logger.info(f"Lock '{self.lock_name}' adquirido por {self.owner_id}")
                return True
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                
                if error_code == 'PreconditionFailed':
                    # El lock ya existe, verificar si ha expirado
                    try:
                        obj = self.s3_client.get_object(Bucket=self.bucket, Key=self.lock_key)
                        lock_data = json.loads(obj['Body'].read().decode())
                        
                        # Verificar si el lock ha expirado
                        if time.time() > lock_data.get('expires_at', 0):
                            logger.info(f"Lock '{self.lock_name}' expirado, intentando renovar")
                            # Intentar eliminar el lock expirado y reintentarlo
                            try:
                                self.s3_client.delete_object(Bucket=self.bucket, Key=self.lock_key)
                                continue  # Reintentar adquisición
                            except:
                                pass  # Si no se puede eliminar, continuar esperando
                        
                        # Lock activo, esperar si es modo blocking
                        if not blocking:
                            return False
                            
                        if timeout and (time.time() - start_time) >= actual_timeout:
                            logger.warning(f"Timeout esperando lock '{self.lock_name}'")
                            return False
                            
                        time.sleep(0.1)  # Esperar antes de reintentar
                        
                    except ClientError:
                        # Error leyendo el lock, asumir que está activo
                        if not blocking:
                            return False
                        time.sleep(0.1)
                else:
                    logger.error(f"Error adquiriendo lock: {e}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error inesperado adquiriendo lock: {e}")
                return False
    
    def release(self):
        """
        Libera el lock distribuido
        """
        try:
            # Verificar que somos el propietario antes de eliminar
            obj = self.s3_client.get_object(Bucket=self.bucket, Key=self.lock_key)
            lock_data = json.loads(obj['Body'].read().decode())
            
            if lock_data.get('owner') == self.owner_id:
                self.s3_client.delete_object(Bucket=self.bucket, Key=self.lock_key)
                logger.info(f"Lock '{self.lock_name}' liberado por {self.owner_id}")
                return True
            else:
                logger.warning(f"Intento de liberar lock '{self.lock_name}' sin ser propietario")
                return False
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                # El lock ya no existe, probablemente expiró
                logger.info(f"Lock '{self.lock_name}' ya no existe (probablemente expiró)")
                return True
            else:
                logger.error(f"Error liberando lock: {e}")
                return False
        except Exception as e:
            logger.error(f"Error inesperado liberando lock: {e}")
            return False

# Lock local para operaciones en memoria
local_lock = threading.RLock()

# Lock distribuido para operaciones de archivo
flows_lock = DistributedLock("flows_operations", s3_client, S3_BUCKET, timeout=60)

@contextlib.contextmanager
def acquire_flows_lock(timeout=30):
    """
    Context manager para adquirir el lock de flujos de forma segura
    """
    # Primero adquirir el lock local
    local_acquired = local_lock.acquire(timeout=1)
    if not local_acquired:
        raise RuntimeError("No se pudo adquirir el lock local")
    
    try:
        # Luego adquirir el lock distribuido
        distributed_acquired = flows_lock.acquire(blocking=True, timeout=timeout)
        if not distributed_acquired:
            raise RuntimeError(f"No se pudo adquirir el lock distribuido en {timeout}s")
        
        try:
            yield
        finally:
            # Liberar lock distribuido
            flows_lock.release()
    finally:
        # Liberar lock local
        local_lock.release()

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
            cwd='/app'
        )
        
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        logger.error(f"Error ejecutando src.py: {e}")
        return False, "", str(e)

def delete_route_from_ru(dest_ip):
    """Elimina la ruta del destino en RU usando ip -6 route del"""
    try:
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
            
        return result.returncode == 0 or "No such file or directory" in result.stderr or "No route to host" in result.stderr
        
    except Exception as e:
        logger.error(f"Error eliminando ruta en RU: {e}")
        return False

def get_flows_data():
    """Obtiene los datos actuales de flows - DEBE ejecutarse dentro del lock"""
    try:
        success, stdout, stderr = run_flows_command(['--list'])
        logger.info(f"flows.py --list success: {success}")
        
        if success:
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
                
                try:
                    data = json.loads(json_text)
                    logger.info(f"JSON parseado exitosamente")
                    
                    if not isinstance(data, dict):
                        logger.warning("Data no es dict, retornando vacío")
                        return {"flows": []}
                    if "flows" not in data:
                        logger.warning("No hay campo 'flows', añadiéndolo")
                        data["flows"] = []
                    
                    return data
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Error parseando JSON: {e}")
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
        
        # Para lectura, usar un timeout más corto
        with acquire_flows_lock(timeout=10):
            data = get_flows_data()
            
        logger.info(f"Datos obtenidos exitosamente")
        return jsonify(data), 200
    except RuntimeError as e:
        logger.error(f"Error adquiriendo lock en GET /flows: {e}")
        return jsonify({"error": "Sistema ocupado, reintente en unos momentos"}), 503
    except Exception as e:
        logger.error(f"Error en GET /flows: {e}")
        return jsonify({"error": "Error interno del servidor", "flows": []}), 500

@app.route('/flows/<encoded_ip>', methods=['POST'])
def create_flow(encoded_ip):
    """POST /flows/<ip> - Crea un nuevo flujo"""
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
        
        # Adquirir lock antes de cualquier operación
        with acquire_flows_lock(timeout=30):
            logger.info(f"[CREATE] Lock adquirido para IP: {ip}")
            
            # Preparar argumentos para flows.py
            cmd_args = [ip, '--add']
            
            if route:
                route_json = json.dumps(route)
                cmd_args.extend(['--route', route_json])
            
            # Añadir timestamp de API si LOGTS está habilitado
            if api_timestamp is not None:
                cmd_args.extend(['--api-timestamp', str(api_timestamp)])
                logger.info(f"Pasando timestamp de API: {api_timestamp}")
            
            # Crear flujo con flows.py
            success, stdout, stderr = run_flows_command(cmd_args)
            
            if not success:
                logger.error(f"[CREATE] Error en flows.py: {stderr}")
                if "ya existe" in stderr:
                    return jsonify({"error": f"El flujo {ip} ya existe"}), 409
                return jsonify({"error": f"Error creando flujo: {stderr}"}), 500
            
            logger.info(f"[CREATE] Flujo {ip} creado exitosamente en base de datos")
        
        # El lock se libera aquí automáticamente
        
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
        
        logger.info(f"[UPDATE] Iniciando actualización de flujo para IP: {ip}")
        
        # Adquirir lock antes de cualquier operación
        with acquire_flows_lock(timeout=30):
            logger.info(f"[UPDATE] Lock adquirido para IP: {ip}")
            
            # Actualizar flujo con flows.py
            route_json = json.dumps(route)
            success, stdout, stderr = run_flows_command([ip, '--update', '--route', route_json])
            
            if not success:
                logger.error(f"[UPDATE] Error en flows.py: {stderr}")
                if "no encontrado" in stderr:
                    return jsonify({"error": f"El flujo {ip} no existe"}), 404
                return jsonify({"error": f"Error actualizando flujo: {stderr}"}), 500
            
            logger.info(f"[UPDATE] Flujo {ip} actualizado exitosamente en base de datos")
        
        # El lock se libera aquí automáticamente
        
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
    """DELETE /flows/<ip> - Elimina un flujo y su ruta en RU"""
    try:
        # Decodificar la IP
        ip = decode_ip_from_url(encoded_ip)
        if not ip:
            return jsonify({"error": "IP inválida"}), 400
        
        logger.info(f"[DELETE] Iniciando eliminación de flujo: {ip}")

        # Adquirir lock antes de cualquier operación
        with acquire_flows_lock(timeout=30):
            logger.info(f"[DELETE] Lock adquirido para IP: {ip}")
            
            # Eliminar flujo con flows.py
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
                logger.info(f"[DELETE] Flujo {ip} eliminado exitosamente del registro")
        
        # El lock se libera aquí automáticamente
        
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
            "local_lock_locked": local_lock._count > 0 if hasattr(local_lock, '_count') else False,
            "distributed_lock_name": flows_lock.lock_name,
            "distributed_lock_key": flows_lock.lock_key
        }
        
        # Intentar obtener información del lock distribuido
        try:
            obj = s3_client.get_object(Bucket=S3_BUCKET, Key=flows_lock.lock_key)
            lock_data = json.loads(obj['Body'].read().decode())
            status["distributed_lock_exists"] = True
            status["distributed_lock_owner"] = lock_data.get('owner', 'unknown')
            status["distributed_lock_expires_at"] = lock_data.get('expires_at', 0)
            status["distributed_lock_expired"] = time.time() > lock_data.get('expires_at', 0)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                status["distributed_lock_exists"] = False
            else:
                status["distributed_lock_error"] = str(e)
        
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
    
    # Crear directorio de locks si no existe
    try:
        # Verificar/crear directorio de locks en S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key="locks/.gitkeep",
            Body=b"# Directorio para locks distribuidos"
        )
        logger.info("Directorio de locks inicializado")
    except Exception as e:
        logger.error(f"Error inicializando directorio de locks: {e}")
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

    logger.info("Iniciando Flask API con sistema de cerrojos distribuidos...")
    app.run(host='0.0.0.0', port=5000, debug=False)