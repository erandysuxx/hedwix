# Imagen del notebook: Python + lo de la DB + lo del funnel (fuentes_curadas.id_de_url) + lo del dispatch + Jupyter.
# Se construye con la raíz del repo como contexto (ver servicio "notebook" en db/docker-compose.yml).
FROM python:3.13-slim
WORKDIR /app
COPY funnel/requirements.txt /tmp/req-funnel.txt
COPY dispatch/requirements.txt /tmp/req-dispatch.txt
COPY db/requirements.txt /tmp/req-db.txt
COPY db/testing/requirements.txt /tmp/req-testing.txt
RUN pip install --no-cache-dir -r /tmp/req-funnel.txt -r /tmp/req-dispatch.txt -r /tmp/req-db.txt -r /tmp/req-testing.txt
