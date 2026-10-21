from pymongo import ASCENDING, DESCENDING, TEXT

from migraciones import asegurar_coleccion

DESCRIPCION = "Colección noticias: validador con las reglas de ESQUEMA.md e índices para MCP / agent"

TEXTO = {"bsonType": "string"}
FECHA = {"bsonType": "date"}

ESQUEMA = {
    "bsonType": "object",
    "required": ["_id", "origin", "source", "source_type", "title", "url", "published", "fetched_at", "summary",
                 "content", "score", "extra"],
    "properties": {
        "_id": {"bsonType": "string", "pattern": "^[0-9a-f]{40}$", "description": "sha1 de la URL normalizada"},
        "origin": {"enum": ["curated", "email"]},
        "source": {"bsonType": "string", "minLength": 1},
        "source_type": {"enum": ["rss", "api", "scrape"]},
        "title": {"bsonType": "string", "pattern": "\\S", "maxLength": 300},
        "url": {"bsonType": "string", "pattern": "^https?://[^\\s/]+"},
        "published": FECHA,
        "fetched_at": FECHA,
        "summary": {"bsonType": "string", "maxLength": 500},
        "content": {"bsonType": "string", "maxLength": 100_000},
        "score": {"bsonType": ["int", "long", "double", "null"]},
        "extra": {"bsonType": "object"},
    },
}


def aplicar(db):
    asegurar_coleccion(db, "noticias", ESQUEMA)
    db.noticias.create_index([("published", DESCENDING)], name="recientes")
    db.noticias.create_index([("source", ASCENDING), ("published", DESCENDING)], name="por_fuente")
    db.noticias.create_index([("score", DESCENDING)], name="populares",
                             partialFilterExpression={"score": {"$type": "number"}})
    db.noticias.create_index([("title", TEXT), ("summary", TEXT), ("content", TEXT)], name="busqueda",
                             weights={"title": 10, "summary": 5, "content": 1}, default_language="english")
