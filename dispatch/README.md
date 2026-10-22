# Dispatch: digest diario con Claude (pieza 5)

Escoge las noticias más importantes del día y escribe el mensaje de WhatsApp. Por ahora lo **imprime** en vez de mandarlo; el envío será la siguiente pieza (Twilio → WhatsApp).

```
db/ (noticias) ─► dispatch.py ─► Claude (escoger 5) ─► Claude (escribir) ─► db/ (digests) ─► enviar()
```

| Archivo | Qué hace |
|---|---|
| `dispatch.py` | La corrida completa (ver abajo). |
| `probar_con_claude_code.py` | Lo mismo con tu suscripción de Claude Code (`claude -p`) en vez de la API, sin arXiv y **sin guardar** el digest. Sirve mientras no haya llave de API. Cuenta contra el límite de tu plan. |
| `requirements.txt` | `anthropic`. Además necesita `../funnel/requirements.txt`, porque importa `funnel.py`. |
| `Dockerfile`, `docker-compose.yml` | El servicio `dispatch`; lo incluye el `docker-compose.yml` de la raíz. |

## Qué hace cada corrida

1. **Leer** las noticias que el funnel guardó en las últimas 24 h. Filtra por `fetched_at`, no por `published`: Anthropic, Meta y HF Daily Papers sólo dan el día de publicación. Con `MONGODB_URI` lee de la colección `noticias`; sin ella, de `../funnel/datos/noticias.jsonl`.
2. **Escoger:** Claude ve título, resumen y puntaje de todas y escoge las 5 más importantes, con un "por qué".
3. **Escribir:** Claude lee el texto completo de esas 5 y escribe el mensaje en español, con formato de WhatsApp y un máximo de 1,600 caracteres (el límite de Twilio). Si se pasa, le pide que lo acorte, hasta dos veces.
4. **Guardar** el digest con la fecha de México como `_id` en la colección `digests` (migración `db/migraciones/003_digests.py`). Si corre dos veces el mismo día, el segundo reemplaza al primero. Sin `MONGODB_URI` lo guarda en `datos/digests/AAAA-MM-DD.json`.
5. **Enviar:** por ahora `enviar()` sólo imprime el mensaje.

Usa `claude-opus-5-5` con esfuerzo medio y la llave del equipo en `ANTHROPIC_API_KEY`.

## Uso

**Con Docker, desde la raíz del repo** (lee y escribe en MongoDB). Necesita `ANTHROPIC_API_KEY` en el `.env` de la raíz y la migración 003 aplicada (`docker compose exec app python migrar.py`):

```bash
docker compose run --rm dispatch                              # digest de las últimas 24 h
docker compose run --rm dispatch python dispatch.py --horas 48
```

**Sin Docker, desde `dispatch/`:**

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r ../funnel/requirements.txt -r requirements.txt
ANTHROPIC_API_KEY=... MONGODB_URI="mongodb://hedwix_app:<clave>@127.0.0.1:27017/hedwix?authSource=hedwix" .venv/bin/python dispatch.py
.venv/bin/python probar_con_claude_code.py      # sin llave, con Claude Code (no corre en Docker: necesita el comando claude)
```

**Probarlo sin gastar tokens:** el notebook `db/testing/revisar_dispatch.ipynb` corre las funciones reales con Claude simulado y no escribe nada en la DB. Ver [`db/testing/README.md`](../db/testing/README.md).

## Pendiente

- **Correrlo una vez con la API real.** Nunca se ha corrido con `ANTHROPIC_API_KEY`; la llamada, los `fallbacks` y el formato de salida no se han probado.
- **arXiv:** hoy le manda a Claude todas las noticias del día, unos 110k tokens. `probar_con_claude_code.py` ya excluye arXiv (unos 18k tokens); hay que decidir si `dispatch.py` hace lo mismo.
- **Noticias sin texto:** algunas candidatas no tienen texto (HF trending, notas que el funnel no pudo descargar). Si Claude escoge una, escribe sólo con el título.
