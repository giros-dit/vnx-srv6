FROM python:3.9-slim

WORKDIR /app

# Copiar el script al contenedor
COPY store_routes.py .
COPY mynetworkx.py .
COPY requirements.txt .

# Instalar dependencias
RUN pip install -r requirements.txt

