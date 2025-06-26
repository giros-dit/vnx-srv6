#!/usr/bin/env python3
import json
import subprocess
import os
import urllib.parse
from flask import Flask, request, jsonify
import logging

app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

S3_ENDPOINT = os.environ.get('S3_ENDPOINT')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

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

def run_src_command(dest_prefix, path_json, replace=False, high_occupancy=False):
    """Ejecuta el comando src.py para crear/actualizar rutas"""
    try:
        cmd = ['python3', '/app/src.py', dest_prefix, path_json]
        if replace:
            cmd.append('--replace')
        if high_occupancy:
            cmd.append('--high-occupancy')
            
        logger.info(f"Ejecutando: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd='/app'
        )
        
        logger.info(f"src.py return code: {result.returncode}")
        logger.info(f"src.py stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"src.py stderr: {result.stderr}")
            
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        logger.error(f"Error ejecutando src.py: {e}")
        return False, "", str(e)

def get_flows_data():
    """Obtiene los datos actuales de flows"""
    try:
        success, stdout, stderr = run_flows_command(['--list'])
        if success:
            # Parsear la salida JSON
            for line in stdout.split('\n'):
                if line.strip().startswith('{'):
                    return json.loads(line.strip())
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
        data = get_flows_data()
        return jsonify(data), 200
    except Exception as e:
        logger.error(f"Error en GET /flows: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

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
        
        if not success:
            if "ya existe" in stderr:
                return jsonify({"error": f"El flujo {ip} ya existe"}), 409
            return jsonify({"error": f"Error creando flujo: {stderr}"}), 500
        
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
    """DELETE /flows/<ip> - Elimina un flujo"""
    try:
        # Decodificar la IP
        ip = decode_ip_from_url(encoded_ip)
        if not ip:
            return jsonify({"error": "IP inválida"}), 400
        
        logger.info(f"Eliminando flujo para IP: {ip}")
        
        # Eliminar flujo con flows.py
        success, stdout, stderr = run_flows_command([ip, '--delete'])
        
        if not success:
            if "no encontrado" in stderr:
                return jsonify({"error": f"El flujo {ip} no existe"}), 404
            return jsonify({"error": f"Error eliminando flujo: {stderr}"}), 500
        
        return jsonify({"message": f"Flujo {ip} eliminado exitosamente"}), 200
        
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
    
    logger.info("Iniciando Flask API para gestión de flujos...")
    app.run(host='0.0.0.0', port=5000, debug=False)