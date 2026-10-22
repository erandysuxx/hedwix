"""Colección `noticias`: lo que entrega el Information Funnel (formato en ESQUEMA.md, en la raíz del repo).

Diferencias con el JSONL del funnel:
- `id` se guarda como `_id`, así Mongo rechaza solo los repetidos.
- `published` y `fetched_at` se guardan como fechas (Date), no como texto.
"""

import sys
from collections import Counter
from datetime import datetime

from pymongo import DESCENDING
from pymongo.errors import BulkWriteError

TAMANO_DE_LOTE = 500
LLAVE_DUPLICADA = 11000
NO_PASA_VALIDACION = 121


def a_documento(item):
    """Convierte una noticia del funnel en documento de Mongo."""
    documento = {"_id": item["id"], **{campo: valor for campo, valor in item.items() if campo != "id"}}
    for campo in ("published", "fetched_at"):
        if isinstance(documento.get(campo), str):
            documento[campo] = datetime.fromisoformat(documento[campo])
    return documento


def a_item(documento):
    """Lo contrario de a_documento: regresa la noticia con el formato del funnel (para MCP / agent)."""
    item = {"id": documento["_id"], **{campo: valor for campo, valor in documento.items() if campo != "_id"}}
    for campo in ("published", "fetched_at"):
        if isinstance(item.get(campo), datetime):
            item[campo] = item[campo].isoformat(timespec="seconds")
    return item


def insertar_noticias(db, items):
    """Inserta las noticias nuevas. Regresa (nuevas, repetidas, invalidas), cada una un Counter por fuente."""
    nuevas, repetidas, invalidas = Counter(), Counter(), Counter()
    documentos = [a_documento(item) for item in items]

    for inicio in range(0, len(documentos), TAMANO_DE_LOTE):
        lote = documentos[inicio:inicio + TAMANO_DE_LOTE]
        fallidos = {}
        try:
            db.noticias.insert_many(lote, ordered=False)
        except BulkWriteError as error:
            fallidos = {falla["index"]: falla for falla in error.details["writeErrors"]}

        for indice, documento in enumerate(lote):
            fuente = documento.get("source", "?")
            falla = fallidos.get(indice)
            if falla is None:
                nuevas[fuente] += 1
            elif falla["code"] == LLAVE_DUPLICADA:
                repetidas[fuente] += 1
            elif falla["code"] == NO_PASA_VALIDACION:
                invalidas[fuente] += 1
                print(f"[db] inválida ({fuente}) {documento['_id']}: {falla.get('errInfo', falla['errmsg'])}",
                      file=sys.stderr)
            else:
                raise RuntimeError(f"Error inesperado al insertar {documento['_id']}: {falla['errmsg']}")

    return nuevas, repetidas, invalidas


def ids_existentes(db, ids):
    """De los ids dados, cuáles ya están guardados."""
    return set(db.noticias.distinct("_id", {"_id": {"$in": list(ids)}}))


def recientes(db, desde=None, fuentes=None, limite=50, excluir_fuentes=None):
    """Las noticias más recientes, opcionalmente desde una fecha, y sólo de ciertas `fuentes` o sin las de
    `excluir_fuentes` (nombres o regex). Si se dan las dos, manda `fuentes`."""
    filtro = {}
    if desde:
        filtro["published"] = {"$gte": desde}
    if fuentes:
        filtro["source"] = {"$in": list(fuentes)}
    elif excluir_fuentes:
        filtro["source"] = {"$nin": list(excluir_fuentes)}
    return [a_item(doc) for doc in db.noticias.find(filtro).sort("published", DESCENDING).limit(limite)]


def mas_populares(db, desde=None, limite=10):
    """Las de mayor `score` (puntos de Hacker News o votos de HF Daily Papers)."""
    filtro = {"score": {"$type": "number"}}
    if desde:
        filtro["published"] = {"$gte": desde}
    return [a_item(doc) for doc in db.noticias.find(filtro).sort("score", DESCENDING).limit(limite)]


def buscar(db, texto, limite=20, fuentes=None, desde=None):
    """Búsqueda de texto en title, summary y content, ordenada por relevancia.

    Opcionalmente sólo de ciertas fuentes y publicadas desde una fecha.
    """
    filtro = {"$text": {"$search": texto}}
    if fuentes:
        filtro["source"] = {"$in": list(fuentes)}
    if desde:
        filtro["published"] = {"$gte": desde}
    cursor = (db.noticias.find(filtro, {"relevancia": {"$meta": "textScore"}})
              .sort([("relevancia", {"$meta": "textScore"})]).limit(limite))
    # "relevancia" sólo sirve para ordenar; se quita para regresar el mismo formato que las demás consultas
    return [a_item({campo: valor for campo, valor in doc.items() if campo != "relevancia"}) for doc in cursor]


def por_fuente(db):
    """Cada fuente con cuántas noticias tiene y la fecha de la más reciente, de la que tiene más a la que menos."""
    filas = db.noticias.aggregate([
        {"$group": {"_id": "$source", "source_type": {"$first": "$source_type"}, "noticias": {"$sum": 1},
                    "mas_reciente": {"$max": "$published"}}},
        {"$sort": {"noticias": -1, "_id": 1}},
    ])
    return [{"source": fila["_id"], "source_type": fila["source_type"], "noticias": fila["noticias"],
             "mas_reciente": fila["mas_reciente"].isoformat(timespec="seconds")} for fila in filas]
