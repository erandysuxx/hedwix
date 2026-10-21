"""Migraciones de la base hedwix. Cada archivo NNN_nombre.py define DESCRIPCION y aplicar(db).

Las corre migrar.py, en orden, y anota las aplicadas en la colección `_migraciones`.
Una migración ya aplicada no se vuelve a correr: para cambiar algo, crear una nueva.
"""


def asegurar_coleccion(db, nombre, esquema):
    """Crea la colección con su validador $jsonSchema, o actualiza el validador si ya existe."""
    if nombre in db.list_collection_names():
        db.command("collMod", nombre, validator={"$jsonSchema": esquema}, validationLevel="strict")
    else:
        db.create_collection(nombre, validator={"$jsonSchema": esquema}, validationLevel="strict")
