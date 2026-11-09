"""Corridas: crear, detener, reanudar, saber cuándo terminaron y resumir su avance.

Una corrida guarda una copia del perfil con el que se lanzó (parametros.perfil),
así cambiar el YAML a media corrida no la altera.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos
from docubot.db.modelos import Candidato, Corrida, CorridaSitio, Documento, Ficha, Tarea
from docubot.db.modelos import Perfil as PerfilBD
from docubot.filtros.referencia import Referencia
from docubot.perfiles.cargador import PerfilCargado
from docubot.perfiles.esquema import Perfil
from docubot.perfiles.sincronizar import sincronizar
from docubot.pipeline import cola

ACTIVAS = ("pendiente", "tomada")


class CambiosCorrida(BaseModel):
    """Ajustes del perfil que se pueden cambiar solo para una corrida."""

    respetar_robots: bool | None = None
    peticiones_por_segundo: float | None = Field(None, gt=0, le=20)
    profundidad: int | None = Field(None, ge=0, le=10)
    max_paginas: int | None = Field(None, ge=1, le=10_000)
    puntaje_minimo: int | None = Field(None, ge=0, le=100)


def aplicar_cambios(perfil: Perfil, cambios: CambiosCorrida | None) -> Perfil:
    if cambios is None:
        return perfil
    datos = perfil.model_dump(mode="json")
    if cambios.respetar_robots is not None:
        datos["red"]["respetar_robots"] = cambios.respetar_robots
    if cambios.peticiones_por_segundo is not None:
        datos["red"]["peticiones_por_segundo_por_dominio"] = cambios.peticiones_por_segundo
    if cambios.profundidad is not None:
        datos["descubrimiento"]["exploracion"]["profundidad"] = cambios.profundidad
    if cambios.max_paginas is not None:
        datos["descubrimiento"]["exploracion"]["max_paginas"] = cambios.max_paginas
    if cambios.puntaje_minimo is not None:
        datos["documentos"]["puntaje_minimo"] = cambios.puntaje_minimo
    return Perfil.model_validate(datos)


_perfiles: dict[tuple, Perfil] = {}
_referencias: dict[tuple, Referencia | None] = {}


class ErrorCorrida(ValueError):
    pass


def perfil_de(corrida: Corrida) -> Perfil:
    clave = (corrida.id, corrida.creada)  # la fecha distingue ids reutilizados (p. ej. tras vaciar la base)
    if clave not in _perfiles:
        _perfiles[clave] = Perfil.model_validate(corrida.parametros["perfil"])
    return _perfiles[clave]


def carpeta_de(corrida: Corrida) -> Path:
    return Path(corrida.parametros["carpeta"])


def referencia_de(corrida: Corrida) -> Referencia | None:
    """La referencia del perfil (lo que ya se tiene), leída una vez por corrida."""
    clave = (corrida.id, corrida.creada)
    if clave not in _referencias:
        config = perfil_de(corrida).referencia
        _referencias[clave] = Referencia(config, carpeta_de(corrida)) if config else None
    return _referencias[clave]


def descarga_activa(corrida: Corrida) -> bool:
    return bool(corrida.parametros.get("descargar", True))


async def perfil_por_id(sesion: AsyncSession, perfil_id: int) -> Perfil:
    """El perfil tal como está guardado en la base (para tareas sin corrida)."""
    fila = await sesion.get(PerfilBD, perfil_id)
    clave = ("perfil", perfil_id, fila.huella)
    if clave not in _perfiles:
        _perfiles[clave] = Perfil.model_validate(fila.config)
    return _perfiles[clave]


async def crear(
    sesion: AsyncSession,
    cargado: PerfilCargado,
    fuentes: list[int] | None = None,
    *,
    descargar: bool = True,
    cambios: CambiosCorrida | None = None,
) -> Corrida:
    if not cargado.valido or cargado.perfil is None:
        raise ErrorCorrida(f"el perfil '{cargado.nombre}' tiene errores: " + "; ".join(cargado.errores))
    perfil = cargado.perfil
    total = len(perfil.descubrimiento.fuentes)
    indices = list(range(total)) if not fuentes else sorted(set(fuentes))
    fuera = [i for i in indices if not 0 <= i < total]
    if fuera:
        raise ErrorCorrida(f"el perfil tiene {total} fuente(s) (0 a {total - 1}); no existe: {fuera}")

    await sincronizar(sesion, [cargado])
    if perfil.geografia is not None:
        from docubot.geo.catalogo import importar  # aquí, para no cargar la geografía si no se usa

        await importar(sesion, perfil.geografia, cargado.carpeta)
    perfil_id = await sesion.scalar(select(PerfilBD.id).where(PerfilBD.nombre == perfil.nombre))
    perfil = aplicar_cambios(perfil, cambios)
    corrida = Corrida(
        perfil_id=perfil_id,
        estado="corriendo",
        iniciada=func.now(),
        parametros={
            "perfil": perfil.model_dump(mode="json"),
            "carpeta": str(cargado.carpeta),
            "fuentes": indices,
            "descargar": descargar,
            "cambios": cambios.model_dump(exclude_none=True) if cambios else {},
        },
    )
    sesion.add(corrida)
    await sesion.flush()
    for i in indices:
        await cola.encolar(sesion, "descubrir", {"fuente": i}, corrida_id=corrida.id)
    await sesion.refresh(corrida)
    return corrida


async def detener(sesion: AsyncSession, corrida_id: int) -> int:
    """Cancela lo pendiente; lo que ya está corriendo termina. Devuelve cuántas tareas canceló."""
    await sesion.execute(
        update(Corrida).where(Corrida.id == corrida_id, Corrida.estado == "corriendo").values(estado="detenida")
    )
    r = await sesion.execute(
        update(Tarea).where(Tarea.corrida_id == corrida_id, Tarea.estado == "pendiente").values(estado="cancelada")
    )
    return r.rowcount or 0


async def reanudar(sesion: AsyncSession, corrida_id: int, reintentar_fallidas: bool = False) -> int:
    estados = ["cancelada"] + (["fallida"] if reintentar_fallidas else [])
    valores: dict[str, Any] = {"estado": "pendiente", "disponible_en": func.now()}
    if reintentar_fallidas:
        valores["intentos"] = 0
    r = await sesion.execute(
        update(Tarea).where(Tarea.corrida_id == corrida_id, Tarea.estado.in_(estados)).values(**valores)
    )
    n = r.rowcount or 0
    if n:
        await sesion.execute(
            update(Corrida).where(Corrida.id == corrida_id).values(estado="corriendo", terminada=None, error=None)
        )
    return n


async def perfil_actual(sesion: AsyncSession, corrida: Corrida) -> Perfil:
    """El perfil como está ahora en su YAML (lo vuelve a leer y lo sincroniza; importa su catálogo)."""
    from docubot.ajustes import obtener_ajustes
    from docubot.perfiles import cargar_todos

    nombre = await sesion.scalar(select(PerfilBD.nombre).where(PerfilBD.id == corrida.perfil_id))
    cargado = next(
        (c for c in cargar_todos(obtener_ajustes().carpeta_perfiles) if c.nombre == nombre and c.valido), None
    )
    if cargado is not None:
        await sincronizar(sesion, [cargado])
        if cargado.perfil.geografia is not None:
            from docubot.geo.catalogo import importar

            await importar(sesion, cargado.perfil.geografia, cargado.carpeta)
        await sesion.flush()
    return await perfil_por_id(sesion, corrida.perfil_id)


async def reabrir(sesion: AsyncSession, corrida_id: int) -> None:
    """La corrida vuelve a estar en curso (se le encolaron tareas nuevas)."""
    await sesion.execute(
        update(Corrida).where(Corrida.id == corrida_id).values(estado="corriendo", terminada=None, error=None)
    )


async def revisar_fin(sesion: AsyncSession, corrida_id: int) -> bool:
    """Si ya no quedan tareas activas, marca la corrida como terminada. True si la terminó."""
    activas = await sesion.scalar(select(func.count()).where(Tarea.corrida_id == corrida_id, Tarea.estado.in_(ACTIVAS)))
    if activas:
        return False
    fallidas = await sesion.scalar(
        select(func.count()).where(Tarea.corrida_id == corrida_id, Tarea.estado == "fallida")
    )
    r = await sesion.execute(
        update(Corrida)
        .where(Corrida.id == corrida_id, Corrida.estado == "corriendo")
        .values(
            estado="terminada",
            terminada=func.now(),
            error=f"{fallidas} tarea(s) fallaron" if fallidas else None,
        )
    )
    if r.rowcount:
        await eventos.publicar(sesion, "corrida", corrida_id=corrida_id, estado="terminada")
    return bool(r.rowcount)


async def estado_de(sesion: AsyncSession, corrida_id: int) -> str | None:
    return await sesion.scalar(select(Corrida.estado).where(Corrida.id == corrida_id))


async def resumen(sesion: AsyncSession, corrida: Corrida) -> dict[str, Any]:
    cid = corrida.id
    tareas: dict[str, dict[str, int]] = {}
    for etapa, estado, n in await sesion.execute(
        select(Tarea.etapa, Tarea.estado, func.count())
        .where(Tarea.corrida_id == cid)
        .group_by(Tarea.etapa, Tarea.estado)
    ):
        tareas.setdefault(etapa, {})[estado] = n
    sitios = {
        estado: n
        for estado, n in await sesion.execute(
            select(CorridaSitio.estado, func.count())
            .where(CorridaSitio.corrida_id == cid)
            .group_by(CorridaSitio.estado)
        )
    }
    paginas = await sesion.scalar(
        select(func.coalesce(func.sum(CorridaSitio.paginas), 0)).where(CorridaSitio.corrida_id == cid)
    )
    candidatos = {
        fuente: n
        for fuente, n in await sesion.execute(
            select(Candidato.fuente, func.count()).where(Candidato.corrida_id == cid).group_by(Candidato.fuente)
        )
    }
    por_estado = {
        estado: n
        for estado, n in await sesion.execute(
            select(Candidato.estado, func.count()).where(Candidato.corrida_id == cid).group_by(Candidato.estado)
        )
    }
    nuevos = await sesion.scalar(
        select(func.count()).where(Candidato.corrida_id == cid, Candidato.datos["nuevo"].astext == "true")
    )
    docs, peso = (
        await sesion.execute(
            select(func.count(func.distinct(Documento.id)), func.coalesce(func.sum(Documento.bytes), 0))
            .select_from(Candidato)
            .join(Documento, Documento.id == Candidato.documento_id)
            .where(Candidato.corrida_id == cid)
        )
    ).one()
    fichas = {
        estado: n
        for estado, n in await sesion.execute(
            select(Ficha.estado, func.count(func.distinct(Ficha.id)))
            .join(Candidato, (Candidato.documento_id == Ficha.documento_id) & (Candidato.perfil_id == Ficha.perfil_id))
            .where(Candidato.corrida_id == cid)
            .group_by(Ficha.estado)
        )
    }
    nombre = await sesion.scalar(select(PerfilBD.nombre).where(PerfilBD.id == corrida.perfil_id))
    return {
        "id": cid,
        "perfil": nombre,
        "estado": corrida.estado,
        "error": corrida.error,
        "creada": corrida.creada,
        "iniciada": corrida.iniciada,
        "terminada": corrida.terminada,
        "fuentes": corrida.parametros.get("fuentes", []),
        "tareas": tareas,
        "sitios": sitios,
        "paginas": paginas,
        "candidatos": candidatos,
        "candidatos_total": sum(candidatos.values()),
        "candidatos_estado": por_estado,
        "nuevos": nuevos,
        "documentos": docs,
        "bytes": int(peso),
        "descargar": descarga_activa(corrida),
        "fichas": fichas,
        "cambios": corrida.parametros.get("cambios", {}),
    }
