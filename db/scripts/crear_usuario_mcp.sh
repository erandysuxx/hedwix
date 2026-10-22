#!/usr/bin/env bash
# Crea (o actualiza la contraseña de) el usuario de sólo lectura hedwix_mcp en una DB que ya existía.
# En un volumen nuevo no hace falta: lo crea mongo-init/01-usuario-app.js.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; source "$RAIZ/.env"; set +a
: "${HEDWIX_MCP_PASSWORD:?Falta HEDWIX_MCP_PASSWORD en .env de la raíz (ver .env.example)}"

docker compose --project-directory "$RAIZ" exec -T -e HEDWIX_MCP_PASSWORD mongo mongosh --quiet \
  --username "$MONGO_ROOT_USER" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin --eval '
    const hedwix = db.getSiblingDB("hedwix");
    const datos = { pwd: process.env.HEDWIX_MCP_PASSWORD, roles: [{ role: "read", db: "hedwix" }] };
    if (hedwix.getUser("hedwix_mcp")) { hedwix.updateUser("hedwix_mcp", datos); print("hedwix_mcp actualizado"); }
    else { hedwix.createUser({ user: "hedwix_mcp", ...datos }); print("hedwix_mcp creado"); }'
