from migraciones import asegurar_coleccion

DESCRIPCION = "Colección digests: el mensaje que escribe el Agent-Dispatch cada día, con la fecha como _id"

TEXTO = {"bsonType": "string"}

ESQUEMA = {
    "bsonType": "object",
    "required": ["_id", "generado_at", "modelo", "mensaje", "noticias"],
    "properties": {
        "_id": {"bsonType": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                "description": "fecha del digest en México, AAAA-MM-DD"},
        "generado_at": {"bsonType": "date"},
        "modelo": TEXTO,
        "mensaje": {"bsonType": "string", "minLength": 1, "maxLength": 1600},
        "noticias": {
            "bsonType": "array",
            "items": {
                "bsonType": "object",
                "required": ["id", "source", "title", "url", "por_que"],
                "properties": {
                    "id": {"bsonType": "string", "pattern": "^[0-9a-f]{40}$"},
                    "source": TEXTO,
                    "title": TEXTO,
                    "url": TEXTO,
                    "por_que": TEXTO,
                },
            },
        },
    },
}


def aplicar(db):
    # El _id es la fecha, así que consultar "el digest de ayer" ya usa el índice de _id
    asegurar_coleccion(db, "digests", ESQUEMA)
