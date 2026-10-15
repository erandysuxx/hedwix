# Noticias del Funnel: formato para la DB

Este documento es para Egon (DB, pieza 4). Explica qué entrega el Information Funnel (pieza 3) y cómo se ve cada noticia.

## Cómo se obtienen los datos

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt   # una sola vez
.venv/bin/python funnel.py                 # últimas 24 h -> datos/noticias.jsonl
.venv/bin/python funnel.py --horas 168     # última semana
```

- La salida es **JSONL**: una noticia por línea, en JSON.
- Cada corrida **agrega al final** solo las noticias nuevas. Si un `id` ya está en el archivo, no se vuelve a escribir.
- Hay noticias reales de ejemplo, 2 por fuente, en `ejemplos/noticias_ejemplo.jsonl`.
- El resumen de cada corrida (nuevas, repetidas, inválidas por fuente) y las alertas de fuentes rotas salen por stderr, no en el archivo.

Cuando la DB exista, el Funnel puede escribir directo en ella: solo cambian `guardar()` e `ids_ya_guardados()` en `funnel.py`.

## Campos

Todas las noticias traen exactamente estos 12 campos, en este orden. El Funnel descarta cualquier item que no cumpla estas reglas.

| Campo | Tipo | ¿Puede ser null? | Qué es |
|---|---|---|---|
| `id` | texto, 40 caracteres hex | no | sha1 de la URL normalizada (sin `utm_*`, sin `#fragmento`, sin `/` final). **Úsalo como llave primaria.** |
| `origin` | texto | no | De qué pieza viene: `curated` (hoy siempre) o `email` (cuando se conecte Diego). |
| `source` | texto | no | Nombre de la fuente, por ejemplo `Hacker News`. Lista completa abajo. |
| `source_type` | texto | no | `rss`, `api` o `scrape`. |
| `title` | texto | no | Título sin HTML. Máximo 300 caracteres. |
| `url` | texto | no | Link a la noticia, `http(s)://`. El más largo visto: ~120 caracteres. |
| `published` | fecha ISO 8601 con zona (UTC) | no | Cuándo se publicó. Ejemplo: `2026-10-15T04:00:00+00:00`. |
| `fetched_at` | fecha ISO 8601 con zona (UTC) | no | Cuándo la trajo el Funnel. Es igual para todas las noticias de una corrida. |
| `summary` | texto | no (puede ser `""`) | Resumen corto en una sola línea, sin HTML. Máximo 500 caracteres. Sirve para listar. |
| `content` | texto | no (puede ser `""`) | **Texto completo de la noticia**, sin HTML, con un párrafo por línea (`\n`). Máximo 100,000 caracteres. Ver "Qué hay en `content`" abajo. |
| `score` | número | **sí** | Popularidad: votos (HF Daily Papers) o puntos (Hacker News). **Más alto es mejor.** `null` en las demás fuentes. |
| `extra` | objeto JSON | no (puede ser `{}`) | Datos propios de cada fuente. Ver tabla abajo. |

## Tabla sugerida (Postgres)

Es solo una propuesta; ajústala como te convenga.

```sql
CREATE TABLE noticias (
    id           CHAR(40)    PRIMARY KEY,
    origin       TEXT        NOT NULL CHECK (origin IN ('curated', 'email')),
    source       TEXT        NOT NULL,
    source_type  TEXT        NOT NULL CHECK (source_type IN ('rss', 'api', 'scrape')),
    title        TEXT        NOT NULL,
    url          TEXT        NOT NULL,
    published    TIMESTAMPTZ NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL,
    summary      TEXT        NOT NULL DEFAULT '',
    content      TEXT        NOT NULL DEFAULT '',
    score        DOUBLE PRECISION,
    extra        JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX noticias_published ON noticias (published DESC);
CREATE INDEX noticias_source    ON noticias (source);
```

Para cargar: `INSERT ... ON CONFLICT (id) DO NOTHING`. El Funnel ya no manda repetidos, pero así la DB también queda protegida.

## Qué hay en `content`

| Fuentes | De dónde sale el texto | Largo típico |
|---|---|---|
| Last Week in AI, Import AI, Latent Space, The Gradient, Ahead of AI, AWS ML Blog, GitHub Changelog, Simon Willison | El feed ya trae la nota completa | 1,000 a 80,000 caracteres |
| OpenAI Blog, Hugging Face Blog, TechCrunch AI, Databricks Blog, Google DeepMind Blog, Mistral News, Anthropic News, Meta AI Blog, Hacker News | El Funnel descarga la página de cada nota y extrae el artículo con [trafilatura](https://trafilatura.readthedocs.io/) | 2,000 a 30,000 caracteres |
| arXiv, HF Daily Papers | El abstract (no se baja el PDF) | 500 a 2,000 caracteres |
| OpenRouter | La descripción del modelo | ~200 caracteres |
| Hugging Face: modelos trending | No hay texto | `""` |

Si la descarga de una nota falla (el sitio bloquea, es un PDF o un tweet), `content` se queda con el texto corto que traía la fuente y se avisa por stderr. En la prueba del 15 de octubre se bajaron 28 de 28 notas; en pruebas anteriores Reuters respondió 401.

Con texto completo, el archivo pesa unos 2 MB por día (casi todo es arXiv).

## Fuentes y qué trae `extra`

| `source` | `source_type` | `score` | `extra` |
|---|---|---|---|
| OpenAI Blog, Hugging Face Blog, Last Week in AI, Import AI, Latent Space, The Gradient, Ahead of AI, TechCrunch AI, AWS ML Blog, GitHub Changelog, Databricks Blog, Google DeepMind Blog, Mistral News, Simon Willison | `rss` | null | `tags`: lista de etiquetas del feed |
| arXiv cs.AI, arXiv cs.CL, arXiv cs.LG | `rss` | null | `tags` |
| Hacker News | `rss` | puntos | `hn_url` (hilo de comentarios), `comments` (número) |
| HF Daily Papers | `api` | votos | `arxiv` (link), `github` (link o null), `org` (organización o null) |
| OpenRouter: top semanal, OpenRouter: agénticos | `api` | null | `rank` (1 es el mejor), `model_id`, `context_length`, `pricing` |
| OpenRouter: nuevos | `api` | null | `model_id`, `context_length`, `pricing` |
| Hugging Face: modelos trending | `api` | null | `rank` (1 es el mejor), `likes`, `downloads`, `pipeline_tag`, `num_parameters` |
| Anthropic News, Meta AI Blog | `scrape` | null | `{}` |

Cualquier fuente puede traer además `also_in`: la lista de otras fuentes donde salió la misma URL (por ejemplo, un modelo que está en "top semanal" y en "agénticos").

## Cosas a tener en cuenta

- **Volumen:** arXiv es ~80% de las noticias (unos 700 papers al día entre las tres categorías). Todavía no se decide si se queda.
- **Rankings:** OpenRouter top/agénticos y HF trending no tienen fecha propia; `published` es la hora de la consulta. Como el `id` sale de la URL del modelo, un modelo que sigue en el ranking días después **no se vuelve a guardar**. Por eso `rank` refleja el día en que entró, no el lugar actual.
- **Fechas sin hora:** Anthropic, Meta y HF Daily Papers solo dan el día, así que `published` queda a las `00:00:00+00:00` de ese día.
- **Email:** cuando se conecte, sus noticias llegarán con este mismo formato y `origin: "email"`.
