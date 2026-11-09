"""Etapa de prueba: escribe el mensaje en la bitácora.

Sirve para comprobar que la cola y el worker funcionan (docubot eco "hola").
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Tarea

log = logging.getLogger("docubot.eco")


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    if tarea.carga.get("fallar"):
        raise RuntimeError("fallo pedido en la carga")
    log.info("eco #%s: %s", tarea.id, tarea.carga.get("mensaje", ""))
