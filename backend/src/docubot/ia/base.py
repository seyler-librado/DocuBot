"""Interfaz común de los proveedores de IA.

Un proveedor recibe instrucciones (sistema), el turno del usuario y, si el
documento está escaneado, imágenes JPEG de sus páginas. Devuelve el texto de
la respuesta. Nada más: sin historial, sin herramientas.

Para escribir uno propio, ver config/extensiones/README.md.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from docubot.ajustes import AjustesIA
from docubot.pipeline.errores import ErrorPermanente

log = logging.getLogger("docubot.ia")


class ErrorIA(Exception):
    """Falla pasajera (sin conexión, servidor saturado...): vale la pena reintentar."""


class ErrorIAPermanente(ErrorIA, ErrorPermanente):
    """Reintentar no sirve: llave inválida, modelo inexistente, petición mal formada."""


class Desborde(ErrorIA):
    """La petición no cabe en la ventana del modelo: hay que recortar el texto."""


@dataclass
class Respuesta:
    texto: str
    modelo: str = ""
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    segundos: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class Proveedor(ABC):
    nombre: str = "?"
    vision: bool = False  # ¿acepta imágenes?
    espera_reintento: float = 3.0  # segundos antes del primer reintento (luego se duplica)

    def __init__(self, ajustes: AjustesIA, transporte: httpx.AsyncBaseTransport | None = None) -> None:
        self.ajustes = ajustes
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(ajustes.timeout, connect=15.0),
            transport=transporte,
        )

    @property
    def modelo(self) -> str:
        return self.ajustes.modelo

    @property
    def llave(self) -> str | None:
        return self.ajustes.llave.get_secret_value() if self.ajustes.llave else None

    @abstractmethod
    async def _completar(self, sistema: str, usuario: str, imagenes: list[str]) -> Respuesta:
        """Una petición. `imagenes` son JPEG en base64."""

    async def completar(self, sistema: str, usuario: str, imagenes: list[str] | None = None) -> Respuesta:
        """Pide una respuesta, con reintentos ante fallas pasajeras."""
        imagenes = list(imagenes or [])
        if imagenes and not (self.vision and self.ajustes.vision):
            raise ErrorIAPermanente(f"el proveedor {self.nombre} no está configurado para leer imágenes")
        intentos = self.ajustes.reintentos + 1
        for intento in range(intentos):
            inicio = time.monotonic()
            try:
                r = await self._completar(sistema, usuario, imagenes)
                r.segundos = round(time.monotonic() - inicio, 1)
                return r
            except (ErrorIAPermanente, Desborde):
                raise
            except (ErrorIA, httpx.TransportError) as error:
                if intento + 1 >= intentos:
                    if isinstance(error, httpx.TransportError):
                        raise ErrorIA(f"sin respuesta de {self.nombre}: {type(error).__name__}: {error}") from error
                    raise
                log.info("%s falló (%s); reintento", self.nombre, error)
                await asyncio.sleep(self.espera_reintento * 2**intento)
        raise ErrorIA("sin respuesta")  # no se llega aquí

    async def salud(self) -> dict[str, Any]:
        """¿Responde? {ok, modelo, modelos?, detalle}. Nunca lanza."""
        return {"ok": None, "modelo": self.modelo, "detalle": "este proveedor no informa su estado"}

    async def cerrar(self) -> None:
        await self.http.aclose()

    # --- utilidades para los proveedores ---------------------------------------

    def revisar_estado(self, r: httpx.Response) -> None:
        """Convierte un error HTTP en el error de IA que corresponde."""
        if r.status_code < 400:
            return
        detalle = r.text[:300]
        if r.status_code == 413 or "context" in detalle.lower() and "length" in detalle.lower():
            raise Desborde(f"{self.nombre}: la petición no cabe ({r.status_code}): {detalle}")
        if r.status_code in (408, 409, 425, 429) or r.status_code >= 500:
            raise ErrorIA(f"{self.nombre} respondió {r.status_code}: {detalle}")
        if r.status_code in (401, 403):
            raise ErrorIAPermanente(f"{self.nombre} rechazó la llave ({r.status_code}): {detalle}")
        raise ErrorIAPermanente(f"{self.nombre} respondió {r.status_code}: {detalle}")
