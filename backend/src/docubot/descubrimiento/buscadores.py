"""Adaptadores de buscadores. Todos devuelven una lista de Resultado.

| motor   | llave en .env                        | notas                                   |
|---------|--------------------------------------|-----------------------------------------|
| searxng | ninguna                              | buscador propio (docker compose --profile searxng) |
| brave   | DOCUBOT_BUSCADORES__BRAVE_LLAVE      | Brave Search API                        |
| serper  | DOCUBOT_BUSCADORES__SERPER_LLAVE     | resultados de Google vía serper.dev     |
| serpapi | DOCUBOT_BUSCADORES__SERPAPI_LLAVE    | resultados de Google vía serpapi.com    |
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlencode

from docubot.ajustes import AjustesBuscadores
from docubot.pipeline.errores import ErrorPermanente
from docubot.red.cliente import Cliente, ErrorRed


@dataclass
class Resultado:
    url: str
    titulo: str = ""
    resumen: str = ""


Buscar = Callable[[Cliente, str, int, AjustesBuscadores], Awaitable[list[Resultado]]]


def _llave(valor, nombre: str) -> str:
    if valor is None or not valor.get_secret_value():
        raise ErrorPermanente(
            f"el motor {nombre} necesita una llave: define DOCUBOT_BUSCADORES__{nombre.upper()}_LLAVE en .env"
        )
    return valor.get_secret_value()


async def _json(cliente: Cliente, url: str, motor: str, **kw) -> dict:
    try:
        if "json" in kw:
            r = await cliente.publicar(url, kw.pop("json"), **kw)
        else:
            r = await cliente.obtener(url, **kw)
    except ErrorRed as error:
        raise ErrorRed(f"{motor}: {error}", url) from error
    if r.status_code in (401, 403):
        raise ErrorPermanente(f"{motor} rechazó la llave (respondió {r.status_code})")
    if r.status_code >= 400:
        raise ErrorRed(f"{motor} respondió {r.status_code}: {r.text[:200]}", url.split("?")[0])
    try:
        return r.json()
    except ValueError:
        if motor == "searxng":
            raise ErrorPermanente(
                "SearXNG no devolvió JSON: activa 'json' en search.formats de su settings.yml"
            ) from None
        raise ErrorRed(f"{motor} no devolvió JSON", url.split("?")[0]) from None


async def searxng(cliente: Cliente, consulta: str, maximo: int, a: AjustesBuscadores) -> list[Resultado]:
    resultados: list[Resultado] = []
    vistos: set[str] = set()
    for pagina in range(1, 6):
        parametros = {"q": consulta, "format": "json", "pageno": pagina, "language": a.idioma or "all"}
        datos = await _json(cliente, f"{a.searxng_url.rstrip('/')}/search?{urlencode(parametros)}", "searxng")
        nuevos = [r for r in datos.get("results", []) if r.get("url") and r["url"] not in vistos]
        if not nuevos:
            break
        for r in nuevos:
            vistos.add(r["url"])
            resultados.append(Resultado(r["url"], r.get("title", ""), r.get("content", "")))
        if len(resultados) >= maximo:
            break
    return resultados[:maximo]


async def brave(cliente: Cliente, consulta: str, maximo: int, a: AjustesBuscadores) -> list[Resultado]:
    llave = _llave(a.brave_llave, "brave")
    resultados: list[Resultado] = []
    for desplazamiento in range(0, 10):
        parametros = {"q": consulta, "count": 20, "offset": desplazamiento}
        if a.pais:
            parametros["country"] = a.pais
        if a.idioma:
            parametros["search_lang"] = a.idioma
        datos = await _json(
            cliente,
            f"https://api.search.brave.com/res/v1/web/search?{urlencode(parametros)}",
            "brave",
            cabeceras={"X-Subscription-Token": llave, "Accept": "application/json"},
        )
        pagina = datos.get("web", {}).get("results", [])
        resultados += [
            Resultado(r["url"], r.get("title", ""), r.get("description", "")) for r in pagina if r.get("url")
        ]
        if len(resultados) >= maximo or not datos.get("query", {}).get("more_results_available"):
            break
    return resultados[:maximo]


async def serper(cliente: Cliente, consulta: str, maximo: int, a: AjustesBuscadores) -> list[Resultado]:
    llave = _llave(a.serper_llave, "serper")
    cuerpo: dict = {"q": consulta, "num": min(maximo, 100)}
    if a.pais:
        cuerpo["gl"] = a.pais
    if a.idioma:
        cuerpo["hl"] = a.idioma
    datos = await _json(
        cliente, "https://google.serper.dev/search", "serper", json=cuerpo, cabeceras={"X-API-KEY": llave}
    )
    return [
        Resultado(r["link"], r.get("title", ""), r.get("snippet", ""))
        for r in datos.get("organic", [])
        if r.get("link")
    ][:maximo]


async def serpapi(cliente: Cliente, consulta: str, maximo: int, a: AjustesBuscadores) -> list[Resultado]:
    llave = _llave(a.serpapi_llave, "serpapi")
    parametros = {"engine": "google", "q": consulta, "num": min(maximo, 100), "api_key": llave}
    if a.pais:
        parametros["gl"] = a.pais
    if a.idioma:
        parametros["hl"] = a.idioma
    datos = await _json(cliente, f"https://serpapi.com/search.json?{urlencode(parametros)}", "serpapi")
    if datos.get("error") and "hasn't returned any results" not in datos["error"]:
        raise ErrorRed(f"serpapi: {datos['error']}", "https://serpapi.com/search.json")
    return [
        Resultado(r["link"], r.get("title", ""), r.get("snippet", ""))
        for r in datos.get("organic_results", [])
        if r.get("link")
    ][:maximo]


MOTORES: dict[str, Buscar] = {"searxng": searxng, "brave": brave, "serper": serper, "serpapi": serpapi}
