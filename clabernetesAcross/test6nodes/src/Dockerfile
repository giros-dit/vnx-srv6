FROM python:3.9-slim

WORKDIR /app

# Copiar el script de generación de túneles
COPY tunnelmaker.py .

# Instalar pymongo
RUN pip install pymongo

#CMD ["python", "tunnelmaker.py"]