import subprocess

def run_command(command):
    """Ejecuta un comando en el shell y espera a que finalice antes de continuar."""
    try:
        print(f"Ejecutando: {command}")
        result = subprocess.run(command, shell=True, check=True, text=True)
        print(f"Comando completado: {command}")
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar el comando: {e}")
        exit(1)


def main():
    # Paso 1: Aplicar el archivo de topología
    run_command("kubectl apply -f ./converted")

    # Paso 2: Aplicar parche
    run_command("converted/deployment-patcher.sh")
    
    # Confirmación final
    print("El despliegue del escenario de la topología ha sido completado exitosamente.")

    directories = ['./conf/rgnb', './conf/rupf']
    for directory in directories:
        script_path = os.path.join(directory, 'script.sh')
        if os.path.exists(script_path):
            with open(script_path, 'w') as script_file:
                script_file.write('')

if __name__ == "__main__":
    main()
