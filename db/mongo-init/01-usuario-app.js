// Se ejecuta una sola vez, cuando el volumen de datos está vacío.
// Crea el usuario de la aplicación con permisos sólo sobre la base "hedwix":
// readWrite para los datos y dbAdmin para que migrar.py pueda cambiar validadores e índices.
db.getSiblingDB("hedwix").createUser({
  user: "hedwix_app",
  pwd: process.env.HEDWIX_APP_PASSWORD,
  roles: [
    { role: "readWrite", db: "hedwix" },
    { role: "dbAdmin", db: "hedwix" },
  ],
});
