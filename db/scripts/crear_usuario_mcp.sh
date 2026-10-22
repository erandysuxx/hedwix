#!/usr/bin/env bash
# Crea (o actualiza) el usuario hedwix_mcp y su rol lectura_mcp en una DB que ya existía. El rol sólo puede leer
# noticias y digests, no usuarios ni envios. En un volumen nuevo no hace falta: lo crea mongo-init/01-usuario-app.js.
# Si hedwix_mcp ya existía con el rol "read" de antes, también se lo cambia por lectura_mcp.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; source "$RAIZ/.env"; set +a
: "${HEDWIX_MCP_PASSWORD:?Falta HEDWIX_MCP_PASSWORD en .env de la raíz (ver .env.example)}"

docker compose --project-directory "$RAIZ" exec -T -e HEDWIX_MCP_PASSWORD mongo mongosh --quiet \
  --username "$MONGO_ROOT_USER" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin --eval '
    const hedwix = db.getSiblingDB("hedwix");
    const privilegios = [
      { resource: { db: "hedwix", collection: "noticias" }, actions: ["find"] },
      { resource: { db: "hedwix", collection: "digests" }, actions: ["find"] },
    ];
    if (hedwix.getRole("lectura_mcp")) { hedwix.updateRole("lectura_mcp", { privileges: privilegios, roles: [] }); }
    else { hedwix.createRole({ role: "lectura_mcp", privileges: privilegios, roles: [] }); }
    const datos = { pwd: process.env.HEDWIX_MCP_PASSWORD, roles: [{ role: "lectura_mcp", db: "hedwix" }] };
    if (hedwix.getUser("hedwix_mcp")) { hedwix.updateUser("hedwix_mcp", datos); print("hedwix_mcp actualizado"); }
    else { hedwix.createUser({ user: "hedwix_mcp", ...datos }); print("hedwix_mcp creado"); }'
