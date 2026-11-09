"""Eventos en vivo: el worker avisa lo que pasa y la interfaz se entera al instante.

- `publicar(sesion, tipo, **datos)` manda un NOTIFY de Postgres dentro de la
  transacción en curso: el aviso sale cuando esta se confirma (si se deshace,
  no sale). Sirve desde cualquier proceso (worker o API).
- `difusor` (en la API) escucha ese canal con LISTEN y reparte cada evento a
  las conexiones WebSocket abiertas.
"""

import asyncio
import contextlib
import json
import logging
from typing import Any

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.ajustes import obtener_ajustes

log = logging.getLogger("docubot.eventos")

CANAL = "docubot_eventos"
MAX_BYTES = 7000  # NOTIFY admite hasta 8000 bytes


async def publicar(sesion: AsyncSession, tipo: str, **datos: Any) -> None:
    carga = json.dumps({"tipo": tipo, **datos}, ensure_ascii=False, default=str)
    if len(carga.encode()) > MAX_BYTES:
        carga = json.dumps(
            {"tipo": tipo, **{k: v for k, v in datos.items() if not isinstance(v, str) or len(v) < 200}}, default=str
        )
    await sesion.execute(text("SELECT pg_notify(:canal, :carga)"), {"canal": CANAL, "carga": carga})


class Difusor:
    """Una sola conexión LISTEN por proceso de API; cada suscriptor recibe una cola."""

    def __init__(self) -> None:
        self.suscriptores: set[asyncio.Queue[str]] = set()
        self._tarea: asyncio.Task | None = None
        self.conectado = False

    def iniciar(self) -> None:
        if self._tarea is None or self._tarea.done():
            self._tarea = asyncio.create_task(self._escuchar())

    async def detener(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._tarea
            self._tarea = None

    def suscribir(self) -> asyncio.Queue[str]:
        cola: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self.suscriptores.add(cola)
        return cola

    def cancelar(self, cola: asyncio.Queue[str]) -> None:
        self.suscriptores.discard(cola)

    def repartir(self, carga: str) -> None:
        for cola in list(self.suscriptores):
            if cola.full():  # un cliente lento no frena a los demás: pierde lo más viejo
                with contextlib.suppress(asyncio.QueueEmpty):
                    cola.get_nowait()
            cola.put_nowait(carga)

    async def _escuchar(self) -> None:
        url = obtener_ajustes().base_datos_url.replace("postgresql+psycopg://", "postgresql://")
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conexion:
                    await conexion.execute(f"LISTEN {CANAL}")
                    self.conectado = True
                    async for aviso in conexion.notifies():
                        self.repartir(aviso.payload)
            except asyncio.CancelledError:
                self.conectado = False
                raise
            except Exception as error:
                self.conectado = False
                log.warning("eventos: se perdió la conexión con la base (%s); reintento en 3 s", error)
                await asyncio.sleep(3)


difusor = Difusor()
