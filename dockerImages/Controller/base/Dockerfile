FROM python:3.9-slim

WORKDIR /app

# Copiar el scripts

COPY requirements.txt .

# Instalar pymongo
RUN apt-get update && \
    apt-get install -y openssh-server iputils-ping && \
    pip install -r requirements.txt 

