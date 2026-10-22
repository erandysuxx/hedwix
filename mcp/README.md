# MCP de Hedwix

Servidor [MCP](https://modelcontextprotocol.io) hecho con **FastMCP 4.1.3**. Deja que un agente consulte las noticias de IA de la DB.

- **Sólo lectura:** usa el usuario de Mongo `hedwix_mcp`, que tiene rol `read` sobre la base `hedwix`.
- **Reutiliza las consultas** de `db/hedwix_db`.

```
Funnel ─► MongoDB ─► MCP (este) ─► [Cloudflare Tunnel, fase 2] ─► Agent
```

## Tools

| Tool | Para qué |
|---|---|
| `noticias_recientes(horas=24, fuentes=None, limite=20, incluir_arxiv=False, incluir_rankings=False)` | Lo último que se publicó. Por default deja fuera arXiv (~80% del volumen) y los rankings de modelos, que se guardan con la hora de la consulta y siempre saldrían primero. |
| `buscar_noticias(texto, limite=10, fuentes=None, horas=None)` | Búsqueda por texto con el índice de Mongo. Las notas están en inglés: "agents" encuentra más que "agentes". |
| `noticias_populares(horas=72, limite=10)` | Las de más votos o puntos (Hacker News y HF Daily Papers). |
| `obtener_noticia(id)` | Una noticia con su texto completo, cortado a 20,000 caracteres (`content_cortado`). |
| `listar_fuentes()` | Fuentes, cuántas noticias tiene cada una y la más reciente. |
| `digest_del_dia(fecha=None)` | El digest del Dispatch (colección `digests`). Si no hay, regresa `encontrado: false`. |

**Cómo responden:**
- **Listas:** no traen el `content`, sólo `summary` y `largo_content`, para no llenar el contexto del agente. El texto completo se pide con `obtener_noticia`.
- **Límites:** `limite` va de 1 a 50 y `horas` de 1 a 720. Fuera de rango, la tool responde con un error de validación.
- **Anotaciones:** todas las tools se marcan como `readOnlyHint`.

## Levantarlo (local, en Docker)

Desde la **raíz del repo**, con Mongo arriba:

```bash
# Una sola vez en una DB que ya existía: crea el usuario de sólo lectura con HEDWIX_MCP_PASSWORD del .env de la raíz
db/scripts/crear_usuario_mcp.sh

docker compose up -d --build mcp
curl http://127.0.0.1:8000/health          # {"status":"ok","db":"hedwix"}
```

El MCP queda en **`http://127.0.0.1:8000/mcp`** (streamable HTTP), sólo accesible desde esta máquina.

- **Código montado:** el contenedor monta el repo, así que si cambias `servidor.py` basta con `docker compose restart mcp`.
- **Dependencias:** si cambias `requirements.txt`, usa `--build`.

## Probarlo

```bash
# Tests (cliente en memoria de FastMCP contra la DB local), desde la raíz
docker compose run --rm --no-deps mcp pytest -v

# Con Claude Code como agente, desde la raíz del repo (sólo para ti, en este proyecto)
claude mcp add --transport http --scope local hedwix http://127.0.0.1:8000/mcp
claude mcp list                              # hedwix: ... ✔ Connected
```

Luego, en Claude Code: *"Usando el MCP hedwix, ¿qué noticias de IA llegaron hoy sobre agentes?"*

Desde la terminal también sirve el CLI de FastMCP:
- `fastmcp list http://127.0.0.1:8000/mcp`
- `fastmcp call http://127.0.0.1:8000/mcp buscar_noticias texto=agents limite=3`

## Fase 2: exponerlo con Cloudflare Tunnel (pendiente)

La idea es un servicio `cloudflared` en `mcp/docker-compose.yml`, con perfil `publico`, que lleve una URL HTTPS de Cloudflare a `http://mcp:8000`. Mongo nunca se expone.

**Antes de activarlo hace falta autenticación**, porque hoy el MCP no pide token: sólo es seguro mientras escucha en `127.0.0.1`. Hay dos opciones:
- `JWTVerifier` de FastMCP, pasado en `FastMCP(..., auth=...)`;
- Cloudflare Access con service tokens.

Se decide cuando se defina qué Agent lo va a usar.
