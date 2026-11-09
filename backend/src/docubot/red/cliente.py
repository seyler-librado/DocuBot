"""Cliente HTTP con buenos modales.

Toda petición de DocuBot a la web pasa por aquí:
- se identifica con su user agent;
- consulta robots.txt de cada origen (también en cada salto de una redirección);
- respeta el ritmo por dominio (LimitadorPorDominio) y el Crawl-delay;
- reintenta errores de conexión, 429 y 5xx con espera creciente (o la que pida Retry-After);
- si un certificado TLS está mal, puede reintentar sin verificarlo y lo anota;
- corta las respuestas que pasan del tamaño máximo.

Uso:
    async with Cliente() as cliente:
        r = await cliente.obtener("https://sitio.gob.mx/")
"""

import asyncio
import logging
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import httpx

from docubot.ajustes import AjustesRed, obtener_ajustes
from docubot.red import robots
from docubot.red.limitador import LimitadorPorDominio
from docubot.red.urls import host_de, origen_de

log = logging.getLogger("docubot.red")

REINTENTABLES = {429, 500, 502, 503, 504}
REDIRECCIONES = {301, 302, 303, 307, 308}
MAX_ESPERA = 300.0


@dataclass
class _Extra:
    """Lo que acompaña a una petición además de la URL."""

    cabeceras: dict[str, str] | None = None
    json: object = None
    sumidero: object = None  # con .reiniciar() y .escribir(bytes): recibe el cuerpo de las respuestas 2xx


def _sin_consulta(url: str) -> str:
    """URL sin la consulta, para la bitácora (las APIs llevan llaves en ella)."""
    return url.split("?", 1)[0]


class ErrorRed(Exception):
    """No se pudo obtener la URL."""

    def __init__(self, mensaje: str, url: str) -> None:
        super().__init__(mensaje)
        self.url = url


class BloqueadoPorRobots(ErrorRed):
    pass


class DemasiadoGrande(ErrorRed):
    pass


class SinDNS(ErrorRed):
    """El dominio no existe (o ya no): reintentar no sirve."""


def _es_error_dns(error: Exception) -> bool:
    actual: BaseException | None = error
    while actual is not None:
        if isinstance(actual, socket.gaierror):
            return True
        texto = str(actual)
        if "Name or service not known" in texto or "nodename nor servname" in texto or "getaddrinfo failed" in texto:
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def _es_error_tls(error: Exception) -> bool:
    actual: BaseException | None = error
    while actual is not None:
        if isinstance(actual, ssl.SSLError):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in str(actual) or "certificate verify failed" in str(actual):
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def _retry_after(valor: str | None) -> float | None:
    if not valor:
        return None
    try:
        return max(0.0, float(valor))
    except ValueError:
        pass
    try:
        fecha = parsedate_to_datetime(valor)
        return max(0.0, (fecha - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


class Cliente:
    def __init__(
        self,
        ajustes: AjustesRed | None = None,
        *,
        peticiones_por_segundo: float | None = None,
        respetar_robots: bool | None = None,
        transporte: httpx.AsyncBaseTransport | None = None,
        transporte_sin_tls: httpx.AsyncBaseTransport | None = None,
        espera_base: float = 2.0,
    ) -> None:
        self.ajustes = ajustes or obtener_ajustes().red
        a = self.ajustes
        self.agente = robots.agente_de(a.user_agent)
        self.respetar_robots = a.respetar_robots if respetar_robots is None else respetar_robots
        self.limitador = LimitadorPorDominio(
            peticiones_por_segundo or a.peticiones_por_segundo_por_dominio,
            a.simultaneas_por_dominio,
        )
        self.espera_base = espera_base
        self.hosts_sin_tls: set[str] = set()  # hosts con certificado inválido
        self._reglas: dict[str, robots.Reglas] = {}
        self._candados_robots: dict[str, asyncio.Lock] = {}

        comunes = dict(
            headers={
                "User-Agent": a.user_agent,
                "Accept-Language": "es,en;q=0.8",
            },
            timeout=httpx.Timeout(a.timeout, connect=min(a.timeout, 15.0)),
            follow_redirects=False,
        )
        self._http = httpx.AsyncClient(verify=a.verificar_tls, transport=transporte, **comunes)
        self._http_sin_tls = httpx.AsyncClient(verify=False, transport=transporte_sin_tls or transporte, **comunes)

    async def __aenter__(self) -> "Cliente":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.cerrar()

    async def cerrar(self) -> None:
        await self._http.aclose()
        await self._http_sin_tls.aclose()

    # --- API pública -----------------------------------------------------------

    async def obtener(
        self,
        url: str,
        *,
        max_bytes: int | None = None,
        cabeceras: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET siguiendo redirecciones. La respuesta trae el contenido completo.

        Lanza BloqueadoPorRobots, DemasiadoGrande o ErrorRed. Las respuestas 4xx/5xx
        finales se devuelven (el que llama decide qué hacer con ellas).
        """
        return await self._seguir(url, "GET", self._limite(max_bytes), _Extra(cabeceras))

    async def publicar(
        self,
        url: str,
        json: object,
        *,
        cabeceras: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> httpx.Response:
        """POST con cuerpo JSON (para APIs). No sigue redirecciones."""
        if not await self.permitido(url):
            raise BloqueadoPorRobots(f"robots.txt no permite {_sin_consulta(url)}", url)
        return await self._pedir(url, "POST", self._limite(max_bytes), _Extra(cabeceras, json))

    async def descargar(self, url: str, sumidero: object, *, max_bytes: int) -> httpx.Response:
        """GET que escribe el cuerpo en `sumidero` en lugar de guardarlo en memoria.

        Sigue redirecciones y reintenta como `obtener`; si reintenta, el sumidero
        empieza de cero. La respuesta devuelta trae cabeceras y estado, sin contenido.
        """
        return await self._seguir(url, "GET", max_bytes, _Extra(sumidero=sumidero))

    async def cabeza(self, url: str) -> httpx.Response:
        """HEAD siguiendo redirecciones (para saber tipo y tamaño sin descargar)."""
        return await self._seguir(url, "HEAD", 0, _Extra())

    async def permitido(self, url: str) -> bool:
        """¿El robots.txt del sitio deja pedir esta URL?"""
        if not self.respetar_robots:
            return True
        reglas = await self._reglas_de(url)
        return reglas.permite(url, self.agente)

    async def sitemaps(self, url: str) -> list[str]:
        """Sitemaps que declara el robots.txt del sitio (se lee aunque no se respete)."""
        reglas = await self._reglas_de(url)
        return list(reglas.parser.sitemaps) if reglas.parser is not None else []

    # --- internos --------------------------------------------------------------

    def _limite(self, max_bytes: int | None) -> int:
        return max_bytes if max_bytes is not None else self.ajustes.max_mb_pagina * 1024 * 1024

    async def _seguir(self, url: str, metodo: str, limite: int, extra: "_Extra") -> httpx.Response:
        actual = url
        for _ in range(self.ajustes.max_redirecciones + 1):
            if not await self.permitido(actual):
                raise BloqueadoPorRobots(f"robots.txt no permite {actual}", actual)
            r = await self._pedir(actual, metodo, limite, extra)
            destino = r.headers.get("location")
            if r.status_code in REDIRECCIONES and destino:
                actual = urljoin(str(r.url), destino)
                if r.status_code == 303:
                    metodo = "GET" if metodo != "HEAD" else "HEAD"
                continue
            return r
        raise ErrorRed(f"demasiadas redirecciones (más de {self.ajustes.max_redirecciones})", url)

    async def _pedir(self, url: str, metodo: str, limite: int, extra: "_Extra | None" = None) -> httpx.Response:
        """Una petición (sin seguir redirecciones), con ritmo y reintentos."""
        host = host_de(url)
        if not host:
            raise ErrorRed("URL sin host", url)
        intentos = self.ajustes.reintentos + 1
        ultimo_error = ""
        for intento in range(intentos):
            try:
                async with self.limitador.turno(host):
                    r = await self._una(url, metodo, limite, host, extra or _Extra())
            except DemasiadoGrande:
                raise
            except httpx.TransportError as error:
                if _es_error_dns(error):
                    raise SinDNS(f"el dominio {host} no existe (no resuelve DNS)", url) from error
                ultimo_error = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
                if intento + 1 < intentos:
                    await asyncio.sleep(self.espera_base * 2**intento)
                continue

            if r.status_code in REINTENTABLES and intento + 1 < intentos:
                espera = _retry_after(r.headers.get("retry-after"))
                espera = min(espera if espera is not None else self.espera_base * 2**intento, MAX_ESPERA)
                if r.status_code in (429, 503):
                    self.limitador.pausar(host, espera)
                log.info("%s respondió %s; reintento en %.0fs", _sin_consulta(url), r.status_code, espera)
                await asyncio.sleep(espera)
                continue
            return r
        raise ErrorRed(f"sin respuesta tras {intentos} intento(s): {ultimo_error}", url)

    async def _una(self, url: str, metodo: str, limite: int, host: str, extra: "_Extra") -> httpx.Response:
        cliente = self._http_sin_tls if host in self.hosts_sin_tls else self._http
        try:
            return await self._leer(cliente, url, metodo, limite, extra)
        except httpx.ConnectError as error:
            if cliente is self._http and self.ajustes.reintentar_sin_tls and _es_error_tls(error):
                log.warning("certificado inválido en %s; se reintenta sin verificar", host)
                self.hosts_sin_tls.add(host)
                return await self._leer(self._http_sin_tls, url, metodo, limite, extra)
            raise

    @staticmethod
    async def _leer(cliente: httpx.AsyncClient, url: str, metodo: str, limite: int, extra: "_Extra") -> httpx.Response:
        async with cliente.stream(metodo, url, headers=extra.cabeceras, json=extra.json) as r:
            if metodo == "HEAD":
                await r.aread()
                return r
            declarado = r.headers.get("content-length")
            if limite and declarado and declarado.isdigit() and int(declarado) > limite:
                raise DemasiadoGrande(f"{url} pesa {int(declarado)} bytes (máximo {limite})", url)
            sumidero = extra.sumidero if extra.sumidero is not None and 200 <= r.status_code < 300 else None
            if sumidero is not None:
                sumidero.reiniciar()
            partes: list[bytes] = []
            total = 0
            async for parte in r.aiter_bytes():
                total += len(parte)
                if limite and total > limite:
                    raise DemasiadoGrande(f"{url} pasa de {limite} bytes", url)
                if sumidero is not None:
                    sumidero.escribir(parte)
                else:
                    partes.append(parte)
            # el contenido ya viene descomprimido: sin estas cabeceras httpx no lo vuelve a decodificar
            cabeceras = httpx.Headers(r.headers)
            for nombre in ("content-encoding", "content-length", "transfer-encoding"):
                cabeceras.pop(nombre, None)
            completa = httpx.Response(
                r.status_code,
                headers=cabeceras,
                content=b"".join(partes),
                request=r.request,
                extensions=r.extensions,
            )
            return completa

    async def _reglas_de(self, url: str) -> robots.Reglas:
        origen = origen_de(url)
        reglas = self._reglas.get(origen)
        if reglas is not None and not reglas.vencida:
            return reglas
        candado = self._candados_robots.setdefault(origen, asyncio.Lock())
        async with candado:
            reglas = self._reglas.get(origen)
            if reglas is not None and not reglas.vencida:
                return reglas
            reglas = await self._leer_robots(origen)
            self._reglas[origen] = reglas
            retraso = reglas.retraso(self.agente)
            if retraso:
                self.limitador.fijar_retraso(host_de(url), retraso)
            return reglas

    async def _leer_robots(self, origen: str) -> robots.Reglas:
        url = f"{origen}/robots.txt"
        try:
            # sin pasar por robots (obvio) y siguiendo pocas redirecciones
            actual = url
            for _ in range(5):
                r = await self._pedir(actual, "GET", 512 * 1024)
                if r.status_code in REDIRECCIONES and r.headers.get("location"):
                    actual = urljoin(str(r.url), r.headers["location"])
                    continue
                break
        except (ErrorRed, httpx.HTTPError) as error:
            return robots.desde_respuesta(None, detalle=str(error))
        return robots.desde_respuesta(r.status_code, r.text)
