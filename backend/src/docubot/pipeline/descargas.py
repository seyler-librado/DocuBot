"""Encolar descargas sin duplicar: una tarea activa por candidato como máximo."""

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Candidato, Corrida
from docubot.pipeline.cola import CANAL


async def encolar(sesion: AsyncSession, corrida_id: int | None, candidatos: list[tuple[int, int]]) -> int:
    """Encola [(candidato_id, puntaje)]; los de mayor puntaje se bajan primero. Devuelve cuántas encoló."""
    if not candidatos:
        return 0
    r = await sesion.execute(
        text(
            """
            INSERT INTO tareas (etapa, corrida_id, carga, prioridad, max_intentos)
            SELECT 'descargar', :corrida, jsonb_build_object('candidato_id', c.id), c.puntaje, 3
            FROM unnest(CAST(:ids AS bigint[]), CAST(:puntajes AS int[])) AS c(id, puntaje)
            WHERE NOT EXISTS (
              SELECT 1 FROM tareas t
              WHERE t.etapa = 'descargar' AND t.estado IN ('pendiente', 'tomada')
                AND t.carga->>'candidato_id' = c.id::text
            )
            """
        ),
        {
            "corrida": corrida_id,
            "ids": [c for c, _ in candidatos],
            "puntajes": [p or 0 for _, p in candidatos],
        },
    )
    n = r.rowcount or 0
    if n:
        await sesion.execute(text("SELECT pg_notify(:canal, 'descargar')"), {"canal": CANAL})
    return n


async def pendientes(
    sesion: AsyncSession, corrida_id: int, *, limite: int | None = None, incluir_fallidos: bool = False
) -> list[tuple[int, int]]:
    """Candidatos aceptados de la corrida que todavía no tienen documento."""
    estados = ["aceptado"] + (["fallido"] if incluir_fallidos else [])
    consulta = (
        select(Candidato.id, Candidato.puntaje)
        .where(
            Candidato.corrida_id == corrida_id,
            Candidato.estado.in_(estados),
            Candidato.documento_id.is_(None),
        )
        .order_by(Candidato.puntaje.desc().nulls_last(), Candidato.id)
    )
    if limite:
        consulta = consulta.limit(limite)
    return [(i, p) for i, p in await sesion.execute(consulta)]


async def descargar_corrida(
    sesion: AsyncSession, corrida_id: int, *, limite: int | None = None, incluir_fallidos: bool = False
) -> int:
    """Encola las descargas que falten de una corrida (y la reabre si ya había terminado)."""
    lista = await pendientes(sesion, corrida_id, limite=limite, incluir_fallidos=incluir_fallidos)
    if incluir_fallidos and lista:
        await sesion.execute(
            update(Candidato)
            .where(Candidato.id.in_([i for i, _ in lista]), Candidato.estado == "fallido")
            .values(estado="aceptado", motivo=None)
        )
    n = await encolar(sesion, corrida_id, lista)
    if n:
        await sesion.execute(
            update(Corrida).where(Corrida.id == corrida_id).values(estado="corriendo", terminada=None, error=None)
        )
    return n
