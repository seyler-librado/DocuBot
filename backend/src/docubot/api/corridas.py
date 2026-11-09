"""Corridas: lanzar un perfil, ver su avance, detener, reanudar, ver lo encontrado."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos
from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Corrida, CorridaSitio, Sitio, Tarea
from docubot.db.sesion import sesion_api
from docubot.perfiles import cargar_todos
from docubot.pipeline import corridas, descargas, procesar

ruta = APIRouter(prefix="/api/corridas", tags=["corridas"])


class NuevaCorrida(BaseModel):
    perfil: str
    fuentes: list[int] | None = None  # índices de descubrimiento.fuentes; si no, todas
    descargar: bool = True  # bajar los candidatos aceptados conforme aparecen
    ajustes: corridas.CambiosCorrida | None = None  # cambios solo para esta corrida


async def _corrida(sesion: AsyncSession, corrida_id: int) -> Corrida:
    corrida = await sesion.get(Corrida, corrida_id)
    if corrida is None:
        raise HTTPException(404, f"no existe la corrida {corrida_id}")
    return corrida


@ruta.post("", status_code=201)
async def crear(datos: NuevaCorrida, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    cargado = next((c for c in cargar_todos(obtener_ajustes().carpeta_perfiles) if c.nombre == datos.perfil), None)
    if cargado is None:
        raise HTTPException(404, f"no hay un perfil llamado '{datos.perfil}'")
    try:
        corrida = await corridas.crear(sesion, cargado, datos.fuentes, descargar=datos.descargar, cambios=datos.ajustes)
    except corridas.ErrorCorrida as error:
        raise HTTPException(422, str(error)) from None
    await eventos.publicar(sesion, "corrida", corrida_id=corrida.id, estado="corriendo")
    await sesion.commit()
    return await corridas.resumen(sesion, corrida)


@ruta.get("")
async def listar(
    limite: int = Query(20, ge=1, le=200), sesion: AsyncSession = Depends(sesion_api)
) -> list[dict[str, Any]]:
    filas = (await sesion.scalars(select(Corrida).order_by(Corrida.id.desc()).limit(limite))).all()
    return [await corridas.resumen(sesion, c) for c in filas]


@ruta.get("/{corrida_id}")
async def detalle(corrida_id: int, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    return await corridas.resumen(sesion, await _corrida(sesion, corrida_id))


@ruta.post("/{corrida_id}/detener")
async def detener(corrida_id: int, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    await _corrida(sesion, corrida_id)
    canceladas = await corridas.detener(sesion, corrida_id)
    await eventos.publicar(sesion, "corrida", corrida_id=corrida_id, estado="detenida")
    await sesion.commit()
    return {"canceladas": canceladas}


@ruta.post("/{corrida_id}/reanudar")
async def reanudar(
    corrida_id: int, reintentar_fallidas: bool = False, sesion: AsyncSession = Depends(sesion_api)
) -> dict[str, Any]:
    await _corrida(sesion, corrida_id)
    n = await corridas.reanudar(sesion, corrida_id, reintentar_fallidas)
    await eventos.publicar(sesion, "corrida", corrida_id=corrida_id, estado="corriendo")
    await sesion.commit()
    return {"reanudadas": n}


@ruta.post("/{corrida_id}/descargar")
async def descargar(
    corrida_id: int,
    limite: int | None = Query(None, ge=1),
    fallidos: bool = False,
    sesion: AsyncSession = Depends(sesion_api),
) -> dict[str, Any]:
    """Encola la descarga de los aceptados que falten (y, con fallidos=true, reintenta los fallidos)."""
    await _corrida(sesion, corrida_id)
    n = await descargas.descargar_corrida(sesion, corrida_id, limite=limite, incluir_fallidos=fallidos)
    await sesion.commit()
    return {"encoladas": n}


@ruta.post("/{corrida_id}/fichas")
async def fichas(corrida_id: int, rehacer: bool = False, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    """Encola extracción de texto y fichas para los documentos de la corrida que no las tengan."""
    corrida = await _corrida(sesion, corrida_id)
    cuenta = await procesar.completar_corrida(
        sesion, corrida_id, await corridas.perfil_actual(sesion, corrida), rehacer=rehacer
    )
    if sum(cuenta.values()):
        await corridas.reabrir(sesion, corrida_id)
    await sesion.commit()
    return cuenta


@ruta.get("/{corrida_id}/fallas")
async def fallas(corrida_id: int, sesion: AsyncSession = Depends(sesion_api)) -> list[dict[str, Any]]:
    """Las tareas que fallaron de forma definitiva, con su error."""
    filas = await sesion.scalars(
        select(Tarea)
        .where(Tarea.corrida_id == corrida_id, Tarea.estado == "fallida")
        .order_by(Tarea.terminada.desc().nulls_last())
        .limit(200)
    )
    return [
        {
            "id": t.id,
            "etapa": t.etapa,
            "error": t.error,
            "intentos": t.intentos,
            "carga": t.carga,
            "terminada": t.terminada,
        }
        for t in filas
    ]


@ruta.post("/{corrida_id}/lugares")
async def lugares(corrida_id: int, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    """Vuelve a ubicar los documentos de la corrida con el catálogo actual del perfil."""
    corrida = await _corrida(sesion, corrida_id)
    n = await procesar.ubicar_corrida(sesion, corrida_id, await corridas.perfil_actual(sesion, corrida))
    if n:
        await corridas.reabrir(sesion, corrida_id)
    await sesion.commit()
    return {"encoladas": n}


@ruta.get("/{corrida_id}/sitios")
async def sitios(
    corrida_id: int,
    estado: str | None = None,
    limite: int = Query(100, ge=1, le=1000),
    desde: int = Query(0, ge=0),
    sesion: AsyncSession = Depends(sesion_api),
) -> list[dict[str, Any]]:
    consulta = (
        select(CorridaSitio, Sitio.dominio)
        .join(Sitio, Sitio.id == CorridaSitio.sitio_id)
        .where(CorridaSitio.corrida_id == corrida_id)
        .order_by(CorridaSitio.documentos.desc(), Sitio.dominio)
        .offset(desde)
        .limit(limite)
    )
    if estado:
        consulta = consulta.where(CorridaSitio.estado == estado)
    return [
        {
            "sitio_id": cs.sitio_id,
            "dominio": dominio,
            "estado": cs.estado,
            "origen": cs.origen,
            "lugar": cs.lugar,
            "paginas": cs.paginas,
            "documentos": cs.documentos,
            "segundos": cs.segundos,
            "error": cs.error,
        }
        for cs, dominio in await sesion.execute(consulta)
    ]


@ruta.get("/{corrida_id}/candidatos")
async def candidatos(
    corrida_id: int,
    fuente: str | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    limite: int = Query(100, ge=1, le=1000),
    desde: int = Query(0, ge=0),
    sesion: AsyncSession = Depends(sesion_api),
) -> list[dict[str, Any]]:
    consulta = (
        select(Candidato)
        .where(Candidato.corrida_id == corrida_id)
        .order_by(Candidato.puntaje.desc().nulls_last(), Candidato.id)
        .offset(desde)
        .limit(limite)
    )
    if fuente:
        consulta = consulta.where(Candidato.fuente == fuente)
    if tipo:
        consulta = consulta.where(Candidato.tipo == tipo)
    if estado:
        consulta = consulta.where(Candidato.estado == estado)
    return [
        {
            "id": c.id,
            "url": c.url,
            "fuente": c.fuente,
            "tipo": c.tipo,
            "puntaje": c.puntaje,
            "motivo": c.motivo,
            "documento_id": c.documento_id,
            "ancla": c.ancla,
            "pagina_origen": c.pagina_origen,
            "estado": c.estado,
            "datos": c.datos,
        }
        for c in await sesion.scalars(consulta)
    ]
