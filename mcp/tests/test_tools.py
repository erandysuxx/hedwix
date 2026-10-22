"""Pruebas del MCP contra la DB local, con el cliente en memoria de FastMCP (sin levantar el servidor HTTP).

Uso (desde la raíz del repo): docker compose run --rm --no-deps mcp pytest -v
Necesitan noticias en la DB (por ejemplo, las de ejemplo con cargar_jsonl.py).
"""

import os

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pymongo import MongoClient
from pymongo.errors import OperationFailure

import servidor

TOOLS = {"noticias_recientes", "buscar_noticias", "noticias_populares", "obtener_noticia", "listar_fuentes",
         "digest_del_dia"}
CAMPOS_DE_LISTA = {"id", "origin", "source", "source_type", "title", "url", "published", "fetched_at", "summary",
                   "score", "extra", "largo_content"}


@pytest.fixture
async def cliente():
    async with Client(transport=servidor.mcp) as cliente:
        yield cliente


async def llamar(cliente, tool, **argumentos):
    return (await cliente.call_tool(tool, argumentos)).data


async def test_estan_las_tools_y_son_de_solo_lectura(cliente):
    tools = await cliente.list_tools()
    assert {tool.name for tool in tools} == TOOLS
    for tool in tools:
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.description, f"{tool.name} necesita docstring: el agente escoge la tool por ella"


async def test_noticias_recientes(cliente):
    datos = await llamar(cliente, "noticias_recientes", horas=720, limite=5)
    assert 0 < datos["total"] == len(datos["noticias"]) <= 5
    for noticia in datos["noticias"]:
        assert set(noticia) == CAMPOS_DE_LISTA            # sin `content`: las listas no traen el texto completo
        assert not noticia["source"].startswith("arXiv")  # arXiv y rankings quedan fuera por default
        assert noticia["source"] not in servidor.RANKINGS
    fechas = [noticia["published"] for noticia in datos["noticias"]]
    assert fechas == sorted(fechas, reverse=True)


async def test_noticias_recientes_puede_incluir_arxiv_o_pedir_fuentes(cliente):
    datos = await llamar(cliente, "noticias_recientes", horas=720, limite=50, incluir_arxiv=True, incluir_rankings=True)
    assert datos["total"] == 50
    solo_hn = await llamar(cliente, "noticias_recientes", horas=720, fuentes=["Hacker News"])
    assert solo_hn["total"] > 0 and {n["source"] for n in solo_hn["noticias"]} == {"Hacker News"}


@pytest.mark.parametrize("argumentos", [{"limite": 0}, {"limite": 51}, {"horas": 0}, {"horas": 721}])
async def test_limites_fuera_de_rango_se_rechazan(cliente, argumentos):
    with pytest.raises(ToolError):
        await llamar(cliente, "noticias_recientes", **argumentos)


async def test_buscar_noticias(cliente):
    datos = await llamar(cliente, "buscar_noticias", texto="agents", limite=5)
    assert datos["total"] > 0
    assert all(set(n) == CAMPOS_DE_LISTA for n in datos["noticias"])
    filtrada = await llamar(cliente, "buscar_noticias", texto="model", fuentes=["Hacker News"], limite=50)
    assert {n["source"] for n in filtrada["noticias"]} <= {"Hacker News"}


async def test_noticias_populares_ordenadas_por_score(cliente):
    datos = await llamar(cliente, "noticias_populares", horas=720, limite=10)
    puntajes = [n["score"] for n in datos["noticias"]]
    assert puntajes and None not in puntajes and puntajes == sorted(puntajes, reverse=True)


async def test_obtener_noticia(cliente):
    una = (await llamar(cliente, "noticias_recientes", horas=720, limite=1))["noticias"][0]
    completa = await llamar(cliente, "obtener_noticia", id=una["id"])
    assert completa["id"] == una["id"] and "content" in completa
    assert len(completa["content"]) <= servidor.LIMITE_DE_CONTENIDO
    assert completa["content_cortado"] == (una["largo_content"] > servidor.LIMITE_DE_CONTENIDO)


async def test_obtener_noticia_corta_las_muy_largas(cliente):
    larga = servidor.db.noticias.find_one({"$expr": {"$gt": [{"$strLenCP": "$content"}, servidor.LIMITE_DE_CONTENIDO]}})
    if larga is None:
        pytest.skip("no hay noticias de más de 20,000 caracteres en la DB")
    completa = await llamar(cliente, "obtener_noticia", id=larga["_id"])
    assert completa["content_cortado"] is True and len(completa["content"]) == servidor.LIMITE_DE_CONTENIDO


@pytest.mark.parametrize("id_", ["f" * 40, "no-es-un-sha1"])
async def test_obtener_noticia_con_id_malo_da_error_claro(cliente, id_):
    with pytest.raises(ToolError):
        await llamar(cliente, "obtener_noticia", id=id_)


async def test_listar_fuentes(cliente):
    fuentes = (await llamar(cliente, "listar_fuentes"))["fuentes"]
    assert sum(f["noticias"] for f in fuentes) == servidor.db.noticias.count_documents({})
    assert [f["noticias"] for f in fuentes] == sorted((f["noticias"] for f in fuentes), reverse=True)


async def test_digest_del_dia_sin_digest_no_falla(cliente):
    datos = await llamar(cliente, "digest_del_dia", fecha="1999-01-01")
    assert datos["encontrado"] is False
    with pytest.raises(ToolError):
        await llamar(cliente, "digest_del_dia", fecha="ayer")


def test_el_usuario_del_mcp_no_puede_escribir():
    db = MongoClient(os.environ["MONGODB_URI"]).get_default_database()
    with pytest.raises(OperationFailure) as error:
        db.noticias.insert_one({"_id": "prueba-de-escritura"})
    assert error.value.code == 13  # Unauthorized
