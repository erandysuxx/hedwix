# Revisar los datos de la DB

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
uv pip install --python db/testing/.venv/bin/python -r funnel/requirements.txt -r db/requirements.txt -r db/testing/requirements.txt
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
