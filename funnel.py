"""Information Funnel (pieza 3 de Hedwix): junta las noticias de las fuentes, las valida y entrega solo las nuevas.

Pasos de cada corrida:
1. Recibir: por ahora solo de Curated Sources (fuentes_curadas.recolectar). Email se conecta después.
2. Validar: cada item debe cumplir el formato descrito en ESQUEMA.md. Los que no, se descartan y se avisan.
3. Quitar repetidos: si el `id` ya se entregó en una corrida anterior, no se vuelve a entregar.
4. Guardar: si está definida la variable MONGODB_URI, en la colección `noticias` de la DB de Egon (MongoDB);
   si no, agrega las noticias nuevas al archivo JSONL (una noticia por línea).

Uso: .venv/bin/python funnel.py [--horas 24] [--salida datos/noticias.jsonl]
     MONGODB_URI="mongodb://usuario:clave@127.0.0.1:27017/hedwix?authSource=hedwix" .venv/bin/python funnel.py
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import cache
from pathlib import Path

import fuentes_curadas

ARCHIVO_DE_SALIDA = Path(__file__).parent / "datos" / "noticias.jsonl"

CAMPOS = ["id", "origin", "source", "source_type", "title", "url", "published", "fetched_at", "summary", "content",
          "score", "extra"]
ORIGENES_VALIDOS = {"curated", "email"}
TIPOS_DE_FUENTE_VALIDOS = {"rss", "api", "scrape"}


# ============================================================ Validación

def es_fecha_iso_con_zona(texto):
    try:
        return datetime.fromisoformat(texto).tzinfo is not None
    except (TypeError, ValueError):
        return False


def problemas_del_item(item):
    """Regresa la lista de problemas que tiene un item. Lista vacía = el item es válido."""
    if not isinstance(item, dict):
        return ["no es un diccionario"]
    if list(item) != CAMPOS:
        return [f"campos distintos a los acordados: {list(item)}"]

    problemas = []
    if not (isinstance(item["id"], str) and re.fullmatch(r"[0-9a-f]{40}", item["id"])):
        problemas.append("id no es un sha1")
    elif item["id"] != fuentes_curadas.id_de_url(item["url"] or ""):
        problemas.append("id no corresponde a la url")
    if item["origin"] not in ORIGENES_VALIDOS:
        problemas.append(f"origin inválido: {item['origin']!r}")
    if not (isinstance(item["source"], str) and item["source"].strip()):
        problemas.append("source vacío")
    if item["source_type"] not in TIPOS_DE_FUENTE_VALIDOS:
        problemas.append(f"source_type inválido: {item['source_type']!r}")
    if not (isinstance(item["title"], str) and item["title"].strip()):
        problemas.append("title vacío")
    if not (isinstance(item["url"], str) and re.match(r"https?://[^\s/]+", item["url"])):
        problemas.append(f"url inválida: {item['url']!r}")
    if not es_fecha_iso_con_zona(item["published"]):
        problemas.append(f"published no es fecha ISO con zona horaria: {item['published']!r}")
    if not es_fecha_iso_con_zona(item["fetched_at"]):
        problemas.append(f"fetched_at no es fecha ISO con zona horaria: {item['fetched_at']!r}")
    if not isinstance(item["summary"], str):
        problemas.append("summary no es texto")
    if not isinstance(item["content"], str):
        problemas.append("content no es texto")
    if item["score"] is not None and (isinstance(item["score"], bool) or not isinstance(item["score"], (int, float))):
        problemas.append(f"score no es número: {item['score']!r}")
    if not isinstance(item["extra"], dict):
        problemas.append("extra no es un objeto")
    return problemas


# ============================================================ Almacenamiento
# Con MONGODB_URI se guarda en MongoDB; sin ella, en el archivo JSONL como antes.

@cache
def coleccion_de_noticias():
    """La colección `noticias` de MongoDB, o None si no está definida MONGODB_URI."""
    if not os.environ.get("MONGODB_URI"):
        return None
    from pymongo import MongoClient  # solo hace falta pymongo si se usa la DB
    return MongoClient(os.environ["MONGODB_URI"]).get_default_database()["noticias"]


def a_documento(item):
    """En la DB el `id` va como `_id` (así Mongo rechaza repetidos) y las fechas como Date, no como texto."""
    documento = {"_id": item["id"], **{campo: valor for campo, valor in item.items() if campo != "id"}}
    documento["published"] = datetime.fromisoformat(item["published"])
    documento["fetched_at"] = datetime.fromisoformat(item["fetched_at"])
    return documento


def ids_ya_guardados(archivo, ids=()):
    """Los ids que ya están guardados. En la DB solo se buscan los `ids` dados; en el archivo, se leen todos."""
    coleccion = coleccion_de_noticias()
    if coleccion is not None:
        return set(coleccion.distinct("_id", {"_id": {"$in": list(ids)}}))
    if not archivo.exists():
        return set()
    ids = set()
    with archivo.open(encoding="utf-8") as lineas:
        for linea in lineas:
            if linea.strip():
                ids.add(json.loads(linea)["id"])
    return ids


def guardar(items, archivo):
    """Inserta los items en la DB o los agrega al final del archivo, uno por línea."""
    coleccion = coleccion_de_noticias()
    if coleccion is not None:
        if items:
            coleccion.insert_many([a_documento(item) for item in items], ordered=False)
        return
    archivo.parent.mkdir(parents=True, exist_ok=True)
    with archivo.open("a", encoding="utf-8") as salida:
        for item in items:
            salida.write(json.dumps(item, ensure_ascii=False) + "\n")


# ============================================================ Corrida

def correr_funnel(desde, archivo=ARCHIVO_DE_SALIDA):
    """Hace una corrida completa y regresa las noticias nuevas que se guardaron."""
    recibidos = fuentes_curadas.recolectar(desde)
    ids_recibidos = [item["id"] for item in recibidos if isinstance(item, dict) and "id" in item]
    ya_guardados = ids_ya_guardados(archivo, ids_recibidos)

    nuevos = []
    repetidos = Counter()
    invalidos = Counter()
    for item in recibidos:
        problemas = problemas_del_item(item)
        if problemas:
            fuente = item.get("source", "?") if isinstance(item, dict) else "?"
            invalidos[fuente] += 1
            print(f"[funnel] descartado ({fuente}): {'; '.join(problemas)}", file=sys.stderr)
        elif item["id"] in ya_guardados:
            repetidos[item["source"]] += 1
        else:
            nuevos.append(item)
            ya_guardados.add(item["id"])

    guardar(nuevos, archivo)

    nuevos_por_fuente = Counter(item["source"] for item in nuevos)
    print(f"[funnel] recibidos {len(recibidos)} | nuevos {len(nuevos)} | ya guardados {sum(repetidos.values())}"
          f" | inválidos {sum(invalidos.values())} -> {'MongoDB' if coleccion_de_noticias() is not None else archivo}",
          file=sys.stderr)
    for fuente in sorted(set(nuevos_por_fuente) | set(repetidos) | set(invalidos)):
        print(f"[funnel]   {fuente}: {nuevos_por_fuente[fuente]} nuevos, {repetidos[fuente]} ya guardados,"
              f" {invalidos[fuente]} inválidos", file=sys.stderr)
    return nuevos


def main():
    parser = argparse.ArgumentParser(description="Junta las noticias de las fuentes y guarda solo las nuevas.")
    parser.add_argument("--horas", type=int, default=24, help="qué tan atrás buscar (default: 24)")
    parser.add_argument("--salida", type=Path, default=ARCHIVO_DE_SALIDA,
                        help=f"archivo JSONL donde se guardan (default: {ARCHIVO_DE_SALIDA})")
    args = parser.parse_args()

    desde = datetime.now(timezone.utc) - timedelta(hours=args.horas)
    correr_funnel(desde, args.salida)


if __name__ == "__main__":
    main()
