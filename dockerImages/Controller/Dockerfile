FROM python:3.9-slim

WORKDIR /app

# Copiar el scripts
COPY tunnelmaker.py .
COPY mynetworkx.py .
COPY requirements.txt .

# Instalar pymongo
RUN pip install -r requirements.txt

