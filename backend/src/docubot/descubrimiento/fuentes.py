"""Las fuentes de descubrimiento. Cada una recibe (contexto, fuente del perfil, carga de la tarea).

Las que pueden tardar mucho se parten en tareas más chicas (el buscador: una
tarea por consulta), así el trabajo se reparte entre trabajadores y una
corrida interrumpida se reanuda sin repetir lo hecho.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode, urlsplit

from docubot.ajustes import obtener_ajustes
from docubot.descubrimiento import variables
from docubot.descubrimiento.buscadores import MOTORES
from docubot.descubrimiento.contexto import Contexto, NuevoCandidato, dominio_de
from docubot.descubrimiento.enlaces import es_documento, es_red_social
from docubot.perfiles.esquema import (
    FuenteBuscador,
    FuenteCommonCrawl,
    FuenteListaDominios,
    FuenteSemillas,
    FuenteWayback,
)
from docubot.red.cliente import ErrorRed
from docubot.red.urls import host_de

log = logging.getLogger("docubot.fuentes")

COLLINFO = "https://index.commoncrawl.org/collinfo.json"
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"


async def semillas(ctx: Contexto, fuente: FuenteSemillas, carga: dict[str, Any]) -> None:
    documentos = []
    for url in map(str, fuente.urls):
        if es_documento(url, ctx.perfil.documentos.extensiones):
            documentos.append(NuevoCandidato(url, "semillas"))
        else:
            await ctx.agregar_sitio(url, origen="semillas", semillas=[url])
    await ctx.agregar_candidatos(documentos)


async def lista_dominios(ctx: Contexto, fuente: FuenteListaDominios, carga: dict[str, Any]) -> None:
    filas = variables.leer_csv(ctx.carpeta / fuente.archivo)
    nuevos = 0
    for fila in filas:
        valor = fila.get(fuente.columna_dominio, "")
        if not valor:
            continue
        lugar = fila.get(fuente.columna_lugar) if fuente.columna_lugar else None
        url = valor if "://" in valor else f"https://{valor}"
        semilla = [url] if urlsplit(url).path not in ("", "/") else []  # si trae ruta, se usa como semilla
        nuevos += await ctx.agregar_sitio(valor, origen="lista", semillas=semilla, lugar=lugar or None)
    log.info("lista %s: %s filas, %s sitios nuevos en la corrida", fuente.archivo, len(filas), nuevos)


async def buscador(ctx: Contexto, fuente: FuenteBuscador, carga: dict[str, Any]) -> None:
    if "consulta" not in carga:
        lista = variables.consultas(fuente, ctx.carpeta)
        if len(lista) > 1:
            for consulta, lugar in lista:
                await ctx.encolar("descubrir", {"fuente": carga["fuente"], "consulta": consulta, "lugar": lugar})
            log.info("buscador %s: %s consultas encoladas", fuente.motor, len(lista))
            return
        if not lista:
            return
        consulta, lugar = lista[0]
    else:
        consulta, lugar = carga["consulta"], carga.get("lugar")

    resultados = await MOTORES[fuente.motor](
        ctx.cliente_api, consulta, fuente.max_resultados, obtener_ajustes().buscadores
    )
    extensiones = ctx.perfil.documentos.extensiones
    documentos = []
    for r in resultados:
        host = host_de(r.url)
        if not host or es_red_social(host) or not ctx.filtro.permitido(host):
            continue
        if es_documento(r.url, extensiones):
            documentos.append(
                NuevoCandidato(
                    r.url,
                    "buscador",
                    ancla=r.titulo,
                    lugar=lugar,
                    datos={"consulta": consulta, "resumen": r.resumen[:300]},
                )
            )
            if fuente.usar == "dominios":
                await ctx.agregar_sitio(host, origen="buscador", lugar=lugar)
        elif fuente.usar == "dominios":
            await ctx.agregar_sitio(host, origen="buscador", semillas=[r.url], lugar=lugar)
    await ctx.agregar_candidatos(documentos)
    log.info("buscador %s «%s»: %s resultados, %s documentos", fuente.motor, consulta, len(resultados), len(documentos))


def _lineas_json(texto: str) -> list[dict[str, Any]]:
    salida = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("{"):
            try:
                salida.append(json.loads(linea))
            except ValueError:
                continue
    return salida


async def commoncrawl(ctx: Contexto, fuente: FuenteCommonCrawl, carga: dict[str, Any]) -> None:
    cliente = ctx.cliente_api
    r = await cliente.obtener(COLLINFO)
    if r.status_code != 200:
        raise ErrorRed(f"Common Crawl respondió {r.status_code}", COLLINFO)
    indices = r.json()[: fuente.indices]

    parametros = [
        ("url", fuente.patron),
        ("output", "json"),
        ("fl", "url,mime-detected,status,timestamp"),
        ("filter", "=status:200"),
        ("filter", f"=mime-detected:{fuente.mime}"),
    ]
    vistos: set[str] = set()
    total = 0
    for indice in indices:
        api = indice["cdx-api"]
        r = await cliente.obtener(f"{api}?{urlencode(parametros + [('showNumPages', 'true')])}")
        if r.status_code == 404:
            continue
        if r.status_code != 200:
            raise ErrorRed(f"Common Crawl ({indice['id']}) respondió {r.status_code}", api)
        paginas = int((_lineas_json(r.text) or [{"pages": 1}])[0].get("pages", 1))
        for pagina in range(paginas):
            if total >= fuente.limite:
                break
            r = await cliente.obtener(f"{api}?{urlencode(parametros + [('page', str(pagina))])}")
            if r.status_code == 404:
                break
            if r.status_code != 200:
                raise ErrorRed(f"Common Crawl ({indice['id']}) respondió {r.status_code}", api)
            nuevos = []
            for fila in _lineas_json(r.text):
                url = fila.get("url", "")
                if not url or url in vistos or not ctx.filtro.permitido(host_de(url)):
                    continue
                vistos.add(url)
                nuevos.append(
                    NuevoCandidato(url, "commoncrawl", datos={"indice": indice["id"], "fecha": fila.get("timestamp")})
                )
            nuevos = nuevos[: fuente.limite - total]
            total += await ctx.agregar_candidatos(nuevos)
        log.info("commoncrawl %s: %s documentos hasta ahora", indice["id"], total)


def _consulta_wayback(patron: str) -> tuple[str, str]:
    if patron.startswith("*."):
        return patron[2:], "domain"
    if patron.endswith("*"):
        return patron[:-1], "prefix"
    return patron, "domain" if "/" not in patron else "exact"


async def wayback(ctx: Contexto, fuente: FuenteWayback, carga: dict[str, Any]) -> None:
    url, tipo = _consulta_wayback(fuente.patron)
    parametros = [
        ("url", url),
        ("matchType", tipo),
        ("output", "json"),
        ("fl", "original,mimetype,timestamp"),
        ("filter", "statuscode:200"),
        ("filter", f"mimetype:{fuente.mime}"),
        ("collapse", "urlkey"),
        ("limit", str(fuente.limite)),
    ]
    r = await ctx.cliente_api.obtener(f"{WAYBACK_CDX}?{urlencode(parametros)}")
    if r.status_code != 200:
        raise ErrorRed(f"Wayback respondió {r.status_code}", WAYBACK_CDX)
    filas = r.json() if r.content.strip() else []
    nuevos = [
        NuevoCandidato(original, "wayback", datos={"wayback": marca})
        for original, _mime, marca in filas[1:]
        if ctx.filtro.permitido(host_de(original))
    ]
    total = await ctx.agregar_candidatos(nuevos)
    log.info("wayback %s: %s documentos", fuente.patron, total)


Ejecutar = Callable[[Contexto, Any, dict[str, Any]], Awaitable[None]]

FUENTES: dict[str, Ejecutar] = {
    "semillas": semillas,
    "lista_dominios": lista_dominios,
    "buscador": buscador,
    "commoncrawl": commoncrawl,
    "wayback": wayback,
}

__all__ = ["FUENTES", "dominio_de"]
