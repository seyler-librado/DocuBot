"""Fichas: la cola de revisión."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.api.documentos import titulo_de
from docubot.db.modelos import Candidato, Documento, Ficha, Perfil
from docubot.db.sesion import sesion_api

ruta = APIRouter(prefix="/api/fichas", tags=["fichas"])


@ruta.get("")
async def listar(
    estado: str | None = Query("revision", description="ok | revision | ilegible | error (vacío = todas)"),
    perfil: str | None = None,
    limite: int = Query(50, ge=1, le=500),
    desde: int = Query(0, ge=0),
    sesion: AsyncSession = Depends(sesion_api),
) -> dict[str, Any]:
    filtro = []
    if estado:
        filtro.append(Ficha.estado == estado)
    if perfil:
        filtro.append(Perfil.nombre == perfil)
    base = (
        select(Ficha, Perfil.nombre, Documento)
        .join(Perfil, Perfil.id == Ficha.perfil_id)
        .join(Documento, Documento.id == Ficha.documento_id)
        .where(*filtro)
    )
    total = await sesion.scalar(select(func.count()).select_from(base.subquery()))
    filas = (await sesion.execute(base.order_by(Ficha.actualizado.desc()).offset(desde).limit(limite))).all()
    urls = {
        d: u
        for d, u in await sesion.execute(
            select(Candidato.documento_id, func.min(Candidato.url))
            .where(Candidato.documento_id.in_([f.documento_id for f, _, _ in filas]))
            .group_by(Candidato.documento_id)
        )
    }
    return {
        "total": total,
        "elementos": [
            {
                "documento_id": f.documento_id,
                "perfil": nombre,
                "estado": f.estado,
                "confianza": f.confianza,
                "motivos": f.motivos,
                "titulo": titulo_de(f.campos),
                "paginas": d.paginas,
                "url": urls.get(f.documento_id),
                "tipo_ia": (f.control or {}).get("tipo_ia"),
                "tipo_esperado": (f.control or {}).get("tipo_esperado"),
                "actualizado": f.actualizado,
            }
            for f, nombre, d in filas
        ],
    }
