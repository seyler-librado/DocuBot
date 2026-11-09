"""Explora un sitio y devuelve los documentos que encuentra.

1. Encuentra la portada (https/http, con y sin www). Si redirige a una red
   social o a un dominio estacionado, el sitio se marca y no se sigue.
2. Lee los sitemaps (si el perfil lo pide).
3. Recorre las páginas del mismo sitio por prioridad: primero las semillas,
   luego las que mencionan secciones prioritarias o un tipo de documento.
   Respeta profundidad, máximo de páginas y tiempo máximo.
4. Un enlace es documento si su extensión está en el perfil, si al pedirlo
   responde con el tipo de archivo correcto o si es un visor externo (Drive,
   Dropbox...). Los enlaces sin extensión que parecen descargas se confirman
   con HEAD (con un tope por sitio).

No escribe en la base de datos: eso lo hace la etapa que lo llama.
"""

import heapq
import itertools
import logging
import time
from dataclasses import dataclass, field

from docubot.descubrimiento import enlaces as E
from docubot.descubrimiento import sitemap
from docubot.filtros.dominios import coincide
from docubot.filtros.tipos import Clasificador, normalizar
from docubot.perfiles.esquema import Perfil
from docubot.red.cliente import BloqueadoPorRobots, Cliente, DemasiadoGrande, ErrorRed
from docubot.red.urls import clave_url, host_de, origen_de

log = logging.getLogger("docubot.explorador")

MAX_HEAD_POR_SITIO = 30
MAX_FALLAS_SEGUIDAS = 8  # si el sitio deja de responder, no insistir
SECCIONES_GENERALES = ("documentos", "descargas", "publicaciones", "biblioteca", "transparencia", "normatividad")


@dataclass
class DocumentoEncontrado:
    url: str
    ancla: str = ""
    pagina_origen: str | None = None
    profundidad: int = 0
    verificado: str = "ext"  # ext | head | get | visor | sitemap
    mime: str | None = None
    externo: bool = False


@dataclass
class ResultadoExploracion:
    estado: str = "explorado"  # explorado | sin_respuesta | redes_sociales | estacionado | bloqueado
    url_final: str | None = None
    paginas: int = 0
    documentos: list[DocumentoEncontrado] = field(default_factory=list)
    error: str | None = None
    segundos: float = 0.0
    urls_sitemap: int = 0
    heads: int = 0


class Explorador:
    def __init__(self, cliente: Cliente, perfil: Perfil) -> None:
        self.cliente = cliente
        self.config = perfil.descubrimiento.exploracion
        self.extensiones = perfil.documentos.extensiones
        self.mimes = E.mimes_de(self.extensiones)
        self.clasificador = Clasificador(perfil.documentos)
        secciones = self.config.secciones_prioritarias or SECCIONES_GENERALES
        self.secciones = [normalizar(s) for s in secciones]

    # --- API ------------------------------------------------------------------

    async def explorar(self, dominio: str, semillas: list[str] | None = None) -> ResultadoExploracion:
        inicio = time.monotonic()
        r = ResultadoExploracion()
        try:
            await self._explorar(dominio, list(dict.fromkeys(semillas or [])), r, inicio)
        finally:
            r.segundos = round(time.monotonic() - inicio, 2)
        return r

    # --- recorrido -------------------------------------------------------------

    async def _explorar(self, dominio: str, semillas: list[str], r: ResultadoExploracion, inicio: float) -> None:
        portada = await self._portada(dominio, r)
        if r.estado != "explorado":
            return
        if portada is None and not semillas:
            r.estado = "sin_respuesta"
            return

        base = dominio.lower().removeprefix("www.")
        bases = {base}
        if portada is not None:
            bases.add(host_de(str(portada.url)).removeprefix("www."))
        self._bases = bases
        self._vistos: set[str] = set()
        self._docs: dict[str, DocumentoEncontrado] = {}
        self._cola: list[tuple[int, int, str, int, str | None, str]] = []
        self._orden = itertools.count()
        self._heads = 0

        for s in semillas:
            if E.es_documento(s, self.extensiones):
                self._documento(s, "", None, 0, "ext")
            else:
                self._encolar(s, 0, None, "", prioridad=100)

        if portada is not None:
            r.url_final = str(portada.url)
            self._vistos.add(clave_url(r.url_final))
            r.paginas += 1
            await self._procesar_pagina(portada, 0)

        if self.config.sitemap:
            origen = origen_de(r.url_final or semillas[0])
            declarados = await self.cliente.sitemaps(origen + "/")
            urls = await sitemap.leer(self.cliente, origen, declarados)
            r.urls_sitemap = len(urls)
            for u in urls:
                if E.es_documento(u, self.extensiones):
                    self._documento(u, "", None, 1, "sitemap")
                elif self._mismo_sitio(u) and E.es_pagina(u):
                    self._encolar(u, 1, None, "", prioridad=self._prioridad(u, "") - 5)

        fallas = 0
        while self._cola and r.paginas < self.config.max_paginas:
            if time.monotonic() - inicio > self.config.tiempo_max_s:
                r.error = f"se alcanzó el tiempo máximo ({self.config.tiempo_max_s} s)"
                break
            _, _, url, profundidad, origen_pag, ancla = heapq.heappop(self._cola)
            clave = clave_url(url)
            if clave in self._vistos:
                continue
            self._vistos.add(clave)
            try:
                respuesta = await self.cliente.obtener(url)
            except BloqueadoPorRobots:
                continue
            except DemasiadoGrande:
                continue
            except ErrorRed as error:
                fallas += 1
                if fallas >= MAX_FALLAS_SEGUIDAS:
                    r.error = f"el sitio dejó de responder: {error}"
                    break
                continue
            fallas = 0
            mime = E.tipo_de_respuesta(
                respuesta.headers.get("content-type"),
                respuesta.headers.get("content-disposition"),
                self.mimes,
                self.extensiones,
            )
            if mime:
                self._documento(url, ancla, origen_pag, profundidad, "get", mime)
                continue
            if respuesta.status_code >= 400 or "html" not in respuesta.headers.get("content-type", "html"):
                continue
            r.paginas += 1
            await self._procesar_pagina(respuesta, profundidad)

        r.documentos = list(self._docs.values())
        r.heads = self._heads

    async def _portada(self, dominio: str, r: ResultadoExploracion):
        base = dominio.lower().removeprefix("www.")
        candidatas = [f"https://{base}/", f"https://www.{base}/", f"http://{base}/", f"http://www.{base}/"]
        ultimo_error = None
        for url in candidatas:
            try:
                respuesta = await self.cliente.obtener(url)
            except BloqueadoPorRobots:
                r.estado = "bloqueado"
                r.error = "robots.txt no permite la portada"
                return None
            except ErrorRed as error:
                ultimo_error = str(error)
                continue
            final = str(respuesta.url)
            if E.es_red_social(final):
                r.estado, r.url_final = "redes_sociales", final
                return None
            if respuesta.status_code >= 400:
                ultimo_error = f"respondió {respuesta.status_code}"
                continue
            if E.estacionado(final, respuesta.text if "html" in respuesta.headers.get("content-type", "") else ""):
                r.estado, r.url_final = "estacionado", final
                return None
            return respuesta
        r.error = ultimo_error
        return None

    async def _procesar_pagina(self, respuesta, profundidad: int) -> None:
        pagina = str(respuesta.url)
        for enlace in E.extraer_enlaces(respuesta.content, pagina):
            url, ancla = enlace.url, enlace.ancla
            if E.es_red_social(url):
                continue
            if E.es_documento(url, self.extensiones):
                self._documento(url, ancla, pagina, profundidad + 1, "ext")
            elif E.es_visor(url):
                if self.clasificador.interesa(url, ancla):
                    self._documento(E.url_directa(url), ancla, pagina, profundidad + 1, "visor")
            elif self._mismo_sitio(url) and E.es_pagina(url):
                if E.SOSPECHA_DOCUMENTO.search(url) and self.clasificador.interesa(url, ancla):
                    if await self._confirmar_con_head(url, ancla, pagina, profundidad + 1):
                        continue
                if profundidad + 1 <= self.config.profundidad:
                    self._encolar(url, profundidad + 1, pagina, ancla, self._prioridad(url, ancla))

    async def _confirmar_con_head(self, url: str, ancla: str, pagina: str, profundidad: int) -> bool:
        clave = clave_url(url)
        if self._heads >= MAX_HEAD_POR_SITIO or clave in self._vistos:
            return False
        self._heads += 1
        try:
            r = await self.cliente.cabeza(url)
        except ErrorRed:
            return False
        mime = E.tipo_de_respuesta(
            r.headers.get("content-type"), r.headers.get("content-disposition"), self.mimes, self.extensiones
        )
        if mime:
            self._vistos.add(clave)
            self._documento(url, ancla, pagina, profundidad, "head", mime)
            return True
        return False

    # --- utilidades --------------------------------------------------------------

    def _mismo_sitio(self, url: str) -> bool:
        host = host_de(url)
        return any(coincide(host, b) for b in self._bases)

    def _prioridad(self, url: str, ancla: str) -> int:
        texto = normalizar(f"{url} {ancla}")
        p = 0
        if any(s in texto for s in self.secciones):
            p += 20
        if self.clasificador.tipo_de(url, ancla):
            p += 30
        return p

    def _encolar(self, url: str, profundidad: int, origen: str | None, ancla: str, prioridad: int) -> None:
        if clave_url(url) in self._vistos:
            return
        # menor profundidad primero a igual prioridad; heapq es de mínimos
        heapq.heappush(self._cola, (-prioridad + profundidad * 10, next(self._orden), url, profundidad, origen, ancla))

    def _documento(
        self, url: str, ancla: str, pagina: str | None, profundidad: int, verificado: str, mime: str | None = None
    ) -> None:
        clave = clave_url(url)
        previo = self._docs.get(clave)
        if previo is not None:
            if not previo.ancla and ancla:
                previo.ancla = ancla
            return
        self._docs[clave] = DocumentoEncontrado(
            url=url,
            ancla=ancla,
            pagina_origen=pagina,
            profundidad=profundidad,
            verificado=verificado,
            mime=mime,
            externo=not self._mismo_sitio(url) if hasattr(self, "_bases") else False,
        )
