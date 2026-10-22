// Se ejecuta una sola vez, cuando el volumen de datos está vacío.
// Crea los usuarios de la aplicación, con permisos sólo sobre la base "hedwix":
// - hedwix_app: readWrite para los datos y dbAdmin para que migrar.py pueda cambiar validadores e índices.
// - hedwix_mcp: para el MCP (que queda expuesto a internet por Cloudflare Tunnel). Rol lectura_mcp: sólo puede leer
//   noticias y digests, no usuarios ni envios (teléfonos). El mismo rol está en scripts/crear_usuario_mcp.sh.
const hedwix = db.getSiblingDB("hedwix");
hedwix.createUser({
  user: "hedwix_app",
  pwd: process.env.HEDWIX_APP_PASSWORD,
  roles: [
    { role: "readWrite", db: "hedwix" },
    { role: "dbAdmin", db: "hedwix" },
  ],
});
hedwix.createRole({
  role: "lectura_mcp",
  privileges: [
    { resource: { db: "hedwix", collection: "noticias" }, actions: ["find"] },
    { resource: { db: "hedwix", collection: "digests" }, actions: ["find"] },
  ],
  roles: [],
});
hedwix.createUser({
  user: "hedwix_mcp",
  pwd: process.env.HEDWIX_MCP_PASSWORD,
  roles: [{ role: "lectura_mcp", db: "hedwix" }],
});
