"""Lee los sitemaps de un sitio (los que declara robots.txt y /sitemap.xml)."""

import gzip
import logging

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from docubot.red.cliente import Cliente, ErrorRed

log = logging.getLogger("docubot.sitemap")

MAX_ARCHIVOS = 10
MAX_URLS = 5000
MAX_BYTES = 20 * 1024 * 1024


def _local(etiqueta: str) -> str:
    return etiqueta.rsplit("}", 1)[-1]


def interpretar(contenido: bytes) -> tuple[list[str], list[str]]:
    """(urls de páginas, urls de otros sitemaps) de un sitemap XML (o .gz)."""
    if contenido[:2] == b"\x1f\x8b":
        try:
            contenido = gzip.decompress(contenido)
        except OSError:
            return [], []
    try:
        raiz = ElementTree.fromstring(contenido)
    except (ElementTree.ParseError, DefusedXmlException, ValueError):
        return [], []
    urls, hijos = [], []
    destino = hijos if _local(raiz.tag) == "sitemapindex" else urls
    for nodo in raiz.iter():
        if _local(nodo.tag) == "loc" and nodo.text and nodo.text.strip():
            destino.append(nodo.text.strip())
    return urls, hijos


async def leer(cliente: Cliente, origen: str, declarados: list[str]) -> list[str]:
    """Todas las URLs de los sitemaps del sitio, con límites de archivos y de URLs."""
    pendientes = list(dict.fromkeys(declarados or [f"{origen}/sitemap.xml"]))
    vistos: set[str] = set()
    urls: list[str] = []
    while pendientes and len(vistos) < MAX_ARCHIVOS and len(urls) < MAX_URLS:
        url = pendientes.pop(0)
        if url in vistos:
            continue
        vistos.add(url)
        try:
            r = await cliente.obtener(url, max_bytes=MAX_BYTES)
        except ErrorRed as error:
            log.debug("sitemap %s: %s", url, error)
            continue
        if r.status_code != 200:
            continue
        paginas, hijos = interpretar(r.content)
        urls.extend(paginas[: MAX_URLS - len(urls)])
        pendientes.extend(h for h in hijos if h not in vistos)
    return urls
