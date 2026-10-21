# Hedwix: cómo funciona hoy

> Estado al **21 de octubre de 2026**. Diagrama interactivo: [`docs/flujo-hedwix.html`](docs/flujo-hedwix.html)
> (ábrelo en el navegador; en gris y con línea punteada está lo que todavía no existe).

Hedwix es un bot de noticias de IA. Junta noticias de muchas fuentes, las guarda en una base de datos y,
más adelante, un agente las consultará y se las mandará a los usuarios por WhatsApp.

```
 ENCENDIDO ───────────────────────────────────────────────────    APAGADO (siguiente) ─────────────────────
 Curated Sources ─► Information Funnel ─► MongoDB  ─ ─ ─ ─ ─ ─►  MCP ─► Cloudflare ─► Agent
 (Email: apagado) ─ ┘        │               ▲  │
                             ▼               │  └ ─ ─ ─ ─ ─ ─ ─►  Agent-Dispatch ─► Twilio ─► WhatsApp ─► Usuarios
                      noticias.jsonl ─ cargar_jsonl.py
```

| Pieza | Estado | Dónde vive |
|---|---|---|
| Curated Sources | ✅ funciona | `fuentes_curadas.py` |
| Email | ⏸ pendiente (Diego) | — |
| Information Funnel | ✅ funciona, escribe en Mongo | `funnel.py` |
| **DB (MongoDB)** | ✅ funciona, local en Docker | `db/` (esta carpeta) |
| MCP, Cloudflare, Agent | ⏸ pendiente | — |
| Agent-Dispatch, Twilio, WhatsApp | ⏸ pendiente | — |

---

## 1. De dónde salen las noticias: Curated Sources

`fuentes_curadas.py` consulta **25 fuentes**:

| Tipo de fuente | Fuentes |
|---|---|
| Blogs de laboratorios | OpenAI, DeepMind, Anthropic, Meta, Mistral, Hugging Face |
| Newsletters | Import AI, Latent Space, Last Week in AI… |
| Papers | arXiv cs.AI / cs.CL / cs.LG, HF Daily Papers |
| Comunidad | Hacker News |
| Rankings de modelos | OpenRouter, HF trending |

Además de consultarlas:
- Normaliza cada noticia a **un solo formato de 12 campos**. Ese formato está descrito en `ESQUEMA.md`.
- Descarga el texto completo de las notas que lo necesitan, usando `trafilatura`.

El `id` de cada noticia es el **sha1 de su URL normalizada**, es decir, sin `utm_*`, sin `#` y sin la `/` final. Así, la misma nota que llega por dos fuentes cuenta como una sola.

## 2. El filtro: Information Funnel

En cada corrida, `funnel.py` hace cuatro cosas:

1. **Recibe** lo que trae Curated Sources de las últimas N horas (24 por defecto).
2. **Valida** cada noticia contra el formato acordado y descarta las que no cumplen.
3. **Quita repetidos**: pregunta a la DB cuáles de esos `id` ya existen.
4. **Guarda** las nuevas:
   - si existe `MONGODB_URI`, las inserta directo en MongoDB;
   - si no, las agrega a `datos/noticias.jsonl`, y luego `cargar_jsonl.py` las sube a Mongo.

**Corrida real del 21 de octubre:**
- Llegaron 773 noticias; 767 eran nuevas y 0 inválidas.
- Tardó ~3 minutos.
- Al repetir la corrida enseguida: 0 nuevas y 773 ya guardadas.
- **arXiv es ~80% del volumen** (614 de 773). Todavía no se decide si se queda.

## 3. La DB: MongoDB (mi pieza)

Corre en Docker con `mongo:7.0`, escucha sólo en `127.0.0.1:27017` y tiene autenticación. Todo está en `db/`.

**Base `hedwix`:**

| Colección | Qué guarda | Estado |
|---|---|---|
| `noticias` | Lo que entrega el funnel. `_id` = sha1 de la URL; fechas como `Date`. | **812 noticias** |
| `usuarios` | Suscriptores: teléfono E.164, preferencias (fuentes, temas, hora de envío). | lista, vacía |
| `envios` | Qué noticias se mandaron a quién por WhatsApp y su estado en Twilio. | lista, vacía |
| `digests` | El mensaje que escribe el Agent-Dispatch cada día. `_id` = fecha `AAAA-MM-DD`. | uno por día |
| `_migraciones` | Qué migraciones ya se aplicaron. | 3 |

Cómo se protege la DB:
- **Validador:** cada colección tiene uno (`$jsonSchema`) que rechaza documentos mal formados, por ejemplo un `origin` inválido, una URL rota o fechas como texto.
- **Sin duplicados:** como el `_id` es el sha1 de la URL, una noticia repetida simplemente no entra.
- **Usuarios:** `hedwix_app`, el que usa la aplicación, sólo tiene permisos sobre la base `hedwix`. `root` queda para respaldos y administración.

Índices de `noticias`, pensados para lo que pedirán el MCP y el agent:

| Índice | Sirve para |
|---|---|
| `recientes` | "lo último" |
| `por_fuente` | "lo último de Hacker News" |
| `populares` | ordenar por `score` (votos o puntos) |
| `busqueda` | buscar texto en título, resumen y contenido |

El código para leer y escribir está en `hedwix_db/noticias.py`: `recientes()`, `mas_populares()`, `buscar()`, `insertar_noticias()`. Las piezas que siguen lo van a reutilizar.

## 4. Lo que sigue (apagado)

| Pieza | Qué tomará de la DB | Lo que ya está listo |
|---|---|---|
| **Email** (Diego) | Nada: *escribe* noticias con `origin: "email"`. | El validador ya acepta ese `origin`. |
| **MCP** | Consultas de lectura: recientes, por fuente, búsqueda, populares. | Las funciones de `hedwix_db/noticias.py` y sus índices. |
| **Cloudflare** | Nada directo; expone el MCP hacia afuera. | — |
| **Agent** | Usa las tools del MCP. | — |
| **Agent-Dispatch** | Lee `usuarios` y `noticias`, escribe en `digests` y `envios`. | Colecciones e índices, incluido el que evita reenviar una noticia. |
| **Twilio → WhatsApp** | Sus webhooks actualizan `envios.estado` usando `twilio_sid`. | Índice único sobre `twilio_sid`. |

---

## 5. Cómo hacer correr todo hoy

```bash
# 1. Levantar la DB
cd db
docker compose up -d && docker compose exec app python migrar.py

# 2. Traer noticias de las últimas 24 h (el funnel escribe directo en Mongo)
cd ..
set -a; source db/.env; set +a
docker run --rm --network hedwix_default -e MONGODB_URI -v "$PWD":/funnel:ro -w /funnel \
  python:3.13-slim sh -c 'pip install -q -r requirements.txt && python funnel.py --horas 24'

# 3. Ver qué hay
cd db
docker compose exec app python consultas.py --buscar "agent"

# 4. Respaldar
scripts/respaldar.sh
```

Detalle de instalación, respaldos, migraciones y solución de problemas: [`GUIA.md`](GUIA.md).

## 6. Cosas a tener en cuenta

- **MongoDB 8 no arranca en este kernel (7.0)**, por eso se usa 7.0 ([SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)).
- **Texto completo que falla:** en la primera corrida no se pudo bajar el texto completo de 6 notas de OpenAI ni de una de Reuters; esas notas quedaron sólo con su resumen. Hay que avisarle a quien lleva el funnel.
- **Rankings:** los de OpenRouter y HF guardan el `rank` del día en que el modelo entró, no el actual, porque un modelo que sigue en el ranking no se vuelve a guardar.
- **Respaldos:** `backups/` no se sube a git. Copia los respaldos importantes fuera de esta máquina.
