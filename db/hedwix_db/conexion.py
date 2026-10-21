import os

from dotenv import load_dotenv
from pymongo import MongoClient


def obtener_db():
    """La base indicada en MONGODB_URI (la ruta de la URI, por ejemplo /hedwix).

    Dentro de Docker la variable viene del compose; fuera de Docker se lee del archivo .env.
    """
    load_dotenv()
    cliente = MongoClient(os.environ["MONGODB_URI"], tz_aware=True)
    return cliente.get_default_database()
