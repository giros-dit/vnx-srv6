FROM python:3.11-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    openssh-client \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar archivos de la aplicación
COPY flask/app.py .
COPY flows.py .
COPY src.py .

# Hacer los scripts ejecutables
RUN chmod +x flows.py src.py app.py

# Crear directorio para claves SSH
RUN mkdir -p /root/.ssh && \
    chmod 700 /root/.ssh

# Exponer puerto
EXPOSE 5000

# Comando por defecto
CMD ["python3", "app.py"]