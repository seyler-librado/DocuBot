"""Enlaces: extraerlos del HTML y decidir qué son (documento, página, red social...)."""

import mimetypes
import re
from dataclasses import dataclass
from email.message import Message
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

from docubot.filtros.dominios import coincide
from docubot.red.urls import host_de

REDES_SOCIALES = (
    "facebook.com",
    "fb.com",
    "fb.me",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "linkedin.com",
    "wa.me",
    "whatsapp.com",
    "t.me",
    "threads.net",
    "pinterest.com",
    "flickr.com",
)
# servicios donde un "dominio en venta" o estacionado termina
ESTACIONADOS = (
    "sedoparking.com",
    "parkingcrew.net",
    "bodis.com",
    "above.com",
    "dan.com",
    "afternic.com",
    "hugedomains.com",
    "godaddy.com",
    "sedo.com",
    "parklogic.com",
)
TEXTO_ESTACIONADO = re.compile(
    r"(this domain (is|may be) for sale|domain is parked|este dominio (est[aá] )?en venta|"
    r"buy this domain|compra este dominio)",
    re.IGNORECASE,
)
# visores de documentos externos
VISORES = (
    "drive.google.com",
    "docs.google.com",
    "dropbox.com",
    "onedrive.live.com",
    "1drv.ms",
    "sharepoint.com",
    "issuu.com",
    "scribd.com",
    "calameo.com",
)
# archivos que nunca son ni página ni documento buscado
NO_PAGINA = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "svg",
    "webp",
    "ico",
    "bmp",
    "tif",
    "tiff",
    "mp3",
    "mp4",
    "avi",
    "mov",
    "wmv",
    "webm",
    "ogg",
    "wav",
    "zip",
    "rar",
    "7z",
    "gz",
    "tar",
    "exe",
    "msi",
    "dmg",
    "apk",
    "css",
    "js",
    "json",
    "xml",
    "rss",
    "woff",
    "woff2",
    "ttf",
    "eot",
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "csv",
    "txt",
    "kml",
    "kmz",
}
# URLs sin extensión que suelen servir archivos: vale la pena preguntar con HEAD
SOSPECHA_DOCUMENTO = re.compile(
    r"(descarga|download|getfile|get_file|archivo|documento|attachment|adjunto|"
    r"ver_?pdf|verpdf|consultarpdf|bitstream|\.ashx|filedownload|file\.php|pdf)",
    re.IGNORECASE,
)
ESQUEMAS_NO = ("mailto:", "javascript:", "tel:", "data:", "whatsapp:", "sms:", "#")


@dataclass
class Enlace:
    url: str
    ancla: str
    etiqueta: str  # a, iframe, embed, object, area


def extension(url: str) -> str:
    ruta = urlsplit(url).path
    return PurePosixPath(ruta).suffix.lower().lstrip(".")


def es_documento(url: str, extensiones: list[str]) -> bool:
    return extension(url) in extensiones


def mimes_de(extensiones: list[str]) -> set[str]:
    mimes = set()
    for ext in extensiones:
        tipo, _ = mimetypes.guess_type(f"x.{ext}")
        if tipo:
            mimes.add(tipo)
    if "pdf" in extensiones:
        mimes |= {"application/pdf", "application/x-pdf", "application/acrobat"}
    return mimes


def es_red_social(url_o_host: str) -> bool:
    host = host_de(url_o_host) if "/" in url_o_host else url_o_host
    return any(coincide(host, r) for r in REDES_SOCIALES)


def es_visor(url: str) -> bool:
    return any(coincide(host_de(url), v) for v in VISORES)


def estacionado(url_final: str, html: str = "") -> bool:
    host = host_de(url_final)
    return any(coincide(host, e) for e in ESTACIONADOS) or bool(TEXTO_ESTACIONADO.search(html[:20000]))


def es_pagina(url: str) -> bool:
    return extension(url) not in NO_PAGINA


def nombre_de_archivo(cabecera_disposicion: str | None) -> str | None:
    """filename de un Content-Disposition (también filename*=UTF-8'')."""
    if not cabecera_disposicion:
        return None
    m = Message()
    m["content-disposition"] = cabecera_disposicion
    nombre = m.get_filename()
    return nombre.strip() if nombre else None


def tipo_de_respuesta(
    content_type: str | None, disposicion: str | None, mimes: set[str], extensiones: list[str]
) -> str | None:
    """Si la respuesta es un documento buscado, su MIME; si no, None."""
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in mimes:
        return mime
    nombre = nombre_de_archivo(disposicion)
    if nombre and es_documento("/" + nombre, extensiones):
        return mimetypes.guess_type(nombre)[0] or mime or "application/octet-stream"
    return None


def url_directa(url: str) -> str:
    """Convierte visores de Google Drive/Docs, Dropbox y OneDrive en enlaces de descarga."""
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if host == "drive.google.com":
        m = re.search(r"/file/d/([\w-]+)", p.path)
        id_ = m.group(1) if m else (parse_qs(p.query).get("id") or [None])[0]
        if id_:
            return f"https://drive.google.com/uc?export=download&id={id_}"
    if host == "docs.google.com":
        m = re.match(r"/(document|presentation|spreadsheets)/d/([\w-]+)", p.path)
        if m:
            clase, id_ = m.groups()
            if clase == "presentation":
                return f"https://docs.google.com/presentation/d/{id_}/export/pdf"
            return f"https://docs.google.com/{clase}/d/{id_}/export?format=pdf"
    if host.endswith("dropbox.com"):
        consulta = re.sub(r"(^|&)dl=0", r"\1dl=1", p.query)
        if "dl=1" not in consulta:
            consulta = f"{consulta}&dl=1" if consulta else "dl=1"
        return p._replace(query=consulta).geturl()
    if host == "onedrive.live.com" and "download=1" not in p.query:
        return p._replace(query=f"{p.query}&download=1" if p.query else "download=1").geturl()
    return url


def _ancla(etiqueta) -> str:
    texto = etiqueta.get_text(" ", strip=True)
    if not texto:
        img = etiqueta.find("img")
        texto = (img.get("alt") or img.get("title") or "") if img else ""
    texto = texto or etiqueta.get("title") or etiqueta.get("aria-label") or ""
    if len(texto) < 4:
        # enlaces tipo "descargar" o un ícono: el renglón de la tabla o el elemento de lista da contexto
        contenedor = etiqueta.find_parent(["tr", "li"])
        if contenedor is not None:
            texto = contenedor.get_text(" ", strip=True)
    return " ".join(texto.split())[:300]


def extraer_enlaces(html: str | bytes, base: str) -> list[Enlace]:
    sopa = BeautifulSoup(html, "lxml")
    etiqueta_base = sopa.find("base", href=True)
    if etiqueta_base:
        base = urljoin(base, etiqueta_base["href"])
    enlaces: list[Enlace] = []
    vistos: set[str] = set()
    for nombre, atributo in (("a", "href"), ("area", "href"), ("iframe", "src"), ("embed", "src"), ("object", "data")):
        for etiqueta in sopa.find_all(nombre):
            crudo = (etiqueta.get(atributo) or "").strip()
            if not crudo or crudo.lower().startswith(ESQUEMAS_NO):
                continue
            url, _ = urldefrag(urljoin(base, crudo))
            if not url.lower().startswith(("http://", "https://")) or url in vistos:
                continue
            vistos.add(url)
            enlaces.append(Enlace(url, _ancla(etiqueta) if nombre in ("a", "area") else "", nombre))
    return enlaces
