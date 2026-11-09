"""Cola de tareas sobre Postgres.

Cada etapa del pipeline toma sus tareas pendientes con FOR UPDATE SKIP LOCKED:
varios trabajadores pueden tomar a la vez sin repetir ni bloquearse.
Si un trabajador muere a medio camino, `recuperar_huerfanas` devuelve sus tareas a la cola.
"""

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Tarea

CANAL = "docubot_tareas"
ESPERA_BASE = timedelta(seconds=30)  # primer reintento; luego se duplica


async def encolar(
    sesion: AsyncSession,
    etapa: str,
    carga: dict[str, Any] | None = None,
    *,
    corrida_id: int | None = None,
    prioridad: int = 0,
    max_intentos: int = 3,
) -> Tarea:
    tarea = Tarea(
        etapa=etapa,
        carga=carga or {},
        corrida_id=corrida_id,
        prioridad=prioridad,
        max_intentos=max_intentos,
    )
    sesion.add(tarea)
    await sesion.flush()
    # avisa a los trabajadores dormidos (llega al confirmar la transacción)
    await sesion.execute(text("SELECT pg_notify(:canal, :etapa)"), {"canal": CANAL, "etapa": etapa})
    return tarea


async def encolar_unica(
    sesion: AsyncSession,
    etapa: str,
    clave: str,
    carga: dict[str, Any],
    *,
    corrida_id: int | None = None,
    prioridad: int = 0,
    max_intentos: int = 3,
) -> bool:
    """Encola solo si no hay ya una tarea activa con la misma clave. True si la encoló."""
    r = await sesion.execute(
        text(
            """
            INSERT INTO tareas (etapa, corrida_id, carga, prioridad, max_intentos)
            SELECT :etapa, :corrida, CAST(:carga AS jsonb), :prioridad, :maximo
            WHERE NOT EXISTS (
              SELECT 1 FROM tareas
              WHERE estado IN ('pendiente', 'tomada') AND carga->>'clave' = :clave
            )
            """
        ),
        {
            "etapa": etapa,
            "corrida": corrida_id,
            "carga": json.dumps({**carga, "clave": clave}),
            "prioridad": prioridad,
            "maximo": max_intentos,
            "clave": clave,
        },
    )
    if r.rowcount:
        await sesion.execute(text("SELECT pg_notify(:canal, :etapa)"), {"canal": CANAL, "etapa": etapa})
    return bool(r.rowcount)


async def tomar(sesion: AsyncSession, etapa: str, trabajador: str, limite: int = 1) -> list[Tarea]:
    libres = (
        select(Tarea.id)
        .where(
            Tarea.etapa == etapa,
            Tarea.estado == "pendiente",
            Tarea.disponible_en <= func.now(),
        )
        .order_by(Tarea.prioridad.desc(), Tarea.id)
        .limit(limite)
        .with_for_update(skip_locked=True)
    )
    consulta = (
        update(Tarea)
        .where(Tarea.id.in_(libres))
        .values(
            estado="tomada",
            tomada_por=trabajador,
            tomada_en=func.now(),
            intentos=Tarea.intentos + 1,
        )
        .returning(Tarea)
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    return list((await sesion.scalars(consulta)).all())


async def completar(sesion: AsyncSession, tarea_id: int) -> None:
    await sesion.execute(
        update(Tarea).where(Tarea.id == tarea_id).values(estado="hecha", terminada=func.now(), error=None)
    )


async def fallar(sesion: AsyncSession, tarea_id: int, error: str, *, permanente: bool = False) -> str:
    """Devuelve la tarea a la cola con espera creciente, o la marca fallida. Regresa el estado.

    Con permanente=True (reintentar no sirve) se marca fallida de inmediato.
    """
    tarea = await sesion.get(Tarea, tarea_id, with_for_update=True, populate_existing=True)
    if tarea is None:
        return "desconocida"
    tarea.error = error[:4000]
    tarea.tomada_por = None
    if permanente or tarea.intentos >= tarea.max_intentos:
        tarea.estado = "fallida"
        tarea.terminada = func.now()
    else:
        tarea.estado = "pendiente"
        tarea.disponible_en = func.now() + ESPERA_BASE * (2 ** (tarea.intentos - 1))
    await sesion.flush()
    return tarea.estado


async def cancelar(sesion: AsyncSession, tarea_id: int) -> None:
    await sesion.execute(update(Tarea).where(Tarea.id == tarea_id).values(estado="cancelada", tomada_por=None))


async def latido(sesion: AsyncSession, tarea_id: int) -> None:
    """El trabajador sigue vivo con esta tarea (evita que se tome por huérfana)."""
    await sesion.execute(
        update(Tarea).where(Tarea.id == tarea_id, Tarea.estado == "tomada").values(tomada_en=func.now())
    )


async def recuperar_huerfanas(sesion: AsyncSession, minutos: int = 15) -> int:
    """Regresa a la cola las tareas tomadas hace demasiado (su trabajador murió)."""
    resultado = await sesion.execute(
        update(Tarea)
        .where(
            Tarea.estado == "tomada",
            Tarea.tomada_en < func.now() - timedelta(minutes=minutos),
        )
        .values(estado="pendiente", tomada_por=None)
    )
    return resultado.rowcount or 0


async def resumen(sesion: AsyncSession) -> dict[str, dict[str, int]]:
    """{etapa: {estado: cuántas}}"""
    filas = await sesion.execute(select(Tarea.etapa, Tarea.estado, func.count()).group_by(Tarea.etapa, Tarea.estado))
    salida: dict[str, dict[str, int]] = {}
    for etapa, estado, n in filas:
        salida.setdefault(etapa, {})[estado] = n
    return salida
