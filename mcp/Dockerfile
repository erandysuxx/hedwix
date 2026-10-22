# Imagen del MCP. Se construye con la raíz del repo como contexto (ver mcp/docker-compose.yml);
# el código se monta como volumen, así que aquí sólo van las dependencias.
FROM python:3.13-slim
COPY db/requirements.txt /tmp/req-db.txt
COPY mcp/requirements.txt /tmp/req-mcp.txt
RUN pip install --no-cache-dir -r /tmp/req-db.txt -r /tmp/req-mcp.txt
