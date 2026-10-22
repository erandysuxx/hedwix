"""Prueba del Dispatch con la suscripción de Claude Code (`claude -p`) en vez de la API, mientras llega la llave.

Usa los mismos prompts, modelo, esfuerzo y validaciones de dispatch.py; solo cambia preguntar_a_claude() por una llamada
a `claude -p` sin herramientas. No prueba la llamada a la API en sí (llave, fallbacks), y no guarda el digest.
Deja fuera arXiv para gastar menos. Cuenta contra el límite de uso de tu plan de Claude.

Uso (desde dispatch/): .venv/bin/python probar_con_claude_code.py [--horas 24] [--entrada ../funnel/datos/noticias.jsonl]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import dispatch
import funnel  # dispatch ya agregó funnel/ al sys.path

# Carpeta vacía para correr `claude -p`, así no carga la memoria ni el CLAUDE.md de este proyecto
CARPETA_AISLADA = tempfile.mkdtemp(prefix="hedwix-prueba-")
uso_total = {"tokens": 0, "costo_usd": 0.0}


def como_texto(contenido):
    if isinstance(contenido, str):
        return contenido
    return "".join(bloque.text for bloque in contenido if bloque.type == "text")


def preguntar_con_claude_code(cliente, instrucciones, mensajes, **opciones):
    """Lo mismo que dispatch.preguntar_a_claude, pero con `claude -p`. Los turnos anteriores van en un solo prompt."""
    if len(mensajes) == 1:
        prompt = como_texto(mensajes[0]["content"])
    else:
        prompt = "\n\n".join(
            f"<{'tu_respuesta_anterior' if mensaje['role'] == 'assistant' else 'usuario'}>\n"
            f"{como_texto(mensaje['content'])}\n</{'tu_respuesta_anterior' if mensaje['role'] == 'assistant' else 'usuario'}>"
            for mensaje in mensajes
        )
    esquema = opciones.get("output_config", {}).get("format", {}).get("schema")

    comando = ["claude", "-p", "--model", dispatch.MODELO, "--effort", "medium", "--system-prompt", instrucciones,
               "--tools", "", "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"]
    if esquema:
        comando += ["--json-schema", json.dumps(esquema)]
    salida = subprocess.run(comando, input=prompt, capture_output=True, text=True, cwd=CARPETA_AISLADA, timeout=900)
    if salida.returncode != 0:
        raise RuntimeError(f"claude -p falló ({salida.returncode}): {salida.stderr.strip() or salida.stdout[:500]}")
    resultado = json.loads(salida.stdout)
    if resultado.get("is_error"):
        raise RuntimeError(f"claude -p regresó un error: {resultado.get('result')}")

    uso = resultado["usage"]
    tokens = sum(uso.get(campo, 0) for campo in ("input_tokens", "cache_creation_input_tokens",
                                                   "cache_read_input_tokens", "output_tokens"))
    uso_total["tokens"] += tokens
    uso_total["costo_usd"] += resultado.get("total_cost_usd", 0)
    print(f"[prueba] claude -p: {tokens:,} tokens, {resultado['duration_ms'] / 1000:.0f} s", file=sys.stderr)

    texto = json.dumps(resultado["structured_output"]) if esquema else resultado["result"]
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=texto)])


def main():
    parser = argparse.ArgumentParser(description="Prueba el Dispatch con Claude Code, sin la llave de API.")
    parser.add_argument("--horas", type=int, default=24, help="qué tan atrás buscar noticias que guardó el Funnel (default: 24)")
    parser.add_argument("--entrada", type=Path, default=funnel.ARCHIVO_DE_SALIDA,
                        help=f"archivo JSONL del Funnel, si no hay MONGODB_URI (default: {funnel.ARCHIVO_DE_SALIDA})")
    args = parser.parse_args()

    desde = datetime.now(timezone.utc) - timedelta(hours=args.horas)
    todas = dispatch.leer_noticias(args.entrada, desde)
    noticias = [noticia for noticia in todas if not noticia["source"].startswith("arXiv")]
    print(f"[prueba] {len(noticias)} noticias ({len(todas) - len(noticias)} de arXiv fuera)", file=sys.stderr)
    if not noticias:
        return

    dispatch.preguntar_a_claude = preguntar_con_claude_code
    fecha = datetime.now(dispatch.ZONA_HORARIA).date().isoformat()
    seleccionadas = dispatch.seleccionar(None, noticias)
    mensaje = dispatch.escribir(None, seleccionadas, fecha)

    print("\n=== Noticias escogidas")
    for numero, noticia in enumerate(seleccionadas, start=1):
        print(f"{numero}. [{noticia['source']}] {noticia['title']}\n   {noticia['por_que']}")
    print(f"\n=== Mensaje ({len(mensaje)} de {dispatch.LIMITE_DEL_MENSAJE} caracteres)\n{mensaje}")
    print(f"\n[prueba] total: {uso_total['tokens']:,} tokens; por API costaría ~${uso_total['costo_usd']:.2f} USD",
          file=sys.stderr)


if __name__ == "__main__":
    main()
