"""Agent - Dispatch (pieza 5 de Hedwix): escoge las noticias más importantes del día y escribe el digest de WhatsApp.

Pasos de cada corrida:
1. Leer: las noticias que guardó el Funnel en las últimas horas (por `fetched_at`, no por `published`: Anthropic, Meta
   y HF Daily Papers solo dan el día, así que una nota de ayer guardada hoy quedaría fuera). Con MONGODB_URI, de la
   colección `noticias` de la DB de Egon; sin ella, de funnel/datos/noticias.jsonl.
2. Seleccionar: Claude lee título y resumen de todas y escoge las NOTICIAS_POR_DIGEST más importantes.
3. Escribir: Claude lee el texto completo solo de las seleccionadas y redacta el mensaje en español.
4. Guardar: el digest (mensaje + noticias usadas), con la fecha como llave. Con MONGODB_URI, en la colección
   `digests` (migración db/migraciones/003_digests.py); sin ella, en datos/digests/AAAA-MM-DD.json.
5. Enviar: por ahora solo se imprime. Cuando exista Twilio (pieza 6), solo hay que cambiar enviar().

Usa los créditos de API de Anthropic del equipo: la llave va en la variable de entorno ANTHROPIC_API_KEY.
Uso (desde dispatch/): .venv/bin/python dispatch.py [--horas 24] [--entrada ../funnel/datos/noticias.jsonl]
     MONGODB_URI="mongodb://usuario:clave@127.0.0.1:27017/hedwix?authSource=hedwix" .venv/bin/python dispatch.py
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "funnel"))  # funnel.py vive en funnel/
import funnel  # noqa: E402


# ============================================================ Configuración

MODELO = "claude-opus-5-5"
NOTICIAS_POR_DIGEST = 5
LIMITE_DEL_MENSAJE = 1600  # caracteres; es lo máximo que Twilio deja mandar en un mensaje de WhatsApp
INTENTOS_PARA_ACORTAR = 2
ZONA_HORARIA = ZoneInfo("America/Mexico_City")  # la fecha del digest es la del día en México

CARPETA_DE_DIGESTS = Path(__file__).parent / "datos" / "digests"

# Si un clasificador de seguridad rechaza la petición, la API la vuelve a correr en el modelo que Anthropic recomienda.
OPCIONES_DE_LA_API = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

INSTRUCCIONES_PARA_SELECCIONAR = f"""Eres el editor de Hedwix, un digest diario de noticias de inteligencia artificial que llega por WhatsApp
a un equipo de datos e IA en México y a sus líderes.

Vas a recibir la lista de noticias del día. Cada una trae un índice, la fuente, el título, un resumen corto y, si la
fuente lo tiene, un puntaje de popularidad.

Escoge las {NOTICIAS_POR_DIGEST} noticias más importantes para ese público. Prioriza lanzamientos y cambios que afecten
cómo se construye o se usa la IA (modelos nuevos, plataformas, herramientas, precios, regulación) sobre papers
académicos de nicho. Si varias noticias hablan de lo mismo, escoge solo una: la de la fuente más directa. Para cada una
explica en una frase por qué importa."""

INSTRUCCIONES_PARA_ESCRIBIR = f"""Eres el editor de Hedwix, un digest diario de noticias de inteligencia artificial que llega por WhatsApp
a un equipo de datos e IA en México y a sus líderes.

Vas a recibir las noticias que ya se escogieron para hoy, con su texto completo. Escribe el mensaje del digest:

- En español, claro y directo, aunque las notas estén en inglés.
- Una línea de saludo con la fecha y luego las noticias en el orden en que llegan, numeradas.
- Por cada noticia: un título corto en *negritas*, una o dos frases sobre qué pasó y por qué importa, y el link tal cual.
- Usa solo el formato de WhatsApp (*negritas*, _cursivas_). Nada de Markdown con #, ** ni [texto](link).
- No inventes datos que no estén en las notas.
- El mensaje completo debe medir como máximo {LIMITE_DEL_MENSAJE} caracteres, contando los links.

Responde solo con el texto del mensaje."""

ESQUEMA_DE_SELECCION = {
    "type": "object",
    "properties": {
        "seleccion": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indice": {"type": "integer"},
                    "por_que": {"type": "string"},
                },
                "required": ["indice", "por_que"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["seleccion"],
    "additionalProperties": False,
}


# ============================================================ Lectura
# Con MONGODB_URI se lee de MongoDB; sin ella, del archivo JSONL del Funnel.

def leer_noticias(archivo, desde):
    """Las noticias que el Funnel guardó desde la fecha indicada."""
    coleccion = funnel.coleccion_de_noticias()
    if coleccion is not None:
        return [{"id": documento.pop("_id"), **documento} for documento in coleccion.find({"fetched_at": {"$gte": desde}})]
    if not archivo.exists():
        return []
    noticias = []
    with archivo.open(encoding="utf-8") as lineas:
        for linea in lineas:
            if linea.strip():
                noticia = json.loads(linea)
                if datetime.fromisoformat(noticia["fetched_at"]) >= desde:
                    noticias.append(noticia)
    return noticias


# ============================================================ Claude

def preguntar_a_claude(cliente, instrucciones, mensajes, **opciones):
    """Hace una petición y regresa la respuesta completa. Falla si Claude se negó o se cortó."""
    respuesta = cliente.beta.messages.create(
        model=MODELO,
        max_tokens=16000,
        system=instrucciones,
        messages=mensajes,
        output_config={"effort": "medium", **opciones.pop("output_config", {})},
        **OPCIONES_DE_LA_API,
        **opciones,
    )
    print(f"[dispatch] {respuesta.model}: {respuesta.usage.input_tokens} tokens de entrada,"
          f" {respuesta.usage.output_tokens} de salida", file=sys.stderr)
    if respuesta.stop_reason == "refusal":
        raise RuntimeError(f"Claude se negó a responder: {respuesta.stop_details}")
    if respuesta.stop_reason == "max_tokens":
        raise RuntimeError("La respuesta de Claude se cortó por max_tokens")
    return respuesta


def texto_de(respuesta):
    return "".join(bloque.text for bloque in respuesta.content if bloque.type == "text").strip()


def seleccionar(cliente, noticias):
    """Regresa las noticias más importantes, cada una con el por qué de Claude en "por_que"."""
    lista = "\n\n".join(
        f"[{indice}] {noticia['source']} | {noticia['title']}"
        + (f" | puntaje {noticia['score']:g}" if noticia["score"] is not None else "")
        + (f"\n{noticia['summary']}" if noticia["summary"] else "")
        for indice, noticia in enumerate(noticias)
    )
    respuesta = preguntar_a_claude(
        cliente, INSTRUCCIONES_PARA_SELECCIONAR, [{"role": "user", "content": lista}],
        output_config={"format": {"type": "json_schema", "schema": ESQUEMA_DE_SELECCION}},
    )

    seleccionadas = []
    for elegida in json.loads(texto_de(respuesta))["seleccion"]:
        indice = elegida["indice"]
        if not 0 <= indice < len(noticias):
            print(f"[dispatch] Claude escogió un índice que no existe: {indice}", file=sys.stderr)
        elif all(noticia["id"] != noticias[indice]["id"] for noticia in seleccionadas):
            seleccionadas.append({**noticias[indice], "por_que": elegida["por_que"]})
    if len(seleccionadas) != NOTICIAS_POR_DIGEST:
        print(f"[dispatch] se esperaban {NOTICIAS_POR_DIGEST} noticias y Claude escogió {len(seleccionadas)}",
              file=sys.stderr)
    return seleccionadas[:NOTICIAS_POR_DIGEST]


def escribir(cliente, seleccionadas, fecha):
    """Regresa el texto del mensaje de WhatsApp. Si se pasa del límite, le pide a Claude que lo acorte."""
    notas = "\n\n".join(
        f"<noticia numero=\"{numero}\">\nFuente: {noticia['source']}\nTítulo: {noticia['title']}\n"
        f"Link: {noticia['url']}\nPor qué se escogió: {noticia['por_que']}\n\n{noticia['content'] or noticia['summary']}"
        f"\n</noticia>"
        for numero, noticia in enumerate(seleccionadas, start=1)
    )
    mensajes = [{"role": "user", "content": f"Fecha del digest: {fecha}\n\n{notas}"}]

    for _ in range(1 + INTENTOS_PARA_ACORTAR):
        respuesta = preguntar_a_claude(cliente, INSTRUCCIONES_PARA_ESCRIBIR, mensajes)
        mensaje = texto_de(respuesta)
        if len(mensaje) <= LIMITE_DEL_MENSAJE:
            return mensaje
        print(f"[dispatch] el mensaje mide {len(mensaje)} caracteres; se le pide a Claude que lo acorte",
              file=sys.stderr)
        mensajes += [
            {"role": "assistant", "content": respuesta.content},
            {"role": "user", "content": f"Mide {len(mensaje)} caracteres y el máximo es {LIMITE_DEL_MENSAJE}."
                                        " Acórtalo sin quitar noticias ni links. Responde solo con el mensaje."},
        ]
    raise RuntimeError(f"Claude no logró dejar el mensaje en {LIMITE_DEL_MENSAJE} caracteres")


# ============================================================ Salida

def guardar_digest(fecha, mensaje, seleccionadas, carpeta=CARPETA_DE_DIGESTS):
    """Guarda el digest del día con la fecha como llave, en la DB o en un JSON. Si ya había uno de ese día, lo
    reemplaza. Regresa dónde quedó."""
    generado_at = datetime.now(timezone.utc)
    digest = {
        "modelo": MODELO,
        "mensaje": mensaje,
        "noticias": [{campo: noticia[campo] for campo in ("id", "source", "title", "url", "por_que")}
                     for noticia in seleccionadas],
    }
    coleccion = funnel.coleccion_de_noticias()
    if coleccion is not None:
        coleccion.database["digests"].replace_one({"_id": fecha}, {"generado_at": generado_at, **digest}, upsert=True)
        return f"MongoDB (digests, _id {fecha})"
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"{fecha}.json"
    digest = {"fecha": fecha, "generado_at": generado_at.isoformat(timespec="seconds"), **digest}
    archivo.write_text(json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return archivo


def enviar(mensaje):
    """Por ahora solo imprime el mensaje. Aquí se conectará Twilio."""
    print(mensaje)


# ============================================================ Corrida

def correr_dispatch(desde, archivo=funnel.ARCHIVO_DE_SALIDA):
    """Hace una corrida completa y regresa el mensaje enviado, o None si no hubo noticias."""
    noticias = leer_noticias(archivo, desde)
    origen = "MongoDB" if funnel.coleccion_de_noticias() is not None else archivo
    print(f"[dispatch] {len(noticias)} noticias desde {desde.isoformat(timespec='minutes')} en {origen}",
          file=sys.stderr)
    if not noticias:
        return None

    cliente = anthropic.Anthropic()
    fecha = datetime.now(ZONA_HORARIA).date().isoformat()
    seleccionadas = seleccionar(cliente, noticias)
    mensaje = escribir(cliente, seleccionadas, fecha)
    print(f"[dispatch] digest guardado en {guardar_digest(fecha, mensaje, seleccionadas)}"
          f" ({len(mensaje)} caracteres)", file=sys.stderr)
    enviar(mensaje)
    return mensaje


def main():
    parser = argparse.ArgumentParser(description="Escoge las noticias más importantes y escribe el digest del día.")
    parser.add_argument("--horas", type=int, default=24, help="qué tan atrás buscar noticias que guardó el Funnel (default: 24)")
    parser.add_argument("--entrada", type=Path, default=funnel.ARCHIVO_DE_SALIDA,
                        help=f"archivo JSONL del Funnel (default: {funnel.ARCHIVO_DE_SALIDA})")
    args = parser.parse_args()

    desde = datetime.now(timezone.utc) - timedelta(hours=args.horas)
    correr_dispatch(desde, args.entrada)


if __name__ == "__main__":
    main()
