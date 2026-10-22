"""Carga en Mongo las noticias de un archivo JSONL del Information Funnel. Las repetidas se ignoran.

Uso (desde la raíz): docker compose exec app python cargar_jsonl.py /repo/funnel/datos/noticias.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

from hedwix_db import obtener_db
from hedwix_db.noticias import insertar_noticias


def main():
    parser = argparse.ArgumentParser(description="Carga noticias del funnel (JSONL) en la colección noticias.")
    parser.add_argument("archivo", type=Path)
    args = parser.parse_args()

    with args.archivo.open(encoding="utf-8") as lineas:
        items = [json.loads(linea) for linea in lineas if linea.strip()]

    nuevas, repetidas, invalidas = insertar_noticias(obtener_db(), items)

    print(f"[db] leídas {len(items)} | nuevas {sum(nuevas.values())} | ya guardadas {sum(repetidas.values())}"
          f" | inválidas {sum(invalidas.values())} <- {args.archivo}", file=sys.stderr)
    for fuente in sorted(set(nuevas) | set(repetidas) | set(invalidas)):
        print(f"[db]   {fuente}: {nuevas[fuente]} nuevas, {repetidas[fuente]} ya guardadas,"
              f" {invalidas[fuente]} inválidas", file=sys.stderr)


if __name__ == "__main__":
    main()
