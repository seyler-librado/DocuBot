"""Documentos descargados: biblioteca, detalle, archivo, portada y edición de fichas."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos
from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Documento, DocumentoLugar, Ficha, Lugar, Perfil, Texto
from docubot.db.sesion import sesion_api
from docubot.documentos import pdf
from docubot.documentos.almacen import Almacen
from docubot.ia import fichas as F
from docubot.pipeline import corridas, procesar

ruta = APIRouter(prefix="/api/documentos", tags=["documentos"])

CAMPOS_TITULO = ("titulo", "nombre", "title")


def titulo_de(campos: dict[str, Any] | None) -> str | None:
    campos = campos or {}
    return next((str(campos[k]) for k in CAMPOS_TITULO if campos.get(k)), None)


def _almacen() -> Almacen:
    return Almacen(obtener_ajustes().almacen.carpeta)


async def _documento(sesion: AsyncSession, documento_id: int) -> Documento:
    documento = await sesion.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(404, f"no existe el documento {documento_id}")
    return documento


async def filtrar(
    sesion: AsyncSession,
    perfil: str | None = None,
    corrida: int | None = None,
    tipo: str | None = None,
    ficha: str | None = None,
    q: str | None = None,
    lugar: int | None = None,
):
    """Subconsulta con los ids de documento que cumplen los filtros (columna documento_id)."""
    ids = select(Candidato.documento_id).where(Candidato.documento_id.is_not(None))
    if perfil:
        ids = ids.join(Perfil, Perfil.id == Candidato.perfil_id).where(Perfil.nombre == perfil)
    if corrida:
        ids = ids.where(Candidato.corrida_id == corrida)
    if tipo:
        ids = ids.where(Candidato.tipo == tipo)
    if ficha == "sin":
        ids = ids.where(~select(Ficha.id).where(Ficha.documento_id == Candidato.documento_id).exists())
    elif ficha:
        ids = ids.where(
            select(Ficha.id).where(Ficha.documento_id == Candidato.documento_id, Ficha.estado == ficha).exists()
        )
    if q:
        patron = f"%{q.strip()}%"
        ids = ids.where(
            or_(
                Candidato.url.ilike(patron),
                Candidato.ancla.ilike(patron),
                select(Ficha.id)
                .where(Ficha.documento_id == Candidato.documento_id, cast(Ficha.campos, String).ilike(patron))
                .exists(),
            )
        )
    if lugar:
        contenidos = [lugar]
        pendientes = [lugar]
        while pendientes:  # el lugar y todos los que contiene (estado → municipios)
            hijos = list(await sesion.scalars(select(Lugar.id).where(Lugar.padre_id.in_(pendientes))))
            contenidos += hijos
            pendientes = hijos
        ids = ids.where(
            select(DocumentoLugar.id)
            .where(DocumentoLugar.documento_id == Candidato.documento_id, DocumentoLugar.lugar_id.in_(contenidos))
            .exists()
        )
    return ids.distinct().subquery()


@ruta.get("")
async def listar(
    perfil: str | None = None,
    corrida: int | None = None,
    tipo: str | None = None,
    ficha: str | None = Query(None, description="ok | revision | ilegible | error | sin"),
    q: str | None = Query(None, description="busca en título, campos de la ficha, URL y texto del enlace"),
    lugar: int | None = Query(None, description="id del lugar (incluye los lugares que contiene)"),
    limite: int = Query(24, ge=1, le=200),
    desde: int = Query(0, ge=0),
    sesion: AsyncSession = Depends(sesion_api),
) -> dict[str, Any]:
    ids = await filtrar(sesion, perfil, corrida, tipo, ficha, q, lugar)
    total = await sesion.scalar(select(func.count()).select_from(ids))
    pagina = (
        await sesion.scalars(
            select(Documento)
            .where(Documento.id.in_(select(ids.c.documento_id)))
            .order_by(Documento.id.desc())
            .offset(desde)
            .limit(limite)
        )
    ).all()
    return {"total": total, "elementos": await _resumenes(sesion, pagina)}


async def _resumenes(sesion: AsyncSession, documentos: list[Documento]) -> list[dict[str, Any]]:
    if not documentos:
        return []
    ids = [d.id for d in documentos]
    fuentes: dict[int, dict[str, Any]] = {}
    for c in await sesion.scalars(
        select(Candidato).where(Candidato.documento_id.in_(ids)).order_by(Candidato.puntaje.desc().nulls_last())
    ):
        fuentes.setdefault(
            c.documento_id, {"url": c.url, "tipo": c.tipo, "ancla": c.ancla, "nuevo": (c.datos or {}).get("nuevo")}
        )
    fichas: dict[int, dict[str, Any]] = {}
    for f, nombre in await sesion.execute(
        select(Ficha, Perfil.nombre).join(Perfil, Perfil.id == Ficha.perfil_id).where(Ficha.documento_id.in_(ids))
    ):
        fichas.setdefault(
            f.documento_id,
            {"perfil": nombre, "estado": f.estado, "confianza": f.confianza, "titulo": titulo_de(f.campos)},
        )
    return [
        {
            "id": d.id,
            "bytes": d.bytes,
            "paginas": d.paginas,
            "estado": d.estado,
            "mime": d.mime,
            "creado": d.creado,
            "url": fuentes.get(d.id, {}).get("url"),
            "tipo": fuentes.get(d.id, {}).get("tipo"),
            "ancla": fuentes.get(d.id, {}).get("ancla"),
            "nuevo": fuentes.get(d.id, {}).get("nuevo"),
            "ficha": fichas.get(d.id),
            "titulo": (fichas.get(d.id) or {}).get("titulo") or fuentes.get(d.id, {}).get("ancla"),
        }
        for d in documentos
    ]


@ruta.get("/{documento_id}")
async def detalle(documento_id: int, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    documento = await _documento(sesion, documento_id)
    texto = await sesion.get(Texto, documento_id)
    fichas = (
        await sesion.execute(
            select(Ficha, Perfil.nombre)
            .join(Perfil, Perfil.id == Ficha.perfil_id)
            .where(Ficha.documento_id == documento_id)
        )
    ).all()
    candidatos = (
        await sesion.execute(
            select(Candidato, Perfil.nombre)
            .join(Perfil, Perfil.id == Candidato.perfil_id)
            .where(Candidato.documento_id == documento_id)
        )
    ).all()
    perfiles = sorted({nombre for _, nombre in candidatos})
    padre = Lugar.__table__.alias("padre")
    lugares = (
        await sesion.execute(
            select(DocumentoLugar, Lugar.nombre, Lugar.clave, Lugar.nivel, padre.c.nombre)
            .outerjoin(Lugar, Lugar.id == DocumentoLugar.lugar_id)
            .outerjoin(padre, padre.c.id == Lugar.padre_id)
            .where(DocumentoLugar.documento_id == documento_id)
        )
    ).all()
    return {
        "id": documento.id,
        "sha256": documento.sha256,
        "bytes": documento.bytes,
        "mime": documento.mime,
        "paginas": documento.paginas,
        "estado": documento.estado,
        "creado": documento.creado,
        "texto": None
        if texto is None
        else {
            "metodo": texto.metodo,
            "caracteres": texto.caracteres,
            "error": texto.error,
            "inicio": texto.contenido[:3000],
        },
        "perfiles": perfiles,
        "fichas": [
            {
                "perfil": nombre,
                "estado": f.estado,
                "confianza": f.confianza,
                "motivos": f.motivos,
                "campos": f.campos,
                "titulo": titulo_de(f.campos),
                "modelo": f.modelo,
                "control": f.control,
                "actualizado": f.actualizado,
            }
            for f, nombre in fichas
        ],
        "lugares": [
            {
                "lugar_id": dl.lugar_id,
                "nombre": nombre,
                "clave": clave,
                "nivel": nivel,
                "padre": nombre_padre,
                "catalogo": dl.catalogo,
                "origen": dl.origen,
                "confianza": dl.confianza,
                "estado": dl.estado,
                "candidatos": dl.candidatos or [],
            }
            for dl, nombre, clave, nivel, nombre_padre in lugares
        ],
        "fuentes": [
            {
                "perfil": nombre,
                "url": c.url,
                "tipo": c.tipo,
                "puntaje": c.puntaje,
                "ancla": c.ancla,
                "pagina_origen": c.pagina_origen,
                "fuente": c.fuente,
                "nuevo": (c.datos or {}).get("nuevo"),
                "respaldo": (c.datos or {}).get("respaldo"),
                "lugar": (c.datos or {}).get("lugar"),
            }
            for c, nombre in candidatos
        ],
    }


@ruta.get("/{documento_id}/archivo")
async def archivo(documento_id: int, sesion: AsyncSession = Depends(sesion_api)) -> FileResponse:
    documento = await _documento(sesion, documento_id)
    ruta_archivo = _almacen().ruta(documento.ruta)
    if not ruta_archivo.is_file():
        raise HTTPException(410, "el archivo ya no está en el almacén")
    return FileResponse(
        ruta_archivo,
        media_type=documento.mime,
        filename=ruta_archivo.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@ruta.get("/{documento_id}/portada")
async def portada(documento_id: int, sesion: AsyncSession = Depends(sesion_api)) -> Response:
    """La primera página como imagen (se guarda junto al almacén para no volver a dibujarla)."""
    documento = await _documento(sesion, documento_id)
    almacen = _almacen()
    destino = almacen.carpeta / ".portadas" / f"{documento.sha256}.jpg"
    if not destino.is_file():
        origen = almacen.ruta(documento.ruta)
        if documento.mime != "application/pdf" or not origen.is_file():
            raise HTTPException(404, "sin portada")
        try:
            datos = await asyncio.to_thread(pdf.portada, origen)
        except Exception:
            raise HTTPException(404, "no se pudo dibujar la portada") from None
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
    return FileResponse(
        destino, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"}
    )


# --- fichas ---------------------------------------------------------------------


class FichaEditada(BaseModel):
    campos: dict[str, Any]


async def _perfil(sesion: AsyncSession, nombre: str) -> tuple[int, Any]:
    perfil_id = await sesion.scalar(select(Perfil.id).where(Perfil.nombre == nombre))
    if perfil_id is None:
        raise HTTPException(404, f"no hay un perfil llamado '{nombre}'")
    return perfil_id, await corridas.perfil_por_id(sesion, perfil_id)


@ruta.put("/{documento_id}/fichas/{perfil}")
async def editar_ficha(
    documento_id: int, perfil: str, datos: FichaEditada, sesion: AsyncSession = Depends(sesion_api)
) -> dict[str, Any]:
    """Guarda una ficha corregida a mano (se normaliza igual que la de la IA, sin corrector)."""
    await _documento(sesion, documento_id)
    perfil_id, config = await _perfil(sesion, perfil)
    v = F.validar(datos.campos, config, "")
    ficha = await sesion.scalar(select(Ficha).where(Ficha.documento_id == documento_id, Ficha.perfil_id == perfil_id))
    if ficha is None:
        ficha = Ficha(documento_id=documento_id, perfil_id=perfil_id, control={})
        sesion.add(ficha)
    ficha.campos = v.campos
    ficha.motivos = v.motivos
    ficha.estado = "revision" if any(m.startswith("falta ") for m in v.motivos) else "ok"
    ficha.confianza = "manual"
    ficha.control = {**(ficha.control or {}), "editada": True}
    ficha.actualizado = func.now()
    await eventos.publicar(
        sesion,
        "ficha",
        documento_id=documento_id,
        perfil_id=perfil_id,
        estado=ficha.estado,
        confianza="manual",
        titulo=titulo_de(v.campos),
    )
    await sesion.commit()
    return {"estado": ficha.estado, "motivos": ficha.motivos, "campos": ficha.campos}


@ruta.post("/{documento_id}/fichas/{perfil}/aprobar")
async def aprobar_ficha(documento_id: int, perfil: str, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    perfil_id, _ = await _perfil(sesion, perfil)
    ficha = await sesion.scalar(select(Ficha).where(Ficha.documento_id == documento_id, Ficha.perfil_id == perfil_id))
    if ficha is None:
        raise HTTPException(404, "ese documento no tiene ficha para ese perfil")
    ficha.estado = "ok"
    ficha.control = {**(ficha.control or {}), "aprobada": True}
    ficha.actualizado = func.now()
    await eventos.publicar(
        sesion,
        "ficha",
        documento_id=documento_id,
        perfil_id=perfil_id,
        estado="ok",
        confianza=ficha.confianza,
        titulo=titulo_de(ficha.campos),
    )
    await sesion.commit()
    return {"estado": "ok"}


@ruta.post("/{documento_id}/fichas/{perfil}/rehacer")
async def rehacer_ficha(documento_id: int, perfil: str, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    """Encola la ficha otra vez para que la IA la rehaga."""
    await _documento(sesion, documento_id)
    perfil_id, config = await _perfil(sesion, perfil)
    if not procesar.hace_fichas(config):
        raise HTTPException(422, "no hay proveedor de IA configurado o el perfil no define campos")
    if await sesion.get(Texto, documento_id) is None:
        encolada = await procesar.encolar_extraccion(sesion, documento_id, None)
    else:
        encolada = await procesar.encolar_ficha(sesion, documento_id, perfil_id, None)
    await sesion.commit()
    return {"encolada": encolada}
