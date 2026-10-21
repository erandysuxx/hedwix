from pymongo import ASCENDING, DESCENDING

from migraciones import asegurar_coleccion

DESCRIPCION = "Colecciones usuarios y envios para el Agent-Dispatch (Twilio / WhatsApp)"

ESQUEMA_USUARIOS = {
    "bsonType": "object",
    "required": ["telefono", "activo", "creado"],
    "properties": {
        "telefono": {"bsonType": "string", "pattern": "^\\+[1-9][0-9]{7,14}$", "description": "E.164, ej. +5215512345678"},
        "nombre": {"bsonType": "string"},
        "activo": {"bsonType": "bool"},
        "preferencias": {
            "bsonType": "object",
            "properties": {
                "fuentes": {"bsonType": "array", "items": {"bsonType": "string"}},
                "temas": {"bsonType": "array", "items": {"bsonType": "string"}},
                "hora_envio": {"bsonType": "string", "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$"},
                "zona_horaria": {"bsonType": "string"},
            },
        },
        "creado": {"bsonType": "date"},
        "actualizado": {"bsonType": "date"},
    },
}

ESQUEMA_ENVIOS = {
    "bsonType": "object",
    "required": ["usuario_id", "noticia_ids", "canal", "estado", "creado"],
    "properties": {
        "usuario_id": {"bsonType": "objectId"},
        "noticia_ids": {"bsonType": "array", "items": {"bsonType": "string", "pattern": "^[0-9a-f]{40}$"}},
        "canal": {"enum": ["whatsapp"]},
        "twilio_sid": {"bsonType": ["string", "null"]},
        "estado": {"enum": ["pendiente", "enviado", "entregado", "leido", "fallido"]},
        "error": {"bsonType": ["string", "null"]},
        "creado": {"bsonType": "date"},
        "actualizado": {"bsonType": "date"},
    },
}


def aplicar(db):
    asegurar_coleccion(db, "usuarios", ESQUEMA_USUARIOS)
    db.usuarios.create_index([("telefono", ASCENDING)], name="telefono_unico", unique=True)

    asegurar_coleccion(db, "envios", ESQUEMA_ENVIOS)
    db.envios.create_index([("usuario_id", ASCENDING), ("creado", DESCENDING)], name="historial_usuario")
    # Para no reenviarle a un usuario una noticia que ya recibió
    db.envios.create_index([("usuario_id", ASCENDING), ("noticia_ids", ASCENDING)], name="ya_enviadas")
    # Los webhooks de estado de Twilio buscan por SID; sólo se indexan los envíos que ya tienen uno
    db.envios.create_index([("twilio_sid", ASCENDING)], name="twilio_sid_unico", unique=True,
                           partialFilterExpression={"twilio_sid": {"$type": "string"}})
