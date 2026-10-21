"""Ejemplos de las consultas que harán el MCP y el agent.

Uso: docker compose exec app python consultas.py [--buscar "agent"]
"""

import argparse

from hedwix_db import obtener_db
from hedwix_db.noticias import buscar, mas_populares, recientes


def mostrar(titulo, items):
    print(f"\n== {titulo} ({len(items)})")
    for item in items:
        score = f" [{item['score']}]" if item["score"] is not None else ""
        print(f"  {item['published'][:10]}  {item['source']:<24.24} {item['title'][:70]}{score}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--buscar", default="agent")
    args = parser.parse_args()
    db = obtener_db()

    print("Noticias por fuente:")
    for fila in db.noticias.aggregate([{"$group": {"_id": "$source", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]):
        print(f"  {fila['n']:>5}  {fila['_id']}")

    mostrar("10 más recientes", recientes(db, limite=10))
    mostrar("Hacker News", recientes(db, fuentes=["Hacker News"], limite=5))
    mostrar("Más populares", mas_populares(db, limite=5))
    mostrar(f"Búsqueda: {args.buscar!r}", buscar(db, args.buscar, limite=5))


if __name__ == "__main__":
    main()
