"""MCP de Hedwix: deja que un agente consulte las noticias de IA guardadas en la DB. Sólo lectura.

Tools: noticias_recientes, buscar_noticias, noticias_populares, obtener_noticia, listar_fuentes, digest_del_dia.
Las consultas son las de db/hedwix_db; aquí sólo se ajusta lo que recibe el agente (sin el texto completo en las
listas, límites de tamaño, fechas en ISO).

Uso: MONGODB_URI=... python servidor.py   -> HTTP en 0.0.0.0:8000, MCP en /mcp y /health para revisarlo.
La URI debe ser la del usuario de sólo lectura hedwix_mcp (ver db/scripts/crear_usuario_mcp.sh).
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))  # hedwix_db vive en db/
from hedwix_db import obtener_db  # noqa: E402
from hedwix_db.digests import digest  # noqa: E402
from hedwix_db.noticias import a_item, buscar, mas_populares, por_fuente, recientes  # noqa: E402

LIMITE_DE_CONTENIDO = 20_000  # caracteres de `content` que regresa obtener_noticia
# Rankings sin fecha propia: su `published` es la hora de la consulta, así que siempre parecen lo más nuevo
RANKINGS = {"OpenRouter: top semanal", "OpenRouter: agénticos", "Hugging Face: modelos trending"}
ARXIV = re.compile(r"^arXiv")  # arXiv cs.AI, cs.CL y cs.LG
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": False}

Horas = Annotated[int, Field(ge=1, le=720, description="Qué tan atrás buscar, en horas (máximo 720 = 30 días)")]
Limite = Annotated[int, Field(ge=1, le=50, description="Cuántas noticias regresar (máximo 50)")]
Fuentes = Annotated[list[str] | None, Field(description="Sólo estas fuentes, con el nombre exacto de listar_fuentes")]

mcp = FastMCP(
    "hedwix",
    instructions=(
        "Noticias de inteligencia artificial que Hedwix junta cada día de 25 fuentes: blogs de laboratorios "
        "(OpenAI, Anthropic, DeepMind, Meta, Mistral…), newsletters, Hacker News, papers (arXiv, HF Daily Papers) "
        "y rankings de modelos (OpenRouter, Hugging Face). Las listas traen el resumen; usa obtener_noticia para "
        "leer el texto completo de una. Cita siempre la url de las noticias que uses."
    ),
)
db = obtener_db()


def resumida(item):
    """Una noticia para listas: sin el texto completo, que puede medir hasta 100,000 caracteres."""
    contenido = item.pop("content")
    return {**item, "largo_content": len(contenido)}


def hace(horas):
    return datetime.now(timezone.utc) - timedelta(hours=horas)


@mcp.tool(annotations=SOLO_LECTURA)
def noticias_recientes(horas: Horas = 24, fuentes: Fuentes = None, limite: Limite = 20,
                       incluir_arxiv: bool = False, incluir_rankings: bool = False) -> dict:
    """Las noticias publicadas en las últimas `horas`, de la más nueva a la más vieja.

    Por default deja fuera dos cosas que taparían a las demás:
    - arXiv: ~80% del volumen, cientos de papers al día (incluir_arxiv=True para verlos).
    - Rankings de modelos (OpenRouter top semanal y agénticos, HF trending): se guardan con la hora de la consulta, así que siempre saldrían primero (incluir_rankings=True para verlos).
    Si se pasan `fuentes`, se usan tal cual y estos dos filtros no aplican.
    """
    # Se excluye en el filtro de la consulta (que usa el índice por `published`), sin leer antes toda la colección
    excluir = ([] if incluir_arxiv else [ARXIV]) + ([] if incluir_rankings else sorted(RANKINGS))
    noticias = [resumida(n) for n in recientes(db, desde=hace(horas), fuentes=fuentes, excluir_fuentes=excluir,
                                               limite=limite)]
    return {"noticias": noticias, "total": len(noticias)}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_noticias(texto: Annotated[str, Field(min_length=2, description="Palabras a buscar (en inglés funciona mejor)")],
                    limite: Limite = 10, fuentes: Fuentes = None, horas: Horas | None = None) -> dict:
    """Busca noticias por texto en título, resumen y contenido, de la más relevante a la menos.

    Las notas están casi todas en inglés: "agents" encuentra más que "agentes". Incluye arXiv.
    """
    desde = hace(horas) if horas else None
    noticias = [resumida(n) for n in buscar(db, texto, limite=limite, fuentes=fuentes, desde=desde)]
    return {"noticias": noticias, "total": len(noticias)}


@mcp.tool(annotations=SOLO_LECTURA)
def noticias_populares(horas: Horas = 72, limite: Limite = 10) -> dict:
    """Las noticias con más votos o puntos (sólo Hacker News y HF Daily Papers tienen `score`)."""
    noticias = [resumida(n) for n in mas_populares(db, desde=hace(horas), limite=limite)]
    return {"noticias": noticias, "total": len(noticias)}


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_noticia(id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$", description="El `id` de una noticia")]) -> dict:
    """Una noticia completa, con su texto (`content`). Si mide más de 20,000 caracteres se corta y content_cortado=True."""
    documento = db.noticias.find_one({"_id": id})
    if documento is None:
        raise ToolError(f"No hay ninguna noticia con id {id}")
    item = a_item(documento)
    cortado = len(item["content"]) > LIMITE_DE_CONTENIDO
    return {**item, "content": item["content"][:LIMITE_DE_CONTENIDO], "content_cortado": cortado}


@mcp.tool(annotations=SOLO_LECTURA)
def listar_fuentes() -> dict:
    """Las fuentes que hay en la DB, con cuántas noticias tiene cada una y la fecha de la más reciente."""
    return {"fuentes": por_fuente(db)}


@mcp.tool(annotations=SOLO_LECTURA)
def digest_del_dia(fecha: Annotated[str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$",
                                                      description="AAAA-MM-DD (fecha de México); sin ella, el más reciente")] = None) -> dict:
    """El digest diario que escribió el Dispatch: el mensaje de WhatsApp y las noticias que escogió."""
    encontrado = digest(db, fecha)
    if encontrado is None:
        return {"encontrado": False, "mensaje": f"No hay digest{' del ' + fecha if fecha else ''} todavía"}
    return {"encontrado": True, **encontrado}


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Para revisar que el servidor y la DB respondan. No pasa por la autenticación del MCP."""
    try:
        db.command("ping")
    except Exception as error:
        return JSONResponse({"status": "error", "db": str(error)}, status_code=503)
    return JSONResponse({"status": "ok", "db": db.name})


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000, show_banner=False)
