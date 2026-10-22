# Hedwix

Bot de noticias de inteligencia artificial: junta noticias de muchas fuentes, las guarda en una base de datos, deja que un agente las consulte y manda un digest diario por WhatsApp.

```
Email ┐
      ├─► funnel/ ─► db/ (MongoDB) ─┬─► mcp/ ─► Cloudflare Tunnel ─► Agent
Curated Sources ┘                   └─► dispatch/ ─► Twilio ─► WhatsApp ─► usuarios
```

Diagrama interactivo: [`db/docs/flujo-hedwix.html`](db/docs/flujo-hedwix.html), que se abre en el navegador. Estado detallado: [`db/COMO_FUNCIONA.md`](db/COMO_FUNCIONA.md).

## Piezas

Cada pieza vive en su propia carpeta, con su README, sus dependencias y su `docker-compose.yml`.

| Carpeta | Pieza | Estado | Se conecta con |
|---|---|---|---|
| [`funnel/`](funnel/) | Curated Sources + Information Funnel (2 y 3) | ✅ | escribe en `db/` (`noticias`) |
| [`db/`](db/) | DB: MongoDB, migraciones, respaldos y notebooks de revisión (4) | ✅ | la usan todas; `db/hedwix_db/` es el código compartido |
| [`mcp/`](mcp/) | MCP: tools de sólo lectura para el agente | ✅ local | lee `db/` con el usuario `hedwix_mcp` |
| `dispatch/` | Agent-Dispatch: digest diario con Claude (5) | 🔄 PR #2 | lee `noticias` y escribe `digests` |
| — | Email, Cloudflare Tunnel, Agent, Twilio → WhatsApp | ⏸ | — |

## Cómo se conectan

- **Un solo `docker-compose.yml` en la raíz.** Incluye el de cada pieza (`include:`). Todas comparten la red `hedwix_default`, el volumen de Mongo y el `.env` de la raíz. **Todos los comandos de `docker compose` se corren desde aquí.**
- **Un solo `.env` en la raíz**, a partir de `.env.example`. Ahí están las credenciales de Mongo y la URI de cada pieza:

  | Variable | Pieza | Usuario de Mongo |
  |---|---|---|
  | `MONGODB_URI` | funnel, dispatch | `hedwix_app` (escribe) |
  | `MCP_MONGODB_URI` | MCP | `hedwix_mcp` (sólo lectura) |

- **Código compartido:** el acceso a datos está en `db/hedwix_db/`. Otra pieza lo usa agregando `../db` a su `sys.path`, como hace `mcp/servidor.py`.
- **Formato de las noticias:** lo define [`funnel/ESQUEMA.md`](funnel/ESQUEMA.md). La DB lo hace cumplir con validadores (`db/migraciones/`).

## Arranque rápido

```bash
cp .env.example .env                       # y cambiar las contraseñas (openssl rand -hex 16)
docker compose up -d --build               # mongo, app (herramientas de la DB) y mcp
docker compose exec app python migrar.py   # colecciones, validadores e índices
docker compose run --rm funnel             # traer las noticias de las últimas 24 h
curl http://127.0.0.1:8000/health          # el MCP, en http://127.0.0.1:8000/mcp
```

## Convención para piezas nuevas

1. **Carpeta propia** en la raíz (`dispatch/`, `twilio/`…), con:
   - `README.md`
   - `requirements.txt`
   - `Dockerfile` y `docker-compose.yml`, si corre en Docker. El `build.context` es `..` (la raíz) y el código se monta en `/repo`.
2. **Agrégala al `include:`** del `docker-compose.yml` de la raíz, con `env_file: .env`.
3. **Variables nuevas** en `.env.example` de la raíz. Si la pieza toca Mongo, usa un usuario con los permisos justos (ver `db/mongo-init/`).
4. **Cambios de esquema** en `db/migraciones/` con el siguiente número libre. **Avisa al equipo** qué número tomas: la `003` es de dispatch.
5. **No nombres una carpeta igual que un paquete de Python** que use la pieza (por ejemplo, `mcp/` no lleva `__init__.py`, para no tapar el paquete `mcp`).
6. **Agrégala a la tabla de piezas** de este README y al diagrama.

### Para `feat/dispatch` (PR #2)

Erandy, cuando este cambio entre a `main`:
- **Archivos:** mueve `dispatch.py` y `probar_con_claude_code.py` a `dispatch/`.
- **Imports:** donde dice `import funnel`, agrega antes `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "funnel"))`.
- **Migración:** `003_digests.py` se queda en `db/migraciones/`.
- **Dependencias:** `anthropic` va en `dispatch/requirements.txt`.
