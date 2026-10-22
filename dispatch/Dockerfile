# Imagen del dispatch. Se construye con la raíz del repo como contexto; el código se monta como volumen.
FROM python:3.13-slim
COPY funnel/requirements.txt /tmp/req-funnel.txt
COPY dispatch/requirements.txt /tmp/req-dispatch.txt
RUN pip install --no-cache-dir -r /tmp/req-funnel.txt -r /tmp/req-dispatch.txt
