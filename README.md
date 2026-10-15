# Hedwix: Curated Sources + Information Funnel

Piezas 2 y 3 del bot de noticias de IA Hedwix. Trae noticias de 25 fuentes curadas (blogs de laboratorios, newsletters, arXiv, Hacker News, rankings de modelos), las normaliza a un solo formato, descarta las inválidas o repetidas y las guarda para la DB.

| Archivo | Qué hace |
|---|---|
| `fuentes_curadas.py` | Trae y normaliza las noticias de cada fuente, con el texto completo de cada nota. |
| `funnel.py` | Valida las noticias, quita las que ya se guardaron y agrega las nuevas a `datos/noticias.jsonl`. |
| `ESQUEMA.md` | Formato de cada noticia y tabla sugerida para la DB. |
| `ejemplos/noticias_ejemplo.jsonl` | Noticias reales de ejemplo, 2 por fuente. |

## Uso

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt   # una sola vez
.venv/bin/python funnel.py                         # últimas 24 h -> datos/noticias.jsonl
.venv/bin/python fuentes_curadas.py --solo "Hacker News" --horas 48   # probar una fuente, imprime JSON
```
