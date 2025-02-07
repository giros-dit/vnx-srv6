FROM python:3.9-slim

WORKDIR /app

# Copiar el script al contenedor
COPY store_routes.py .

# Instalar pymongo
RUN pip install pymongo

# Permitir interacción por stdin
CMD ["python", "store_routes.py"]
