# Imagen del notebook: Python + lo de la DB + lo del funnel (para reusar fuentes_curadas.id_de_url) + Jupyter.
# Se construye con la raíz del repo como contexto (ver servicio "notebook" en db/docker-compose.yml).
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt /tmp/req-funnel.txt
COPY db/requirements.txt /tmp/req-db.txt
COPY db/testing/requirements.txt /tmp/req-testing.txt
RUN pip install --no-cache-dir -r /tmp/req-funnel.txt -r /tmp/req-db.txt -r /tmp/req-testing.txt
