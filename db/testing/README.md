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

Necesita que Mongo esté arriba (`docker compose up -d`, desde `db/`).

## Opción 1: abrirlo en Jupyter

```bash
cd db
docker compose --profile testing up -d --build notebook
```

Abre <http://127.0.0.1:8888> → `revisar_datos.ipynb` → *Run → Run All Cells*.
Jupyter no tiene contraseña porque sólo escucha en esta máquina (`127.0.0.1`).

Para apagarlo: `docker compose --profile testing stop notebook`

## Opción 2: correrlo desde la terminal y generar un reporte HTML

```bash
cd db
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
