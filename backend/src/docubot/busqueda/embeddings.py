"""Vectores para la búsqueda por tema.

| embeddings     | qué usa                                                           |
|----------------|-------------------------------------------------------------------|
| local          | fastembed (ONNX en CPU) dentro del contenedor; el modelo se descarga una vez |
| ollama         | http://ollama:11434/v1/embeddings                                 |
| openai         | https://api.openai.com/v1/embeddings (con llave)                  |
| openai_compat  | /embeddings del servidor que digas en busqueda.url               |
"""

import asyncio
import logging
import threading
from abc import ABC, abstractmethod

import httpx

from docubot.ajustes import AjustesBusqueda, obtener_ajustes
from docubot.ia.base import ErrorIA, ErrorIAPermanente

log = logging.getLogger("docubot.busqueda")
LOTE = 64


class ProveedorEmbeddings(ABC):
    nombre = "?"

    def __init__(self, ajustes: AjustesBusqueda) -> None:
        self.ajustes = ajustes

    @property
    def modelo(self) -> str:
        return self.ajustes.modelo

    @abstractmethod
    async def _vectores(self, textos: list[str]) -> list[list[float]]: ...

    async def documentos(self, textos: list[str]) -> list[list[float]]:
        salida: list[list[float]] = []
        for i in range(0, len(textos), LOTE):
            salida += await self._vectores(textos[i : i + LOTE])
        return salida

    async def consulta(self, texto: str) -> list[float]:
        return (await self._vectores([texto]))[0]

    async def cerrar(self) -> None:
        return None


class Local(ProveedorEmbeddings):
    """Modelo chico en CPU (fastembed). Se carga una vez por proceso."""

    nombre = "local"

    def __init__(self, ajustes: AjustesBusqueda) -> None:
        super().__init__(ajustes)
        self._modelo = None
        self._candado = threading.Lock()  # dos trabajadores no deben cargarlo a la vez

    def _cargar(self):
        with self._candado:
            return self._cargar_sin_candado()

    def _cargar_sin_candado(self):
        if self._modelo is None:
            from fastembed import TextEmbedding

            log.info("cargando el modelo de búsqueda por tema %s (la primera vez se descarga)", self.modelo)
            self.ajustes.carpeta_modelos.mkdir(parents=True, exist_ok=True)
            self._modelo = TextEmbedding(self.modelo, cache_dir=str(self.ajustes.carpeta_modelos))
        return self._modelo

    async def _vectores(self, textos: list[str]) -> list[list[float]]:
        def calcular() -> list[list[float]]:
            return [v.tolist() for v in self._cargar().embed(textos)]

        try:
            return await asyncio.to_thread(calcular)  # en un hilo: no frena a las demás tareas
        except ValueError as error:  # modelo que fastembed no conoce
            raise ErrorIAPermanente(f"modelo de búsqueda no disponible: {error}") from None
        except OSError as error:  # no se pudo descargar
            raise ErrorIA(f"no se pudo cargar el modelo de búsqueda: {error}") from error


class OpenAICompat(ProveedorEmbeddings):
    nombre = "openai_compat"
    url_por_omision = ""

    def __init__(self, ajustes: AjustesBusqueda, transporte: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(ajustes)
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), transport=transporte)

    async def _vectores(self, textos: list[str]) -> list[list[float]]:
        url = (self.ajustes.url or self.url_por_omision).rstrip("/")
        if not url:
            raise ErrorIAPermanente("la búsqueda por tema necesita busqueda.url (la raíz /v1 del servidor)")
        llave = self.ajustes.llave.get_secret_value() if self.ajustes.llave else None
        try:
            r = await self.http.post(
                f"{url}/embeddings",
                json={"model": self.modelo, "input": textos},
                headers={"Authorization": f"Bearer {llave}"} if llave else {},
            )
        except httpx.TransportError as error:
            raise ErrorIA(f"sin respuesta del servidor de vectores: {error}") from error
        if r.status_code in (401, 403, 404):
            raise ErrorIAPermanente(f"el servidor de vectores respondió {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            raise ErrorIA(f"el servidor de vectores respondió {r.status_code}: {r.text[:200]}")
        datos = sorted(r.json().get("data", []), key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in datos]

    async def cerrar(self) -> None:
        await self.http.aclose()


class Ollama(OpenAICompat):
    nombre = "ollama"
    url_por_omision = "http://ollama:11434/v1"


class OpenAI(OpenAICompat):
    nombre = "openai"
    url_por_omision = "https://api.openai.com/v1"


_actual: ProveedorEmbeddings | None = None
_de_prueba: ProveedorEmbeddings | None = None


def activo() -> bool:
    return _de_prueba is not None or obtener_ajustes().busqueda.embeddings != "ninguno"


def obtener() -> ProveedorEmbeddings:
    global _actual
    if _de_prueba is not None:
        return _de_prueba
    if _actual is None:
        a = obtener_ajustes().busqueda
        clases = {"local": Local, "ollama": Ollama, "openai": OpenAI, "openai_compat": OpenAICompat}
        if a.embeddings not in clases:
            raise ErrorIAPermanente("la búsqueda por tema está apagada (busqueda.embeddings: ninguno)")
        _actual = clases[a.embeddings](a)
    return _actual


def usar_proveedor(proveedor: ProveedorEmbeddings | None) -> None:
    """Pruebas: reemplaza el proveedor del proceso."""
    global _de_prueba
    _de_prueba = proveedor
