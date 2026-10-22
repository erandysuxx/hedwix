"""Colección `digests`: el mensaje diario que escribe el Agent-Dispatch (migración 003_digests).

`_id` es la fecha del digest en México (AAAA-MM-DD).
"""

from pymongo import DESCENDING


def digest(db, fecha=None):
    """El digest de una fecha, o el más reciente si no se da. None si no hay (o si la colección aún no existe)."""
    documento = (db.digests.find_one({"_id": fecha}) if fecha
                 else db.digests.find_one(sort=[("_id", DESCENDING)]))
    if documento is None:
        return None
    return {"fecha": documento["_id"], **{campo: valor for campo, valor in documento.items() if campo != "_id"},
            "generado_at": documento["generado_at"].isoformat(timespec="seconds")}
