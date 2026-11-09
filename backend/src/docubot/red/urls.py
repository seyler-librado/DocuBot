"""Utilidades de URLs: host, clave para deduplicar."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit

# parámetros de seguimiento que no cambian el recurso
RASTREO = re.compile(r"^(utm_\w+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|_ga)$", re.IGNORECASE)
PUERTOS_POR_OMISION = {"http": 80, "https": 443}


def host_de(url: str) -> str:
    """Host en minúsculas, sin punto final ni puerto. '' si la URL no tiene host."""
    try:
        return (urlsplit(url.strip()).hostname or "").rstrip(".")
    except ValueError:
        return ""


def origen_de(url: str) -> str:
    """esquema://host[:puerto]"""
    p = urlsplit(url.strip())
    return f"{p.scheme}://{p.netloc}"


def clave_url(url: str) -> str:
    """Forma normalizada para saber si dos URLs son el mismo recurso.

    Sin esquema, sin 'www.', sin fragmento, sin barra final, sin parámetros de
    seguimiento. Conserva el resto de la consulta (muchos portales sirven
    documentos con ?id=...).
    """
    p = urlsplit(url.strip())
    host = (p.hostname or "").rstrip(".")
    host = host.removeprefix("www.")
    try:
        puerto = p.port
    except ValueError:
        puerto = None
    if puerto and puerto != PUERTOS_POR_OMISION.get(p.scheme.lower()):
        host = f"{host}:{puerto}"
    ruta = re.sub(r"/{2,}", "/", p.path or "").rstrip("/")
    consulta = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not RASTREO.match(k)])
    return host + ruta + (f"?{consulta}" if consulta else "")
