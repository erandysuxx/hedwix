"""Aplica en orden las migraciones de migraciones/ que todavía no se han aplicado.

Uso: docker compose exec app python migrar.py
"""

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from hedwix_db import obtener_db

CARPETA = Path(__file__).parent / "migraciones"
COLECCION = "_migraciones"


def migraciones_disponibles():
    return sorted(ruta for ruta in CARPETA.glob("[0-9][0-9][0-9]_*.py"))


def cargar(ruta):
    spec = importlib.util.spec_from_file_location(ruta.stem, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main():
    sys.path.insert(0, str(Path(__file__).parent))
    db = obtener_db()
    aplicadas = set(db[COLECCION].distinct("_id"))
    pendientes = [ruta for ruta in migraciones_disponibles() if ruta.stem not in aplicadas]
    if not pendientes:
        print(f"[migrar] nada pendiente ({len(aplicadas)} aplicadas)")
        return
    for ruta in pendientes:
        modulo = cargar(ruta)
        print(f"[migrar] {ruta.stem}: {modulo.DESCRIPCION}")
        modulo.aplicar(db)
        db[COLECCION].insert_one({"_id": ruta.stem, "descripcion": modulo.DESCRIPCION,
                                    "aplicada": datetime.now(timezone.utc)})
    print(f"[migrar] {len(pendientes)} aplicadas")


if __name__ == "__main__":
    main()
