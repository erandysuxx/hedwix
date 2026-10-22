# Hedwix DB (pieza 4): MongoDB local con Docker

```
Email + Curated Sources ─► Information Funnel ─► [ DB: MongoDB ] ─► MCP ─► Cloudflare ─► Agent
                                                        └──────► Agent-Dispatch ─► Twilio ─► WhatsApp ─► usuarios
```

Cada pieza de Hedwix tiene su carpeta (`funnel/`, `db/`, `mcp/`…); ver el [README de la raíz](../README.md).
`db/` es la DB: esquema, migraciones, carga, consultas y respaldos.
**Todos los comandos de esta guía se corren desde la raíz del repo.** Ahí está el `docker-compose.yml` que une todas las piezas, y también el `.env`.

```
db/
├── docker-compose.yml        # mongo:7.0 (con auth) + app (Python 3.13) + notebook; lo incluye el de la raíz
├── Dockerfile, requirements.txt
├── mongo-init/               # crea los usuarios hedwix_app y hedwix_mcp la primera vez
├── hedwix_db/                # código de acceso a datos (lo reutilizan funnel, MCP y dispatch)
│   ├── conexion.py           #   obtener_db()
│   ├── noticias.py           #   insertar_noticias, recientes, mas_populares, buscar, por_fuente, a_item
│   └── digests.py            #   digest()
├── migraciones/              # 001_noticias.py, 002_usuarios_envios.py, 003_digests.py, ...
├── migrar.py                 # aplica migraciones pendientes
├── cargar_jsonl.py           # carga un JSONL del funnel
├── consultas.py              # ejemplos de consultas
├── testing/                 # notebook para revisar los datos (servicio "notebook")
├── scripts/respaldar.sh, restaurar.sh, crear_usuario_mcp.sh
└── backups/                  # respaldos (no se suben a git)
```

---

## 1. Primera vez

```bash
cp .env.example .env                      # en la raíz del repo
# Cambia las 4 contraseñas (openssl rand -hex 16). HEDWIX_APP_PASSWORD va también dentro de MONGODB_URI, y HEDWIX_MCP_PASSWORD dentro de MCP_MONGODB_URI.
docker compose up -d --build
docker compose ps                         # mongo-dev debe estar "Up (healthy)"
docker compose exec app python migrar.py  # crea colecciones, validadores e índices
```

Usuarios de Mongo:

| Usuario | Base de autenticación | Permisos | Para qué |
|---|---|---|---|
| `root` | `admin` | todo | respaldos, administración |
| `hedwix_app` | `hedwix` | `readWrite` + `dbAdmin` sólo sobre `hedwix` | app, funnel, migraciones |
| `hedwix_mcp` | `hedwix` | `read` sólo sobre `hedwix` | el MCP (`mcp/`); en una DB existente se crea con `db/scripts/crear_usuario_mcp.sh` |

> Las credenciales de `.env` **sólo se aplican cuando el volumen está vacío**. Si las cambias después,
> tienes que hacer respaldo → `docker compose down -v` → `up` → `migrar.py` → restaurar.

## 2. Meter noticias

**Opción A: el funnel escribe directo** (`funnel/`). Tiene su propio servicio en el compose, que no se queda corriendo:

```bash
docker compose run --rm funnel                              # últimas 24 h
docker compose run --rm funnel python funnel.py --horas 48
```

Tarda unos 3 minutos. Si en vez de eso usas una `.venv` en el host, la URI va con `127.0.0.1` en lugar de `mongo`.

**Opción B: cargar un JSONL** que ya generó el funnel:

```bash
docker compose exec app python cargar_jsonl.py /repo/funnel/ejemplos/noticias_ejemplo.jsonl
docker compose exec app python cargar_jsonl.py /repo/funnel/datos/noticias.jsonl
```

En los dos casos las repetidas se ignoran, porque `_id` es el sha1 de la URL.

## 3. Consultar

```bash
docker compose exec app python consultas.py --buscar "agent"
docker compose exec mongo mongosh "$(grep ^MONGODB_URI .env | cut -d= -f2-)"   # shell como hedwix_app
```

**Revisar que los datos estén bien:** el notebook `testing/revisar_datos.ipynb` hace conteos, gráficas y 15 chequeos de calidad. Se puede abrir en Jupyter o correr desde la terminal; ver [`testing/README.md`](testing/README.md).

Desde el host (Compass, etc.): `mongodb://hedwix_app:<clave>@127.0.0.1:27017/hedwix?authSource=hedwix`

---

**MCP:** `docker compose up -d mcp` lo levanta en `http://127.0.0.1:8000/mcp`. Ver [`../mcp/README.md`](../mcp/README.md).

## 4. Modelo de datos (base `hedwix`)

### `noticias`
Los mismos 12 campos de [`funnel/ESQUEMA.md`](../funnel/ESQUEMA.md), con estos cambios:
- `id` → **`_id`**
- `published` / `fetched_at` → **`Date`**

| Índice | Campos | Lo usa |
|---|---|---|
| `recientes` | `published -1` | últimas noticias (MCP, agent) |
| `por_fuente` | `source, published -1` | filtrar por fuente |
| `populares` | `score -1`, sólo donde `score` es número | top de Hacker News y HF |
| `busqueda` | texto: `title`×10, `summary`×5, `content` | búsqueda libre |
| `por_llegada` | `fetched_at -1` | lo que llegó en las últimas horas (dispatch) |

El validador `$jsonSchema` rechaza lo que no cumpla el esquema, por ejemplo `origin` distinto de `curated`/`email`, una URL inválida o fechas en texto.

### `usuarios` (dispatch, por ahora vacía)
`telefono` (E.164 `+52…`, único), `nombre`, `activo`, `preferencias {fuentes, temas, hora_envio "08:00", zona_horaria}`, `creado`, `actualizado`.

### `envios` (dispatch, por ahora vacía)
`usuario_id`, `noticia_ids[]`, `canal: whatsapp`, `twilio_sid` (único cuando existe), `estado` (`pendiente|enviado|entregado|leido|fallido`), `error`, `creado`, `actualizado`.
- El índice `ya_enviadas` (`usuario_id, noticia_ids`) sirve para no reenviarle a nadie la misma noticia.

### `digests` (dispatch)
`_id` (la fecha del digest en México, `AAAA-MM-DD`), `generado_at`, `modelo`, `mensaje` (máximo 1,600 caracteres, el límite de Twilio), `noticias[] {id, source, title, url, por_que}`.
- Si el dispatch corre dos veces el mismo día, el segundo digest reemplaza al primero.

## 5. Migraciones (cambios de esquema)

1. Crea `db/migraciones/004_lo_que_cambia.py` (la 003 es `003_digests`, del dispatch; avisa al equipo qué número tomas) con `DESCRIPCION` y `aplicar(db)`. Para crear una colección o cambiar su validador usa `asegurar_coleccion()`.
2. Corre `docker compose exec app python migrar.py`.

Las migraciones aplicadas se anotan en la colección `_migraciones` y no se repiten. **No edites una migración ya aplicada**: crea una nueva.

## 6. Respaldos y mover la DB a otro servidor

```bash
db/scripts/respaldar.sh                                        # -> db/backups/hedwix_AAAA-MM-DD_HHMM.archive.gz
db/scripts/restaurar.sh db/backups/hedwix_AAAA-MM-DD_HHMM.archive.gz
```

**Para mover la DB a otra máquina:**
1. Copia este proyecto y el respaldo.
2. Crea su `.env` y corre `docker compose up -d`.
3. Corre `migrar.py`.
4. Corre `restaurar.sh`.

Para usar Atlas o un VPS, basta con cambiar `MONGODB_URI` y restaurar ahí con `mongorestore --uri`.

> Con todo el arXiv son ~800 noticias y ~0.7 MB comprimidos por día. Guarda los respaldos importantes fuera de esta máquina.

| Acción | Comando |
|---|---|
| Logs de Mongo | `docker compose logs -f mongo` |
| Detener (conserva datos) | `docker compose down` |
| **Borrar todo, incluidos los datos** | `docker compose down -v` ⚠️ |

---

## 7. Solución de problemas

**`mongo-dev` en `Restarting (1)`: "Linux kernel versions 6.19 and newer has a known incompatibility".**
MongoDB 8.x no arranca en kernels ≥ 6.19 ([SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)). Por eso se usa `mongo:7.0`. Un volumen creado por 8.x no abre en 7.0: hay que restaurar desde un respaldo en un volumen nuevo.

**`Authentication failed`.**
- Revisa que la contraseña de `MONGODB_URI` sea la misma que `HEDWIX_APP_PASSWORD` y que la URI termine en `authSource=hedwix`.
- Si cambiaste `.env` después de crear el volumen, mira la nota de la sección 1.

**`not authorized ... collMod`.**
El usuario necesita `dbAdmin` sobre `hedwix`, que el script de inicio ya incluye. En un volumen viejo, dáselo con root: `db.getSiblingDB("hedwix").grantRolesToUser("hedwix_app",[{role:"dbAdmin",db:"hedwix"}])`.

**`Document failed validation`.**
El documento no cumple el esquema; `cargar_jsonl.py` muestra el campo y el motivo.

**`ServerSelectionTimeoutError`.**
- Dentro de un contenedor el host es `mongo`; desde la máquina es `127.0.0.1`.
- Para `docker run`, agrega `--network hedwix_default`.

**Permisos en archivos creados por `app`.**
El contenedor corre como `1000:1000`. Si tu UID es otro (`id -u`), ajusta `user:` en el compose.
