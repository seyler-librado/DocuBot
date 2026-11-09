"""Qué sigue para un documento: extraer su texto y hacer sus fichas (una por perfil)."""

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import ia
from docubot.db.modelos import Candidato, DocumentoLugar, Ficha, Texto
from docubot.perfiles.esquema import Perfil
from docubot.pipeline import cola


def hace_fichas(perfil: Perfil) -> bool:
    return perfil.fichas.ia and bool(perfil.fichas.campos or perfil.documentos.tipos) and ia.activo()


async def encolar_extraccion(sesion: AsyncSession, documento_id: int, corrida_id: int | None) -> bool:
    return await cola.encolar_unica(
        sesion, "extraer", f"extraer:{documento_id}", {"documento_id": documento_id}, corrida_id=corrida_id
    )


async def encolar_ficha(sesion: AsyncSession, documento_id: int, perfil_id: int, corrida_id: int | None) -> bool:
    return await cola.encolar_unica(
        sesion,
        "fichar",
        f"fichar:{documento_id}:{perfil_id}",
        {"documento_id": documento_id, "perfil_id": perfil_id},
        corrida_id=corrida_id,
    )


async def encolar_ubicacion(sesion: AsyncSession, documento_id: int, perfil_id: int, corrida_id: int | None) -> bool:
    return await cola.encolar_unica(
        sesion,
        "ubicar",
        f"ubicar:{documento_id}:{perfil_id}",
        {"documento_id": documento_id, "perfil_id": perfil_id},
        corrida_id=corrida_id,
    )


async def encolar_indexado(sesion: AsyncSession, documento_id: int, corrida_id: int | None) -> bool:
    return await cola.encolar_unica(
        sesion, "indexar", f"indexar:{documento_id}", {"documento_id": documento_id}, corrida_id=corrida_id
    )


async def siguiente(
    sesion: AsyncSession, documento_id: int, perfil_id: int, perfil: Perfil, corrida_id: int | None
) -> str | None:
    """Encola lo que le falta a un documento para este perfil. Devuelve qué encoló."""
    tiene_texto = await sesion.scalar(select(exists().where(Texto.documento_id == documento_id)))
    if not tiene_texto:
        return "extraer" if await encolar_extraccion(sesion, documento_id, corrida_id) else None
    if hace_fichas(perfil):
        tiene_ficha = await sesion.scalar(
            select(exists().where(Ficha.documento_id == documento_id, Ficha.perfil_id == perfil_id))
        )
        if not tiene_ficha:
            return "fichar" if await encolar_ficha(sesion, documento_id, perfil_id, corrida_id) else None
    if perfil.geografia is not None:
        ubicado = await sesion.scalar(
            select(
                exists().where(
                    DocumentoLugar.documento_id == documento_id,
                    DocumentoLugar.catalogo == perfil.geografia.identificador,
                )
            )
        )
        if not ubicado:
            return "ubicar" if await encolar_ubicacion(sesion, documento_id, perfil_id, corrida_id) else None
    return None


async def ubicar_corrida(sesion: AsyncSession, corrida_id: int, perfil: Perfil) -> int:
    """Vuelve a ubicar todos los documentos de la corrida que tienen texto (p. ej. tras cambiar el catálogo).

    Lo que una persona eligió a mano se respeta.
    """
    if perfil.geografia is None:
        return 0
    filas = (
        await sesion.execute(
            select(Candidato.documento_id, Candidato.perfil_id)
            .join(Texto, Texto.documento_id == Candidato.documento_id)
            .where(Candidato.corrida_id == corrida_id)
            .distinct()
        )
    ).all()
    n = 0
    for documento_id, perfil_id in filas:
        n += await encolar_ubicacion(sesion, documento_id, perfil_id, corrida_id)
    return n


async def completar_corrida(
    sesion: AsyncSession, corrida_id: int, perfil: Perfil, *, rehacer: bool = False
) -> dict[str, int]:
    """Encola extracción y fichas para los documentos de una corrida que no las tengan.

    Con rehacer=True vuelve a hacer las fichas aunque ya existan.
    """
    filas = (
        await sesion.execute(
            select(Candidato.documento_id, Candidato.perfil_id)
            .where(Candidato.corrida_id == corrida_id, Candidato.documento_id.is_not(None))
            .distinct()
        )
    ).all()
    cuenta = {"extraer": 0, "fichar": 0, "ubicar": 0}
    for documento_id, perfil_id in filas:
        if rehacer and hace_fichas(perfil):
            tiene_texto = await sesion.scalar(select(exists().where(Texto.documento_id == documento_id)))
            if tiene_texto:
                cuenta["fichar"] += await encolar_ficha(sesion, documento_id, perfil_id, corrida_id)
                continue
        hecho = await siguiente(sesion, documento_id, perfil_id, perfil, corrida_id)
        if hecho:
            cuenta[hecho] += 1
    return cuenta
