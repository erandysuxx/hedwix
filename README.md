# Hedwix: Curated Sources, Information Funnel y Dispatch

Piezas 2, 3 y 5 del bot de noticias de IA Hedwix. Trae noticias de 25 fuentes curadas (blogs de laboratorios, newsletters, arXiv, Hacker News, rankings de modelos), las normaliza a un solo formato, descarta las inválidas o repetidas y las guarda en la DB (MongoDB, carpeta `db/`). Después el Dispatch escoge las 5 más importantes del día con Claude y escribe el digest para WhatsApp.

| Archivo | Qué hace |
|---|---|
| `fuentes_curadas.py` | Trae y normaliza las noticias de cada fuente, con el texto completo de cada nota. |
| `funnel.py` | Valida las noticias, quita las que ya se guardaron y agrega las nuevas a `datos/noticias.jsonl`. |
| `dispatch.py` | Escoge las noticias más importantes, escribe el digest y lo guarda en la colección `digests` (o en `datos/digests/AAAA-MM-DD.json` sin `MONGODB_URI`). Por ahora lo imprime en vez de mandarlo. |
| `ESQUEMA.md` | Formato de cada noticia y tabla sugerida para la DB. |
| `ejemplos/noticias_ejemplo.jsonl` | Noticias reales de ejemplo, 2 por fuente. |
| `db/` | La DB (pieza 4): MongoDB en Docker, migraciones, carga y respaldos. Ver [`db/GUIA.md`](db/GUIA.md) y [`db/COMO_FUNCIONA.md`](db/COMO_FUNCIONA.md). |

## Uso

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt   # una sola vez
.venv/bin/python funnel.py                         # últimas 24 h -> datos/noticias.jsonl
.venv/bin/python fuentes_curadas.py --solo "Hacker News" --horas 48   # probar una fuente, imprime JSON
ANTHROPIC_API_KEY=... .venv/bin/python dispatch.py   # digest de las últimas 24 h, imprime el mensaje
```
