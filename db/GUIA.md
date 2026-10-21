# Hedwix DB (pieza 4): MongoDB local con Docker

```
Email + Curated Sources ─► Information Funnel ─► [ DB: MongoDB ] ─► MCP ─► Cloudflare ─► Agent
                                                        └──────► Agent-Dispatch ─► Twilio ─► WhatsApp ─► usuarios
```

El funnel vive en la raíz de este repo. La carpeta `db/` es la DB: esquema, migraciones, carga y consultas.
Todos los comandos de esta guía se corren desde `db/`, salvo que se indique otra cosa.

```
db/
├── docker-compose.yml        # mongo:7.0 (con auth) + contenedor app (Python 3.13)
├── Dockerfile, requirements.txt
├── .env / .env.example       # credenciales (.env no se sube a git)
├── mongo-init/               # crea el usuario hedwix_app la primera vez
├── hedwix_db/                # código de acceso a datos (lo reutilizan MCP / dispatch)
│   ├── conexion.py           #   obtener_db()
│   └── noticias.py           #   insertar_noticias, recientes, mas_populares, buscar, a_item
├── migraciones/              # 001_noticias.py, 002_usuarios_envios.py, ...
├── migrar.py                 # aplica migraciones pendientes
├── cargar_jsonl.py           # carga un JSONL del funnel
├── consultas.py              # ejemplos de consultas
├── scripts/respaldar.sh, restaurar.sh
└── backups/                  # respaldos (no se suben a git)
```

---

## 1. Primera vez

```bash
cp .env.example .env
# Cambia las 3 contraseñas (openssl rand -hex 16). HEDWIX_APP_PASSWORD también va dentro de MONGODB_URI.
docker compose up -d --build
docker compose ps                         # mongo-dev debe estar "Up (healthy)"
docker compose exec app python migrar.py  # crea colecciones, validadores e índices
```

Usuarios de Mongo:

| Usuario | Base de autenticación | Permisos | Para qué |
|---|---|---|---|
| `root` | `admin` | todo | respaldos, administración |
| `hedwix_app` | `hedwix` | `readWrite` + `dbAdmin` sólo sobre `hedwix` | app, funnel, migraciones |

> Las credenciales de `.env` **sólo se aplican cuando el volumen está vacío**. Si las cambias después,
> tienes que hacer respaldo → `docker compose down -v` → `up` → `migrar.py` → restaurar.

## 2. Meter noticias

**Opción A: el funnel escribe directo** (`funnel.py`, en la raíz del repo).
El host no tiene `python3-venv`, así que se corre en un contenedor conectado a la red del compose:

```bash
cd ..                                    # raíz del repo
set -a; source db/.env; set +a
docker run --rm --network hedwix_default -e MONGODB_URI -v "$PWD":/funnel:ro -w /funnel \
  python:3.13-slim sh -c 'pip install -q -r requirements.txt && python funnel.py --horas 24'
```

Tarda unos 3 minutos. Si en vez de eso usas una `.venv` en el host, la URI va con `127.0.0.1` en lugar de `mongo`.

**Opción B: cargar un JSONL** que ya generó el funnel:

```bash
docker compose exec app python cargar_jsonl.py /repo/ejemplos/noticias_ejemplo.jsonl
docker compose exec app python cargar_jsonl.py /repo/datos/noticias.jsonl
```

En los dos casos las repetidas se ignoran, porque `_id` es el sha1 de la URL.

## 3. Consultar

```bash
docker compose exec app python consultas.py --buscar "agent"
docker compose exec mongo mongosh "$(grep ^MONGODB_URI .env | cut -d= -f2-)"   # shell como hedwix_app
```

Desde el host (Compass, etc.): `mongodb://hedwix_app:<clave>@127.0.0.1:27017/hedwix?authSource=hedwix`

---

## 4. Modelo de datos (base `hedwix`)

### `noticias`
Los mismos 12 campos de `ESQUEMA.md` (raíz del repo), con estos cambios:
- `id` → **`_id`**
- `published` / `fetched_at` → **`Date`**

| Índice | Campos | Lo usa |
|---|---|---|
| `recientes` | `published -1` | últimas noticias (MCP, agent) |
| `por_fuente` | `source, published -1` | filtrar por fuente |
| `populares` | `score -1`, sólo donde `score` es número | top de Hacker News y HF |
| `busqueda` | texto: `title`×10, `summary`×5, `content` | búsqueda libre |

El validador `$jsonSchema` rechaza lo que no cumpla el esquema, por ejemplo `origin` distinto de `curated`/`email`, una URL inválida o fechas en texto.

### `usuarios` (dispatch, por ahora vacía)
`telefono` (E.164 `+52…`, único), `nombre`, `activo`, `preferencias {fuentes, temas, hora_envio "08:00", zona_horaria}`, `creado`, `actualizado`.

### `envios` (dispatch, por ahora vacía)
`usuario_id`, `noticia_ids[]`, `canal: whatsapp`, `twilio_sid` (único cuando existe), `estado` (`pendiente|enviado|entregado|leido|fallido`), `error`, `creado`, `actualizado`.
- El índice `ya_enviadas` (`usuario_id, noticia_ids`) sirve para no reenviarle a nadie la misma noticia.

## 5. Migraciones (cambios de esquema)

1. Crea `migraciones/003_lo_que_cambia.py` con `DESCRIPCION` y `aplicar(db)`. Para crear una colección o cambiar su validador usa `asegurar_coleccion()`.
2. Corre `docker compose exec app python migrar.py`.

Las migraciones aplicadas se anotan en la colección `_migraciones` y no se repiten. **No edites una migración ya aplicada**: crea una nueva.

## 6. Respaldos y mover la DB a otro servidor

```bash
scripts/respaldar.sh                                     # -> backups/hedwix_AAAA-MM-DD_HHMM.archive.gz
scripts/restaurar.sh backups/hedwix_AAAA-MM-DD_HHMM.archive.gz
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
