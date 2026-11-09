"""Aplicación FastAPI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from docubot import __version__
from docubot.ajustes import obtener_ajustes
from docubot.api import busqueda, candidatos, corridas, documentos, eventos, fichas, ia, lugares, perfiles, sistema
from docubot.db.sesion import fabrica_sesiones, obtener_motor
from docubot.eventos import difusor
from docubot.geo.catalogo import importar as importar_catalogo
from docubot.perfiles import cargar_todos
from docubot.perfiles.sincronizar import sincronizar

log = logging.getLogger("docubot.api")


async def _sincronizar_perfiles() -> None:
    """Al arrancar, copia a la base los perfiles válidos. Si falla, la API arranca igual."""
    try:
        cargados = cargar_todos(obtener_ajustes().carpeta_perfiles)
        async with fabrica_sesiones()() as s:
            r = await sincronizar(s, cargados)
            await s.commit()
            for c in cargados:  # catálogos de lugares (no se reimportan si no cambiaron)
                if c.valido and c.perfil.geografia is not None:
                    try:
                        await importar_catalogo(s, c.perfil.geografia, c.carpeta)
                        await s.commit()
                    except Exception:
                        await s.rollback()
                        log.exception("no se pudo importar el catálogo de lugares de %s", c.nombre)
        log.info(
            "perfiles: %s nuevos, %s actualizados, %s sin cambios, %s con errores",
            len(r.creados),
            len(r.actualizados),
            len(r.sin_cambios),
            len(r.invalidos),
        )
        for nombre, errores in r.invalidos.items():
            log.warning("perfil %s con errores: %s", nombre, "; ".join(errores))
    except Exception:
        log.exception("no se pudieron sincronizar los perfiles")


@asynccontextmanager
async def vida(app: FastAPI):
    await _sincronizar_perfiles()
    difusor.iniciar()
    yield
    await difusor.detener()
    await obtener_motor().dispose()


app = FastAPI(
    title="DocuBot",
    version=__version__,
    description="Descubre, descarga y cataloga documentos públicos según perfiles configurables.",
    lifespan=vida,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(sistema.ruta)
app.include_router(perfiles.ruta)
app.include_router(corridas.ruta)
app.include_router(documentos.ruta)
app.include_router(ia.ruta)
app.include_router(fichas.ruta)
app.include_router(candidatos.ruta)
app.include_router(eventos.ruta)
app.include_router(lugares.ruta)
app.include_router(busqueda.ruta)
