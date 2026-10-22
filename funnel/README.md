# Funnel: Curated Sources + Information Funnel (piezas 2 y 3)

Trae noticias de IA de 25 fuentes curadas: blogs de laboratorios, newsletters, arXiv, Hacker News y rankings de modelos. Las normaliza a un solo formato, descarta las inválidas o repetidas y las guarda en la DB ([`../db/`](../db/)).

| Archivo | Qué hace |
|---|---|
| `fuentes_curadas.py` | Trae y normaliza las noticias de cada fuente, con el texto completo de cada nota. |
| `funnel.py` | Valida las noticias, quita las que ya se guardaron y guarda las nuevas: en MongoDB si hay `MONGODB_URI`, si no en `datos/noticias.jsonl`. |
| `ESQUEMA.md` | Formato de cada noticia (el contrato con la DB). |
| `ejemplos/noticias_ejemplo.jsonl` | Noticias reales de ejemplo, 2 por fuente. |
| `Dockerfile`, `docker-compose.yml` | El servicio `funnel`; lo incluye el `docker-compose.yml` de la raíz. |

## Uso

**Con Docker, desde la raíz del repo** (escribe en MongoDB):

```bash
docker compose run --rm funnel                              # últimas 24 h
docker compose run --rm funnel python funnel.py --horas 48
docker compose run --rm funnel python fuentes_curadas.py --solo "Hacker News" --horas 48   # probar una fuente
```

**Sin Docker, desde `funnel/`:**

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt   # una sola vez
.venv/bin/python funnel.py                         # sin MONGODB_URI: últimas 24 h -> datos/noticias.jsonl
.venv/bin/python fuentes_curadas.py --solo "Hacker News" --horas 48   # probar una fuente, imprime JSON
```
