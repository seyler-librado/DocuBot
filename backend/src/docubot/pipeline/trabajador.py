"""Proceso worker: corre N tareas a la vez por etapa, según config/docubot.yaml."""

import asyncio
import contextlib
import logging
import signal
import socket

from docubot import eventos, ia
from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Tarea
from docubot.db.sesion import fabrica_sesiones, obtener_motor
from docubot.pipeline import cola, corridas
from docubot.pipeline.errores import ErrorPermanente
from docubot.pipeline.etapas import ETAPAS, Etapa
from docubot.red import clientes

log = logging.getLogger("docubot.worker")

ESPERA_VACIA = 2.0  # segundos entre consultas cuando no hay trabajo
CADA_RECUPERAR = 60.0
CADA_LATIDO = 60.0


async def _dormir(parar: asyncio.Event, segundos: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(parar.wait(), segundos)


async def _latidos(tarea_id: int) -> None:
    while True:
        await asyncio.sleep(CADA_LATIDO)
        with contextlib.suppress(Exception):
            async with fabrica_sesiones()() as s:
                await cola.latido(s, tarea_id)
                await s.commit()


async def procesar_una(etapa: Etapa, tarea: Tarea, sesiones=None) -> str:
    """Corre una tarea ya tomada y deja su resultado en la cola. Devuelve el estado final."""
    sesiones = sesiones or fabrica_sesiones()
    if tarea.corrida_id is not None:
        async with sesiones() as s:
            if await corridas.estado_de(s, tarea.corrida_id) == "detenida":
                await cola.cancelar(s, tarea.id)
                await s.commit()
                return "cancelada"

    latido = asyncio.create_task(_latidos(tarea.id))
    try:
        async with sesiones() as s:
            await etapa.funcion(s, tarea)
            await cola.completar(s, tarea.id)
            await eventos.publicar(
                s, "tarea", etapa=etapa.nombre, estado="hecha", tarea_id=tarea.id, corrida_id=tarea.corrida_id
            )
            await s.commit()
        estado = "hecha"
    except Exception as error:
        permanente = isinstance(error, ErrorPermanente)
        async with sesiones() as s:
            estado = await cola.fallar(s, tarea.id, f"{type(error).__name__}: {error}", permanente=permanente)
            await eventos.publicar(
                s,
                "tarea",
                etapa=etapa.nombre,
                estado=estado,
                tarea_id=tarea.id,
                corrida_id=tarea.corrida_id,
                error=str(error)[:300],
            )
            await s.commit()
        nivel = logging.WARNING if estado == "pendiente" else logging.ERROR
        log.log(nivel, "tarea %s (%s) falló: %s -> %s", tarea.id, etapa.nombre, error, estado)
    finally:
        latido.cancel()

    if tarea.corrida_id is not None:
        async with sesiones() as s:
            if await corridas.revisar_fin(s, tarea.corrida_id):
                log.info("corrida %s terminada", tarea.corrida_id)
            await s.commit()
    return estado


async def _bucle(etapa: Etapa, nombre: str, parar: asyncio.Event) -> None:
    sesiones = fabrica_sesiones()
    while not parar.is_set():
        try:
            async with sesiones() as s:
                tareas = await cola.tomar(s, etapa.nombre, nombre)
                await s.commit()
        except Exception:
            log.exception("%s: no se pudo leer la cola", nombre)
            await _dormir(parar, ESPERA_VACIA * 5)
            continue
        if not tareas:
            await _dormir(parar, ESPERA_VACIA)
            continue
        try:
            await procesar_una(etapa, tareas[0], sesiones)
        except Exception:
            log.exception("%s: error inesperado con la tarea %s", nombre, tareas[0].id)


async def _recuperador(parar: asyncio.Event) -> None:
    while not parar.is_set():
        try:
            async with fabrica_sesiones()() as s:
                n = await cola.recuperar_huerfanas(s)
                await s.commit()
            if n:
                log.info("se devolvieron %s tareas huérfanas a la cola", n)
        except Exception:
            log.exception("no se pudieron recuperar tareas huérfanas")
        await _dormir(parar, CADA_RECUPERAR)


def _cuantos(etapa: Etapa) -> int:
    if etapa.trabajadores is None:
        return 1
    return getattr(obtener_ajustes().trabajadores, etapa.trabajadores)


async def correr() -> None:
    parar = asyncio.Event()
    bucle = asyncio.get_running_loop()
    for senal in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows no las soporta
            bucle.add_signal_handler(senal, parar.set)

    host = socket.gethostname()
    tareas = [asyncio.create_task(_recuperador(parar))]
    for etapa in ETAPAS.values():
        n = _cuantos(etapa)
        for i in range(n):
            nombre = f"{host}/{etapa.nombre}-{i + 1}"
            tareas.append(asyncio.create_task(_bucle(etapa, nombre, parar)))
        log.info("etapa %-15s %s trabajador(es)", etapa.nombre, n)

    log.info("worker listo")
    await parar.wait()
    log.info("deteniendo: se terminan las tareas en curso")
    await asyncio.gather(*tareas, return_exceptions=True)
    await clientes.cerrar_todos()
    await ia.cerrar()
    await obtener_motor().dispose()
