# Imagen del servicio de scoring de Caja Rural 360.
# Solo lleva lo que la API necesita: el scorecard es un JSON y no requiere LightGBM, SHAP ni matplotlib.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Dependencias primero: aprovecha la caché de capas cuando solo cambia el código
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Código y artefactos versionados (el registry valida su hash al arrancar)
COPY src/ ./src/
COPY api/ ./api/
COPY models/ ./models/
COPY reports/tables/api_ejemplos.json ./reports/tables/api_ejemplos.json

# Usuario sin privilegios: el servicio solo lee artefactos, nunca los escribe
RUN useradd --create-home --shell /bin/bash scoring && chown -R scoring:scoring /app
USER scoring

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
