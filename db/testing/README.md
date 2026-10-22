# Revisar los datos de la DB

Hay dos notebooks:

| Notebook | Qué prueba |
|---|---|
| `revisar_datos.ipynb` | La colección `noticias` y la DB en general (sección de abajo). |
| `revisar_dispatch.ipynb` | El código real de `dispatch/dispatch.py` contra la DB, con Claude simulado y **sin escribir nada** (ver al final). |

Los dos se abren y se corren igual (opciones 1 a 3). En los comandos de la opción 3 cambia `revisar_datos` por `revisar_dispatch`.

`revisar_datos.ipynb` se conecta a MongoDB con `MONGODB_URI` y revisa:

- **Conteos:** cuántos documentos tiene cada colección y qué migraciones se aplicaron.
- **Panorama:** noticias por fuente, por día y por corrida del funnel, con gráficas.
- **15 chequeos de calidad, cada uno ✅ o ❌:**
  - todas las noticias cumplen el validador;
  - el `_id` corresponde a la URL y no hay URLs repetidas;
  - las fechas son `Date` y tienen sentido;
  - `score` sólo aparece en las fuentes que lo tienen;
  - los títulos no tienen HTML;
  - ninguna fuente trae todas sus notas sin texto;
  - las consultas usan sus índices;
  - existen `usuarios` y `envios` con su validador.
- **Muestras:** las últimas noticias, las más populares, una búsqueda de texto y una noticia completa.

Necesita que Mongo esté arriba (`docker compose up -d`, desde la raíz del repo).

## Opción 1: abrirlo en VS Code

VS Code corre el notebook con el **kernel** (Python) que elijas. El Python del sistema no tiene `pandas` ni
`pymongo`, y por eso falla desde la primera celda. Usa el entorno de esta carpeta:

```bash
# Una sola vez, desde la raíz del repo. uv se instala en ~/.local/bin sin sudo:
#   curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.13 db/testing/.venv
uv pip install --python db/testing/.venv/bin/python -r funnel/requirements.txt -r dispatch/requirements.txt -r db/requirements.txt -r db/testing/requirements.txt
# Registrarlo como kernel con nombre, para que VS Code lo encuentre aunque el .venv esté en una subcarpeta:
db/testing/.venv/bin/python -m ipykernel install --user --name hedwix-db --display-name "Hedwix DB (db/testing/.venv)"
```

En VS Code: recarga la ventana (*Developer: Reload Window*), abre `revisar_datos.ipynb` → **Select Kernel**
(arriba a la derecha) → *Jupyter Kernel…* → **Hedwix DB (db/testing/.venv)**. Si no aparece, usa
*Python Environments… → Enter interpreter path…* con la ruta a `db/testing/.venv/bin/python`. Fuera de Docker, el notebook lee la URI del `.env` de la raíz y se conecta por `127.0.0.1`.

**Sin instalar nada:** *Select Kernel → Existing Jupyter Server* → `http://127.0.0.1:8888`, con el servicio
`notebook` de la opción 2 arriba. Así el código corre dentro de Docker.

## Opción 2: abrirlo en Jupyter (navegador)

```bash
# desde la raíz del repo
docker compose --profile testing up -d --build notebook
```

Abre <http://127.0.0.1:8888> → `revisar_datos.ipynb` → *Run → Run All Cells*.
Jupyter no tiene contraseña porque sólo escucha en esta máquina (`127.0.0.1`).

Para apagarlo: `docker compose --profile testing stop notebook`

## Opción 3: correrlo desde la terminal y generar un reporte HTML

```bash
# desde la raíz del repo
docker compose --profile testing run --rm --no-deps notebook sh -c '
  jupyter nbconvert --to notebook --execute revisar_datos.ipynb --output-dir salida --output revisar_datos.ejecutado.ipynb &&
  jupyter nbconvert --to html salida/revisar_datos.ejecutado.ipynb --output-dir salida --output revisar_datos.html'
```

El reporte queda en `db/testing/salida/revisar_datos.html`. Si algún chequeo falla, el comando termina con
error y dice cuáles fallaron, así que sirve para revisar después de cada corrida del funnel.
`salida/` no se sube a git.

## Notas

- **Guarda el notebook sin salidas** (*Edit → Clear Outputs of All Cells*) antes de hacer commit, para que el diff no se llene de datos.
- Las líneas ℹ️ son informativas y no fallan. Ejemplos: notas cuyo texto completo no se pudo descargar, o links de Hacker News a sitios que bloquean la descarga.

## `revisar_dispatch.ipynb`: el Dispatch contra la DB

Corre las funciones reales de `dispatch.py` paso por paso. Sólo cambia la llamada a la API de Claude por una
simulación, así que no necesita `ANTHROPIC_API_KEY` ni gasta tokens.

| Paso | Qué revisa |
|---|---|
| 0. Preparación | Que la migración `003_digests` esté aplicada. Que `digests` no se haya creado sin validador, que es lo que pasa si el dispatch corre antes de la migración. |
| 1. Leer | Que lea de MongoDB y no del JSONL, cuántas noticias toma por `fetched_at`, cuántas se perderían por `published` y que use el índice `por_llegada`. |
| 2. Escoger | El texto exacto que recibe Claude y su tamaño, con y sin arXiv. |
| 3. Escribir | Las notas completas que recibe Claude y el límite de 1,600 caracteres. |
| 4. Guardar | Que el digest pase el validador de `digests`, revisado con `$documents` sin insertar nada. También prueba que el validador rechace lo que no debe entrar. |
| 5. Digests guardados | Si ya hay, que cumplan el validador y que cada noticia exista en `noticias`. |

- **⚠️ Avisos:** no fallan. Ejemplos: la migración 003 sin aplicar, o noticias sin texto que Claude podría escoger.
- **❌ Chequeos:** sí fallan, porque indican un problema real en los datos.

**Antes de usar `dispatch/dispatch.py` de verdad**, aplica la migración 003 (desde la raíz del repo):
`docker compose exec app python migrar.py`
