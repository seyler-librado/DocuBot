"""Candidatos: buscar entre todo lo encontrado y aceptar o rechazar a mano."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Candidato, Perfil
from docubot.db.sesion import sesion_api
from docubot.pipeline import corridas, descargas

ruta = APIRouter(prefix="/api/candidatos", tags=["candidatos"])


def _a_dict(c: Candidato, perfil: str) -> dict[str, Any]:
    return {
        "id": c.id,
        "perfil": perfil,
        "corrida_id": c.corrida_id,
        "url": c.url,
        "fuente": c.fuente,
        "tipo": c.tipo,
        "puntaje": c.puntaje,
        "estado": c.estado,
        "motivo": c.motivo,
        "ancla": c.ancla,
        "pagina_origen": c.pagina_origen,
        "documento_id": c.documento_id,
        "nuevo": (c.datos or {}).get("nuevo"),
        "lugar": (c.datos or {}).get("lugar"),
        "actualizado": c.actualizado,
    }


@ruta.get("")
async def listar(
    perfil: str | None = None,
    corrida: int | None = None,
    estado: str | None = None,
    tipo: str | None = None,
    fuente: str | None = None,
    q: str | None = None,
    limite: int = Query(50, ge=1, le=500),
    desde: int = Query(0, ge=0),
    sesion: AsyncSession = Depends(sesion_api),
) -> dict[str, Any]:
    filtro = []
    if perfil:
        filtro.append(Perfil.nombre == perfil)
    if corrida:
        filtro.append(Candidato.corrida_id == corrida)
    if estado:
        filtro.append(Candidato.estado == estado)
    if tipo:
        filtro.append(Candidato.tipo == tipo)
    if fuente:
        filtro.append(Candidato.fuente == fuente)
    if q:
        patron = f"%{q.strip()}%"
        filtro.append(or_(Candidato.url.ilike(patron), Candidato.ancla.ilike(patron)))
    base = select(Candidato, Perfil.nombre).join(Perfil, Perfil.id == Candidato.perfil_id).where(*filtro)
    total = await sesion.scalar(select(func.count()).select_from(base.subquery()))
    filas = await sesion.execute(
        base.order_by(Candidato.puntaje.desc().nulls_last(), Candidato.id.desc()).offset(desde).limit(limite)
    )
    return {"total": total, "elementos": [_a_dict(c, p) for c, p in filas]}


class CambioCandidato(BaseModel):
    estado: Literal["aceptado", "rechazado"]


@ruta.patch("/{candidato_id}")
async def cambiar(
    candidato_id: int, cambio: CambioCandidato, sesion: AsyncSession = Depends(sesion_api)
) -> dict[str, Any]:
    """Acepta (y encola su descarga) o rechaza un candidato a mano."""
    fila = (
        await sesion.execute(
            select(Candidato, Perfil.nombre)
            .join(Perfil, Perfil.id == Candidato.perfil_id)
            .where(Candidato.id == candidato_id)
        )
    ).first()
    if fila is None:
        raise HTTPException(404, f"no existe el candidato {candidato_id}")
    c, perfil = fila
    if c.estado == "descargado" and cambio.estado == "rechazado":
        raise HTTPException(409, "ya está descargado")
    c.estado = cambio.estado
    c.motivo = "a mano"
    encolada = 0
    if cambio.estado == "aceptado" and c.documento_id is None:
        encolada = await descargas.encolar(sesion, c.corrida_id, [(c.id, c.puntaje or 0)])
        if encolada and c.corrida_id:
            await corridas.reabrir(sesion, c.corrida_id)
    await sesion.commit()
    return _a_dict(c, perfil) | {"descarga_encolada": bool(encolada)}
