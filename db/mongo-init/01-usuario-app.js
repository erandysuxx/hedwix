// Se ejecuta una sola vez, cuando el volumen de datos está vacío.
// Crea los usuarios de la aplicación, con permisos sólo sobre la base "hedwix":
// - hedwix_app: readWrite para los datos y dbAdmin para que migrar.py pueda cambiar validadores e índices.
// - hedwix_mcp: sólo lectura, para el MCP (que queda expuesto a internet por Cloudflare Tunnel).
const hedwix = db.getSiblingDB("hedwix");
hedwix.createUser({
  user: "hedwix_app",
  pwd: process.env.HEDWIX_APP_PASSWORD,
  roles: [
    { role: "readWrite", db: "hedwix" },
    { role: "dbAdmin", db: "hedwix" },
  ],
});
hedwix.createUser({
  user: "hedwix_mcp",
  pwd: process.env.HEDWIX_MCP_PASSWORD,
  roles: [{ role: "read", db: "hedwix" }],
});
