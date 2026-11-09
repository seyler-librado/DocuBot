"""Búsqueda dentro de los documentos."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.ajustes import obtener_ajustes
from docubot.api.documentos import _resumenes, filtrar
from docubot.busqueda import buscar as B
from docubot.busqueda import embeddings
from docubot.db.modelos import Documento, Fragmento, Texto
from docubot.db.sesion import sesion_api
from docubot.pipeline import procesar

ruta = APIRouter(prefix="/api", tags=["búsqueda"])


@ruta.get("/buscar")
async def buscar(
    q: str = Query(..., min_length=2, description='palabras, "frase exacta", -excluida, a OR b'),
    modo: Literal["mixta", "palabras", "tema"] = "mixta",
    perfil: str | None = None,
    corrida: int | None = None,
    tipo: str | None = None,
    ficha: str | None = None,
    lugar: int | None = None,
    limite: int = Query(20, ge=1, le=100),
    desde: int = Query(0, ge=0),
    sesion: AsyncSession = Depends(sesion_api),
) -> dict[str, Any]:
    ids: list[int] | None = None
    if any((perfil, corrida, tipo, ficha, lugar)):
        sub = await filtrar(sesion, perfil, corrida, tipo, ficha, None, lugar)
        ids = list(await sesion.scalars(select(sub.c.documento_id)))
    try:
        modo_usado, total, resultados = await B.buscar(sesion, q.strip(), modo, ids, limite, desde)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    documentos = {
        d.id: d
        for d in await sesion.scalars(select(Documento).where(Documento.id.in_([r.documento_id for r in resultados])))
    }
    resumenes = {
        r["id"]: r
        for r in await _resumenes(
            sesion, [documentos[r.documento_id] for r in resultados if r.documento_id in documentos]
        )
    }
    return {
        "modo": modo_usado,
        "total": total,
        "elementos": [resumenes[r.documento_id] | B.a_dict(r) for r in resultados if r.documento_id in resumenes],
    }


@ruta.get("/busqueda/estado")
async def estado(sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    a = obtener_ajustes().busqueda
    con_texto = await sesion.scalar(select(func.count()).where(Texto.metodo == "texto"))
    datos: dict[str, Any] = {
        "palabras": {"documentos": con_texto},
        "tema": {"activa": embeddings.activo(), "proveedor": a.embeddings},
    }
    if embeddings.activo():
        modelo = embeddings.obtener().modelo
        fragmentos, indexados = (
            await sesion.execute(
                select(func.count(), func.count(func.distinct(Fragmento.documento_id))).where(
                    Fragmento.modelo == modelo
                )
            )
        ).one()
        datos["tema"] |= {
            "modelo": modelo,
            "fragmentos": fragmentos,
            "documentos": indexados,
            "faltan": max(0, con_texto - indexados),
        }
    return datos


async def encolar_faltantes(sesion: AsyncSession, rehacer: bool = False) -> int:
    if not embeddings.activo():
        return 0
    modelo = embeddings.obtener().modelo
    consulta = select(Texto.documento_id).where(Texto.metodo == "texto")
    if not rehacer:
        consulta = consulta.where(
            ~exists().where(Fragmento.documento_id == Texto.documento_id, Fragmento.modelo == modelo)
        )
    n = 0
    for documento_id in await sesion.scalars(consulta):
        n += await procesar.encolar_indexado(sesion, documento_id, None)
    return n


@ruta.post("/busqueda/indexar")
async def indexar(rehacer: bool = False, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    """Encola los vectores de los documentos que no los tengan (o de todos, con rehacer)."""
    if not embeddings.activo():
        raise HTTPException(422, "la búsqueda por tema está apagada (busqueda.embeddings en config/docubot.yaml)")
    n = await encolar_faltantes(sesion, rehacer)
    await sesion.commit()
    return {"encolados": n}
