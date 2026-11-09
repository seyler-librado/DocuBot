"""Geografía: catálogos, mapa, búsqueda de lugares y ubicación a mano."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos
from docubot.db.modelos import Candidato, Catalogo, Documento, DocumentoLugar, Ficha, Lugar, Perfil
from docubot.db.sesion import sesion_api
from docubot.pipeline import corridas

ruta = APIRouter(prefix="/api", tags=["lugares"])
_poligonos: dict[tuple, bytes] = {}
TOLERANCIA = {0: 0.01, 1: 0.003}  # grados; más fino para los niveles más detallados


async def _catalogo_de_perfil(sesion: AsyncSession, perfil: str) -> tuple[int, str]:
    perfil_id = await sesion.scalar(select(Perfil.id).where(Perfil.nombre == perfil))
    if perfil_id is None:
        raise HTTPException(404, f"no hay un perfil llamado '{perfil}'")
    config = await corridas.perfil_por_id(sesion, perfil_id)
    if config.geografia is None:
        raise HTTPException(422, f"el perfil '{perfil}' no tiene geografía")
    return perfil_id, config.geografia.identificador


@ruta.get("/catalogos")
async def catalogos(sesion: AsyncSession = Depends(sesion_api)) -> list[dict[str, Any]]:
    filas = await sesion.scalars(select(Catalogo).order_by(Catalogo.nombre))
    return [{"nombre": c.nombre, "lugares": c.lugares, "actualizado": c.actualizado} for c in filas]


@ruta.get("/mapa")
async def mapa(perfil: str, corrida: int | None = None, sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    """Cuántos documentos hay en cada lugar, para un perfil (y opcionalmente una corrida)."""
    perfil_id, catalogo = await _catalogo_de_perfil(sesion, perfil)
    docs = select(Candidato.documento_id).where(Candidato.perfil_id == perfil_id, Candidato.documento_id.is_not(None))
    if corrida:
        docs = docs.where(Candidato.corrida_id == corrida)
    docs = docs.distinct().subquery()
    base = select(DocumentoLugar).where(
        DocumentoLugar.catalogo == catalogo, DocumentoLugar.documento_id.in_(select(docs.c.documento_id))
    )
    filas = (
        await sesion.execute(
            select(
                Lugar.id,
                Lugar.clave,
                Lugar.nombre,
                Lugar.nivel,
                Lugar.padre_id,
                func.ST_X(Lugar.punto),
                func.ST_Y(Lugar.punto),
                func.count(func.distinct(DocumentoLugar.documento_id)),
                func.count(func.distinct(DocumentoLugar.documento_id)).filter(DocumentoLugar.estado == "revision"),
            )
            .join(DocumentoLugar, DocumentoLugar.lugar_id == Lugar.id)
            .where(DocumentoLugar.id.in_(select(base.subquery().c.id)))
            .group_by(Lugar.id)
        )
    ).all()
    padres = {
        i: n
        for i, n in await sesion.execute(
            select(Lugar.id, Lugar.nombre).where(Lugar.id.in_({f[4] for f in filas if f[4]}))
        )
    }
    estados = {
        e: n
        for e, n in await sesion.execute(
            select(DocumentoLugar.estado, func.count(func.distinct(DocumentoLugar.documento_id)))
            .where(DocumentoLugar.id.in_(select(base.subquery().c.id)))
            .group_by(DocumentoLugar.estado)
        )
    }
    total = await sesion.scalar(select(func.count()).select_from(docs))
    caja = (
        await sesion.execute(
            select(
                func.ST_XMin(func.ST_Extent(Lugar.punto)),
                func.ST_YMin(func.ST_Extent(Lugar.punto)),
                func.ST_XMax(func.ST_Extent(Lugar.punto)),
                func.ST_YMax(func.ST_Extent(Lugar.punto)),
            ).where(Lugar.catalogo == catalogo)
        )
    ).one()
    return {
        "catalogo": catalogo,
        "documentos": total,
        "ubicados": sum(f[7] for f in filas),
        "por_estado": estados,
        "sin_procesar": max(0, total - sum(estados.values())),
        "extension": list(caja) if caja[0] is not None else None,
        "lugares": [
            {
                "id": i,
                "clave": c,
                "nombre": n,
                "nivel": nv,
                "padre": padres.get(p),
                "lon": x,
                "lat": y,
                "documentos": d,
                "revision": r,
            }
            for i, c, n, nv, p, x, y, d, r in filas
        ],
    }


@ruta.get("/mapa/poligonos")
async def poligonos(catalogo: str, nivel: str, sesion: AsyncSession = Depends(sesion_api)) -> Response:
    """Polígonos simplificados de un nivel del catálogo (GeoJSON), en caché mientras el catálogo no cambie."""
    fila = await sesion.get(Catalogo, catalogo)
    if fila is None:
        raise HTTPException(404, f"no existe el catálogo '{catalogo}'")
    clave = (catalogo, nivel, fila.huella)
    if clave not in _poligonos:
        con_padre = await sesion.scalar(
            select(func.count()).where(Lugar.catalogo == catalogo, Lugar.nivel == nivel, Lugar.padre_id.is_not(None))
        )
        tolerancia = TOLERANCIA[1 if con_padre else 0]
        filas = await sesion.execute(
            text(
                """
                SELECT id, clave, nombre, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :t), 4) AS g
                FROM lugares WHERE catalogo = :c AND nivel = :n AND geom IS NOT NULL
                """
            ),
            {"c": catalogo, "n": nivel, "t": tolerancia},
        )
        elementos = [
            {"type": "Feature", "id": i, "properties": {"id": i, "clave": c, "nombre": n}, "geometry": json.loads(g)}
            for i, c, n, g in filas
        ]
        _poligonos[clave] = json.dumps(
            {"type": "FeatureCollection", "features": elementos}, ensure_ascii=False, separators=(",", ":")
        ).encode()
    return Response(
        _poligonos[clave], media_type="application/geo+json", headers={"Cache-Control": "private, max-age=3600"}
    )


@ruta.get("/mapa/niveles")
async def niveles(catalogo: str, sesion: AsyncSession = Depends(sesion_api)) -> list[dict[str, Any]]:
    """Los niveles del catálogo, del más general al más detallado, y si tienen polígonos."""
    filas = (
        await sesion.execute(
            select(Lugar.nivel, func.count(), func.count(Lugar.geom), func.bool_or(Lugar.padre_id.is_not(None)))
            .where(Lugar.catalogo == catalogo)
            .group_by(Lugar.nivel)
        )
    ).all()
    return sorted(
        [{"nivel": n, "lugares": t, "con_poligono": g > 0, "tiene_padre": bool(p)} for n, t, g, p in filas],
        key=lambda x: (x["tiene_padre"], -x["lugares"] if not x["tiene_padre"] else x["lugares"]),
    )


@ruta.get("/lugares/buscar")
async def buscar_lugares(
    catalogo: str, q: str = Query(..., min_length=2), sesion: AsyncSession = Depends(sesion_api)
) -> list[dict[str, Any]]:
    padre = Lugar.__table__.alias("padre")
    patron = f"%{q.strip()}%"
    filas = await sesion.execute(
        select(Lugar.id, Lugar.clave, Lugar.nombre, Lugar.nivel, padre.c.nombre)
        .outerjoin(padre, padre.c.id == Lugar.padre_id)
        .where(Lugar.catalogo == catalogo, func.unaccent(Lugar.nombre).ilike(func.unaccent(patron)))
        .order_by(func.length(Lugar.nombre), Lugar.nombre)
        .limit(20)
    )
    return [{"id": i, "clave": c, "nombre": n, "nivel": nv, "padre": p} for i, c, n, nv, p in filas]


class LugarElegido(BaseModel):
    lugar_id: int


@ruta.put("/documentos/{documento_id}/lugar")
async def asignar_lugar(
    documento_id: int, datos: LugarElegido, sesion: AsyncSession = Depends(sesion_api)
) -> dict[str, Any]:
    """Una persona dice dónde aplica el documento (reemplaza lo que se dedujo en ese catálogo)."""
    if await sesion.get(Documento, documento_id) is None:
        raise HTTPException(404, f"no existe el documento {documento_id}")
    lugar = await sesion.get(Lugar, datos.lugar_id)
    if lugar is None:
        raise HTTPException(404, f"no existe el lugar {datos.lugar_id}")
    await sesion.execute(
        delete(DocumentoLugar).where(
            DocumentoLugar.documento_id == documento_id, DocumentoLugar.catalogo == lugar.catalogo
        )
    )
    sesion.add(
        DocumentoLugar(
            documento_id=documento_id,
            lugar_id=lugar.id,
            catalogo=lugar.catalogo,
            origen="manual",
            confianza=1.0,
            estado="asignado",
        )
    )
    await eventos.publicar(sesion, "lugar", documento_id=documento_id, estado="asignado", lugar=lugar.nombre)
    await sesion.commit()
    return {"lugar_id": lugar.id, "nombre": lugar.nombre}


@ruta.get("/lugares/dudosos")
async def dudosos(
    perfil: str | None = None,
    limite: int = Query(50, ge=1, le=500),
    desde: int = Query(0, ge=0),
    sesion: AsyncSession = Depends(sesion_api),
) -> dict[str, Any]:
    """Documentos con lugar ambiguo o en conflicto, para elegir a mano."""
    filtro = [DocumentoLugar.estado.in_(["ambiguo", "revision"])]
    if perfil:
        _, catalogo = await _catalogo_de_perfil(sesion, perfil)
        filtro.append(DocumentoLugar.catalogo == catalogo)
    base = select(DocumentoLugar).where(*filtro)
    total = await sesion.scalar(select(func.count()).select_from(base.subquery()))
    filas = (await sesion.scalars(base.order_by(DocumentoLugar.id.desc()).offset(desde).limit(limite))).all()
    ids = [f.documento_id for f in filas]
    titulos: dict[int, str] = {}
    for d, campos in await sesion.execute(select(Ficha.documento_id, Ficha.campos).where(Ficha.documento_id.in_(ids))):
        titulo = next((campos.get(k) for k in ("titulo", "nombre", "title") if campos.get(k)), None)
        if titulo:
            titulos.setdefault(d, str(titulo))
    urls = {
        d: u
        for d, u in await sesion.execute(
            select(Candidato.documento_id, func.min(Candidato.url))
            .where(Candidato.documento_id.in_(ids))
            .group_by(Candidato.documento_id)
        )
    }
    return {
        "total": total,
        "elementos": [
            {
                "documento_id": f.documento_id,
                "estado": f.estado,
                "origen": f.origen,
                "catalogo": f.catalogo,
                "candidatos": f.candidatos or [],
                "titulo": titulos.get(f.documento_id),
                "url": urls.get(f.documento_id),
            }
            for f in filas
        ],
    }
