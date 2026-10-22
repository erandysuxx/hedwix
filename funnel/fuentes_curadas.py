"""Curated Sources (pieza 2 de Hedwix): trae noticias de IA de 25 fuentes y las normaliza para el Information Funnel.

La función principal es recolectar(desde). Regresa una lista de items con el formato acordado con el Funnel:
    {id, origin, source, source_type, title, url, published, fetched_at, summary, content, score, extra}

- id: sha1 de la URL normalizada (sin utm_*, fragmento ni "/" final), para deduplicar.
- origin: siempre "curated" (el Email de Diego usa "email").
- source_type: "rss", "api" o "scrape".
- published y fetched_at: ISO 8601 en UTC. Los rankings (OpenRouter top/agénticos, HF trending)
  no tienen fecha propia y usan la hora en que se consultaron.
- summary: resumen corto, máximo 500 caracteres y sin saltos de línea.
- content: el texto más completo que se consiguió, conservando los párrafos. En los newsletters viene completo
  en el feed; en las fuentes de FUENTES_QUE_HAY_QUE_DESCARGAR se baja la página de la nota y se extrae el
  artículo. En papers es el abstract y en modelos la descripción. Si la descarga falla, se queda el texto
  corto que traía la fuente.
- score: popularidad (votos en HF Daily Papers, puntos en Hacker News); más alto es mejor. None si la fuente no tiene.
  En los rankings el lugar va en extra["rank"] (1 es el mejor), no en score.
- extra: datos propios de la fuente. Si la misma URL salió en varias fuentes, extra["also_in"] las lista.

Dependencias: requests y trafilatura (ver requirements.txt).
Uso: .venv/bin/python fuentes_curadas.py [--horas 24] [--solo "Nombre de fuente"]
"""

import argparse
import hashlib
import html
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
import trafilatura


# ============================================================ Configuración

CABECERAS_HTTP = {"User-Agent": "Mozilla/5.0 (ai-news-briefing)"}
SEGUNDOS_MAXIMOS_POR_DESCARGA = 30

# Prefijos de XML que usan los feeds (Atom, Dublin Core, contenido completo y metadatos de arXiv).
ESPACIOS_XML = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# Simon publica también sobre otros temas; nos quedamos con lo que tenga alguna de estas etiquetas.
ETIQUETAS_DE_IA_SIMON = {"ai", "llms", "generative-ai", "ai-agents", "coding-agents", "local-llms"}

# El changelog de GitHub trae de todo (Actions, permisos, etc.); solo pasa lo que mencione IA.
PALABRAS_DE_IA_GITHUB = re.compile(r"\b(AI|LLMs?|MCP)\b|copilot|\bmodels?\b|\bagent", re.IGNORECASE)

# hnrss no hace OR confiable, así que corremos una búsqueda por término y quitamos repetidos.
BUSQUEDAS_HACKER_NEWS = ["AI", "LLM", "GPT", "Claude", "OpenAI", "Anthropic", "Gemini"]
PUNTOS_MINIMOS_HACKER_NEWS = 100
PAUSA_ENTRE_BUSQUEDAS_HN = 3  # segundos; si las búsquedas van seguidas, hnrss empieza a regresar 502

MODELOS_POR_RANKING = 10

# Fuentes cuyo feed o página solo trae una línea de texto: para ellas se descarga cada nota y se extrae el artículo.
# Las demás ya traen el texto completo (newsletters, AWS, GitHub, Simon) o no tienen más texto (papers, modelos).
FUENTES_QUE_HAY_QUE_DESCARGAR = {
    "OpenAI Blog", "Hugging Face Blog", "TechCrunch AI", "Databricks Blog", "Google DeepMind Blog", "Mistral News",
    "Anthropic News", "Meta AI Blog", "Hacker News",
}
DESCARGAS_DE_NOTAS_EN_PARALELO = 8
LIMITE_DE_CONTENIDO = 100_000  # caracteres; las notas más largas que hemos visto andan en 80,000

MESES = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
FECHA_EN_INGLES = re.compile(MESES + r" \d{1,2}, \d{4}")  # "Oct 6, 2026" o "July 09, 2026"


# ============================================================ Herramientas comunes

def descargar(url, intentos=3):
    """Descarga una URL y reintenta si falla (hnrss, por ejemplo, a veces regresa 502)."""
    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.get(url, headers=CABECERAS_HTTP, timeout=SEGUNDOS_MAXIMOS_POR_DESCARGA)
            if respuesta.status_code == 200:
                return respuesta
        except requests.RequestException:
            pass
        if intento < intentos:
            time.sleep(2 * intento)
    raise RuntimeError(f"No se pudo descargar {url}")


def a_iso_utc(fecha):
    """Convierte una fecha a texto ISO 8601 en UTC. Si no trae zona horaria, se asume UTC."""
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc).isoformat(timespec="seconds")


def leer_fecha(texto):
    """Entiende los formatos de fecha que usan nuestras fuentes. Regresa None si no reconoce el texto.

    - RSS:        "Tue, 13 Oct 2026 19:43:07 +0000"
    - Atom y APIs: "2026-10-13T13:32:00+00:00"
    - Páginas HTML: "Oct 6, 2026" o "July 09, 2026"
    """
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        pass
    texto = texto.replace("Sept ", "Sep ")
    for formato in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            pass
    return None


def limpiar_texto(texto, limite=500):
    """Quita etiquetas HTML y espacios de más, y corta el texto a `limite` caracteres."""
    texto = re.sub(r"<[^>]+>", " ", html.unescape(texto or ""))
    return re.sub(r"\s+", " ", texto).strip()[:limite]


def html_a_texto(texto_html, limite=LIMITE_DE_CONTENIDO):
    """Convierte HTML a texto plano conservando los párrafos (a diferencia de limpiar_texto, que deja una sola línea)."""
    texto = re.sub(r"<br\s*/?>|</(?:p|div|h[1-6]|li|blockquote|pre|tr)>", "\n", texto_html or "", flags=re.IGNORECASE)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    lineas = [re.sub(r"[ \t\xa0]+", " ", linea).strip() for linea in texto.splitlines()]
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return texto[:limite]


def normalizar_url(url):
    """Deja la URL en una forma única para que la misma nota con distinto tracking cuente como una sola."""
    partes = urlsplit(url.strip())
    parametros = [(clave, valor) for clave, valor in parse_qsl(partes.query) if not clave.lower().startswith("utm_")]
    ruta = partes.path.rstrip("/") or "/"
    return urlunsplit((partes.scheme.lower(), partes.netloc.lower(), ruta, urlencode(parametros), ""))


def id_de_url(url):
    return hashlib.sha1(normalizar_url(url).encode()).hexdigest()


def nuevo_item(fuente, titulo, url, publicado, resumen="", score=None, extra=None, solo_dia=False, contenido=None):
    """Arma un item con los campos que cada fuente sabe llenar. recolectar() agrega el resto.

    contenido es el texto completo (HTML o texto). Si la fuente no lo trae, se usa el resumen.
    solo_dia=True indica que la fuente da el día pero no la hora (Anthropic, Meta, HF Daily Papers).
    """
    return {
        "source": fuente,
        "title": limpiar_texto(titulo, 300),
        "url": (url or "").strip(),
        "published": a_iso_utc(publicado) if publicado else None,
        "summary": limpiar_texto(resumen or contenido),
        "content": html_a_texto(contenido or resumen),
        "score": score,
        "extra": extra or {},
        "solo_dia": solo_dia,
    }


# ============================================================ Feeds RSS y Atom

def leer_feed(fuente, url, filtro=None):
    """Lee un feed RSS 2.0 o Atom y regresa sus entradas como items.

    filtro(item, entrada_xml) es opcional y regresa True para las entradas que se quedan.
    """
    raiz = ET.fromstring(descargar(url).content.strip())
    items = []

    for entrada in raiz.iter("item"):  # formato RSS 2.0
        fecha = entrada.findtext("pubDate") or entrada.findtext("dc:date", namespaces=ESPACIOS_XML)
        resumen = entrada.findtext("description")
        completo = entrada.findtext("content:encoded", namespaces=ESPACIOS_XML)
        etiquetas = [categoria.text for categoria in entrada.findall("category") if categoria.text]
        item = nuevo_item(fuente, entrada.findtext("title"), entrada.findtext("link"), leer_fecha(fecha), resumen,
                          extra={"tags": etiquetas}, contenido=completo)
        if item["url"] and (filtro is None or filtro(item, entrada)):
            items.append(item)

    for entrada in raiz.findall("atom:entry", ESPACIOS_XML):  # formato Atom
        enlace = ""
        for link in entrada.findall("atom:link", ESPACIOS_XML):
            if link.get("rel", "alternate") == "alternate":
                enlace = link.get("href")
                break
        fecha = (entrada.findtext("atom:published", namespaces=ESPACIOS_XML)
                 or entrada.findtext("atom:updated", namespaces=ESPACIOS_XML))
        resumen = entrada.findtext("atom:summary", namespaces=ESPACIOS_XML)
        completo = entrada.findtext("atom:content", namespaces=ESPACIOS_XML)
        etiquetas = [categoria.get("term") for categoria in entrada.findall("atom:category", ESPACIOS_XML)
                     if categoria.get("term")]
        item = nuevo_item(fuente, entrada.findtext("atom:title", namespaces=ESPACIOS_XML), enlace, leer_fecha(fecha),
                          resumen, extra={"tags": etiquetas}, contenido=completo)
        if item["url"] and (filtro is None or filtro(item, entrada)):
            items.append(item)

    return items


def solo_papers_nuevos(item, entrada_xml):
    """arXiv: solo papers nuevos en su categoría principal.

    El feed también trae "cross" (papers de otra categoría listados aquí, que se repetirían entre
    cs.AI/cs.CL/cs.LG) y "replace"/"replace-cross" (versiones nuevas de papers viejos).
    """
    return entrada_xml.findtext("arxiv:announce_type", namespaces=ESPACIOS_XML) == "new"


def solo_posts_de_ia_simon(item, entrada_xml):
    return bool(set(item["extra"]["tags"]) & ETIQUETAS_DE_IA_SIMON)


def solo_cambios_de_ia_github(item, entrada_xml):
    return bool(PALABRAS_DE_IA_GITHUB.search(item["title"]))


# ============================================================ APIs
# Todas reciben `desde` para tener la misma forma, aunque solo HF Daily Papers lo usa.

def traer_hf_daily_papers(desde):
    """Papers que la comunidad votó en huggingface.co/papers, día por día desde `desde` hasta hoy."""
    items = []
    ids_vistos = set()
    dia = desde.date()
    hoy = datetime.now(timezone.utc).date()
    while dia <= hoy:
        for publicacion in descargar(f"https://huggingface.co/api/daily_papers?date={dia.isoformat()}").json():
            paper = publicacion["paper"]
            if paper["id"] in ids_vistos:
                continue
            ids_vistos.add(paper["id"])
            items.append(nuevo_item(
                "HF Daily Papers",
                paper["title"],
                f"https://huggingface.co/papers/{paper['id']}",
                leer_fecha(paper.get("submittedOnDailyAt") or publicacion.get("publishedAt")),
                paper.get("summary"),
                score=paper.get("upvotes", 0),
                extra={
                    "arxiv": f"https://arxiv.org/abs/{paper['id']}",
                    "github": paper.get("githubRepo"),
                    "org": (paper.get("organization") or {}).get("fullname"),
                },
                solo_dia=True,
            ))
        dia += timedelta(days=1)
    return items


def traer_hacker_news(desde):
    """Historias de HN sobre IA con al menos PUNTOS_MINIMOS_HACKER_NEWS puntos."""
    items_por_hilo = {}  # la URL del hilo de HN identifica a cada historia
    for numero, busqueda in enumerate(BUSQUEDAS_HACKER_NEWS):
        if numero > 0:
            time.sleep(PAUSA_ENTRE_BUSQUEDAS_HN)
        url = f"https://hnrss.org/newest?q={busqueda}&points={PUNTOS_MINIMOS_HACKER_NEWS}"
        try:
            raiz = ET.fromstring(descargar(url).content)
        except (RuntimeError, ET.ParseError) as error:
            print(f"[Hacker News] la búsqueda '{busqueda}' falló: {error}", file=sys.stderr)
            continue

        for entrada in raiz.iter("item"):
            hilo = entrada.findtext("comments")
            if hilo in items_por_hilo:
                continue
            # hnrss pone los puntos y comentarios dentro de la descripción: "Points: 707 ... # Comments: 1033"
            descripcion = html.unescape(entrada.findtext("description") or "")
            puntos = re.search(r"Points: (\d+)", descripcion)
            comentarios = re.search(r"# Comments: (\d+)", descripcion)
            items_por_hilo[hilo] = nuevo_item(
                "Hacker News",
                entrada.findtext("title"),
                entrada.findtext("link"),
                leer_fecha(entrada.findtext("pubDate")),
                score=int(puntos.group(1)) if puntos else 0,
                extra={"hn_url": hilo, "comments": int(comentarios.group(1)) if comentarios else 0},
            )
    return list(items_por_hilo.values())


def modelos_de_openrouter(orden):
    """Lista de modelos de OpenRouter en el orden pedido, sin variantes como ":free" o ":batch"."""
    modelos = descargar(f"https://openrouter.ai/api/v1/models?sort={orden}").json()["data"]
    return [modelo for modelo in modelos if ":" not in modelo["id"]]


def item_de_modelo_openrouter(fuente, modelo, publicado, lugar=None):
    extra = {"model_id": modelo["id"], "context_length": modelo.get("context_length"), "pricing": modelo.get("pricing")}
    if lugar is not None:
        extra["rank"] = lugar
    return nuevo_item(
        fuente,
        modelo["name"],
        f"https://openrouter.ai/{modelo['id']}",
        publicado,
        modelo.get("description"),
        extra=extra,
    )


def ranking_de_openrouter(fuente, orden):
    """Los primeros MODELOS_POR_RANKING de un ranking. extra["rank"] = lugar en el ranking (1 es el mejor)."""
    ahora = datetime.now(timezone.utc)
    modelos = modelos_de_openrouter(orden)[:MODELOS_POR_RANKING]
    return [item_de_modelo_openrouter(fuente, modelo, ahora, lugar)
            for lugar, modelo in enumerate(modelos, start=1)]


def traer_openrouter_top_semanal(desde):
    return ranking_de_openrouter("OpenRouter: top semanal", "top-weekly")


def traer_openrouter_agenticos(desde):
    return ranking_de_openrouter("OpenRouter: agénticos", "agentic-high-to-low")


def traer_openrouter_nuevos(desde):
    """Todos los modelos con su fecha de alta; recolectar() se queda con los recientes."""
    fuente = "OpenRouter: nuevos"
    return [item_de_modelo_openrouter(fuente, modelo, datetime.fromtimestamp(modelo["created"], timezone.utc))
            for modelo in modelos_de_openrouter("newest")]


def traer_hf_trending(desde):
    """Modelos en tendencia en Hugging Face ahora mismo. extra["rank"] = lugar en el ranking (1 es el mejor)."""
    ahora = datetime.now(timezone.utc)
    tendencias = descargar("https://huggingface.co/api/trending?type=model").json()["recentlyTrending"]
    items = []
    for lugar, tendencia in enumerate(tendencias, start=1):
        repo = tendencia["repoData"]
        items.append(nuevo_item(
            "Hugging Face: modelos trending",
            repo["id"],
            f"https://huggingface.co/{repo['id']}",
            ahora,
            extra={
                "rank": lugar,
                "likes": repo.get("likes"),
                "downloads": repo.get("downloads"),
                "pipeline_tag": repo.get("pipeline_tag"),
                "num_parameters": repo.get("numParameters"),
            },
        ))
    return items


# ============================================================ Páginas sin RSS (se leen del HTML)
# Si alguna de estas páginas cambia su diseño, la función va a regresar 0 entradas y recolectar() lo avisa.

def traer_anthropic(desde):
    """anthropic.com/news: cada post es un <a href="/news/..."> con el título, un <time> y a veces un resumen <p>."""
    pagina = descargar("https://www.anthropic.com/news").text
    items = []
    rutas_vistas = set()
    for enlace in re.finditer(r'<a [^>]*href="(/news/[a-z0-9-]+)"[^>]*>(.*?)</a>', pagina, re.DOTALL):
        ruta, contenido = enlace.groups()
        titulo = re.search(r'<(?:h\d|span)[^>]*class="[^"]*[Tt]itle[^"]*"[^>]*>(.*?)</(?:h\d|span)>', contenido,
                           re.DOTALL)
        if ruta in rutas_vistas or not titulo:
            continue
        rutas_vistas.add(ruta)
        fecha = re.search(r"<time[^>]*>(.*?)</time>", contenido, re.DOTALL)
        resumen = re.search(r"<p[^>]*>(.*?)</p>", contenido, re.DOTALL)
        items.append(nuevo_item(
            "Anthropic News",
            titulo.group(1),
            urljoin("https://www.anthropic.com", ruta),
            leer_fecha(limpiar_texto(fecha.group(1))) if fecha else None,
            resumen.group(1) if resumen else "",
            solo_dia=True,
        ))
    return items


def traer_meta(desde):
    """ai.meta.com/blog usa dos tipos de tarjeta, y cada post puede aparecer en las dos:

    - Destacados: un <a> cuyo único contenido es el título; la fecha aparece después.
    - Lista "Blog Posts": el <a> es el botón "Learn More"; el título es el último <h4> antes de él
      y la fecha también va antes.
    """
    pagina = descargar("https://ai.meta.com/blog/").text
    enlaces = list(re.finditer(r'<a [^>]*href="(https://ai\.meta\.com/blog/[a-z0-9-]+/)"[^>]*>(.*?)</a>',
                               pagina, re.DOTALL))
    items_por_url = {}

    # Primero las tarjetas destacadas.
    for enlace in enlaces:
        url, contenido = enlace.groups()
        es_solo_texto = "<" not in contenido and limpiar_texto(contenido)
        if url in items_por_url or not es_solo_texto:
            continue
        texto_siguiente = limpiar_texto(pagina[enlace.end():enlace.end() + 3000], 3000)
        fecha = FECHA_EN_INGLES.search(texto_siguiente)
        items_por_url[url] = nuevo_item("Meta AI Blog", contenido, url, leer_fecha(fecha.group(0)) if fecha else None,
                                        solo_dia=True)

    # Luego los posts que solo salen en la lista.
    for enlace in enlaces:
        url = enlace.group(1)
        if url in items_por_url:
            continue
        html_anterior = pagina[max(0, enlace.start() - 3000):enlace.start()]
        titulos = re.findall(r"<h4[^>]*>(.*?)</h4>", html_anterior, re.DOTALL)
        fechas = FECHA_EN_INGLES.findall(limpiar_texto(html_anterior, 3000))
        if titulos:
            items_por_url[url] = nuevo_item("Meta AI Blog", titulos[-1], url,
                                            leer_fecha(fechas[-1]) if fechas else None, solo_dia=True)

    return list(items_por_url.values())


# ============================================================ Catálogo de fuentes

# Feeds RSS/Atom: nombre -> (url, filtro opcional)
FEEDS = {
    "OpenAI Blog": ("https://openai.com/news/rss.xml", None),
    "Hugging Face Blog": ("https://huggingface.co/blog/feed.xml", None),
    "arXiv cs.AI": ("https://rss.arxiv.org/rss/cs.AI", solo_papers_nuevos),
    "arXiv cs.CL": ("https://rss.arxiv.org/rss/cs.CL", solo_papers_nuevos),
    "arXiv cs.LG": ("https://rss.arxiv.org/rss/cs.LG", solo_papers_nuevos),
    "Last Week in AI": ("https://lastweekin.ai/feed", None),
    "Import AI": ("https://importai.substack.com/feed", None),
    "Latent Space": ("https://www.latent.space/feed", None),
    "The Gradient": ("https://thegradient.pub/rss/", None),
    "Ahead of AI": ("https://magazine.sebastianraschka.com/feed", None),
    "TechCrunch AI": ("https://techcrunch.com/category/artificial-intelligence/feed/", None),
    "AWS ML Blog": ("https://aws.amazon.com/blogs/machine-learning/feed/", None),
    "GitHub Changelog": ("https://github.blog/changelog/feed/", solo_cambios_de_ia_github),
    "Databricks Blog": ("https://www.databricks.com/feed", None),
    "Google DeepMind Blog": ("https://deepmind.google/blog/rss.xml", None),
    "Mistral News": ("https://mistral.ai/news/rss", None),
    "Simon Willison": ("https://simonwillison.net/atom/everything/", solo_posts_de_ia_simon),
}

# Fuentes con lógica propia: nombre -> (función, source_type)
OTRAS_FUENTES = {
    "Hacker News": (traer_hacker_news, "rss"),
    "OpenRouter: top semanal": (traer_openrouter_top_semanal, "api"),
    "OpenRouter: agénticos": (traer_openrouter_agenticos, "api"),
    "OpenRouter: nuevos": (traer_openrouter_nuevos, "api"),
    "Hugging Face: modelos trending": (traer_hf_trending, "api"),
    "HF Daily Papers": (traer_hf_daily_papers, "api"),
    "Anthropic News": (traer_anthropic, "scrape"),
    "Meta AI Blog": (traer_meta, "scrape"),
}

TODAS_LAS_FUENTES = list(FEEDS) + list(OTRAS_FUENTES)


def tipo_de_fuente(nombre):
    return "rss" if nombre in FEEDS else OTRAS_FUENTES[nombre][1]


def traer_fuente(nombre, desde):
    """Corre una fuente. Si falla, lo avisa y regresa una lista vacía para no tumbar a las demás."""
    try:
        if nombre in FEEDS:
            url, filtro = FEEDS[nombre]
            return leer_feed(nombre, url, filtro)
        funcion, _ = OTRAS_FUENTES[nombre]
        return funcion(desde)
    except Exception as error:
        print(f"[{nombre}] ERROR: {error}", file=sys.stderr)
        return []


# ============================================================ Texto completo de las notas

def texto_de_la_nota(url):
    """Descarga la página de una nota y extrae el texto del artículo (sin menús, anuncios ni comentarios).

    Regresa None si la página no se pudo bajar (por ejemplo Reuters responde 401), si no es HTML
    (un PDF o una imagen) o si trafilatura no encontró un artículo en ella (por ejemplo un tweet).
    """
    try:
        respuesta = descargar(url, intentos=1)
    except RuntimeError:
        return None
    if "html" not in respuesta.headers.get("Content-Type", ""):
        return None
    texto = trafilatura.extract(respuesta.text, url=url, include_comments=False)
    return texto[:LIMITE_DE_CONTENIDO] if texto else None


def completar_contenido(items):
    """Para las notas de FUENTES_QUE_HAY_QUE_DESCARGAR, cambia `content` por el texto completo del artículo.

    Si no se puede, se queda el texto corto que traía la fuente y se avisa por stderr.
    """
    por_descargar = [item for item in items if item["source"] in FUENTES_QUE_HAY_QUE_DESCARGAR]
    with ThreadPoolExecutor(max_workers=DESCARGAS_DE_NOTAS_EN_PARALELO) as pool:
        textos = list(pool.map(lambda item: texto_de_la_nota(item["url"]), por_descargar))

    fallidas = 0
    for item, texto in zip(por_descargar, textos):
        if texto and len(texto) > len(item["content"]):
            item["content"] = texto
        elif not texto:
            fallidas += 1
            print(f"[{item['source']}] no se pudo sacar el texto completo de {item['url']}", file=sys.stderr)
    if por_descargar:
        print(f"[texto completo] {len(por_descargar) - fallidas} de {len(por_descargar)} notas descargadas",
              file=sys.stderr)


# ============================================================ Recolección

def es_reciente(item, desde):
    """¿El item se publicó desde `desde`?

    Si la fuente solo da el día (solo_dia), se compara por día. Si no, una nota publicada hoy en la
    tarde quedaría como "hoy 00:00" y en la corrida de mañana ya caería fuera de la ventana. A cambio,
    esos items pueden salir en dos corridas seguidas; el `id` permite descartar el repetido.
    """
    if not item["published"]:
        return False
    publicado = datetime.fromisoformat(item["published"])
    if item["solo_dia"]:
        return publicado.date() >= desde.astimezone(timezone.utc).date()
    return publicado >= desde


def recolectar(desde, solo=None):
    """Corre las fuentes en paralelo y regresa los items publicados desde `desde`, en el formato del Funnel.

    Al final descarga el texto completo de las notas que lo necesitan (ver completar_contenido).

    `desde` es un datetime; si no trae zona horaria, se asume UTC. `solo` es una lista opcional de
    nombres de fuente para correr solo esas.

    Si una fuente falla o no trae ninguna entrada (ni vieja ni nueva), lo avisa por stderr porque
    probablemente se rompió. Que una fuente no tenga nada *reciente* es normal y no se avisa.
    """
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=timezone.utc)
    nombres = solo or TODAS_LAS_FUENTES
    fetched_at = a_iso_utc(datetime.now(timezone.utc))

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(lambda nombre: traer_fuente(nombre, desde), nombres))

    items_por_id = {}
    for nombre, items in zip(nombres, resultados):
        if not items:
            print(f"[{nombre}] ALERTA: 0 entradas, revisar si la fuente cambió", file=sys.stderr)

        for item in items:
            if not es_reciente(item, desde):
                continue

            item_id = id_de_url(item["url"])
            ya_guardado = items_por_id.get(item_id)
            if ya_guardado:
                # La misma URL vino de otra fuente: nos quedamos con la primera y anotamos la otra.
                otras_fuentes = ya_guardado["extra"].setdefault("also_in", [])
                if item["source"] != ya_guardado["source"] and item["source"] not in otras_fuentes:
                    otras_fuentes.append(item["source"])
                continue

            items_por_id[item_id] = {
                "id": item_id,
                "origin": "curated",
                "source": item["source"],
                "source_type": tipo_de_fuente(nombre),
                "title": item["title"],
                "url": item["url"],
                "published": item["published"],
                "fetched_at": fetched_at,
                "summary": item["summary"],
                "content": item["content"],
                "score": item["score"],
                "extra": item["extra"],
            }

    items = list(items_por_id.values())
    completar_contenido(items)
    return items


def main():
    parser = argparse.ArgumentParser(description="Trae noticias de IA de las fuentes curadas y las imprime como JSON.")
    parser.add_argument("--horas", type=int, default=24, help="qué tan atrás buscar (default: 24)")
    parser.add_argument("--solo", action="append", choices=TODAS_LAS_FUENTES,
                        help="correr solo esta fuente (se puede repetir)")
    args = parser.parse_args()

    desde = datetime.now(timezone.utc) - timedelta(hours=args.horas)
    json.dump(recolectar(desde, args.solo), sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
