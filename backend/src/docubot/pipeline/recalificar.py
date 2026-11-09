"""Vuelve a calcular el puntaje de los candidatos de un perfil (p. ej. tras cambiar sus tipos).

No toca lo descargado ni lo fallido.
"""

from collections import Counter

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Candidato
from docubot.filtros.puntaje import Calificador
from docubot.perfiles.esquema import Perfil

LOTE = 2000


async def recalificar(sesion: AsyncSession, perfil_id: int, perfil: Perfil) -> Counter:
    calificador = Calificador(perfil.documentos)
    cuenta: Counter = Counter()
    ultimo = 0
    while True:
        filas = (
            await sesion.execute(
                select(
                    Candidato.id, Candidato.url, Candidato.ancla, Candidato.puntaje, Candidato.estado, Candidato.tipo
                )
                .where(
                    Candidato.perfil_id == perfil_id,
                    Candidato.estado.in_(["nuevo", "aceptado", "rechazado"]),
                    Candidato.id > ultimo,
                )
                .order_by(Candidato.id)
                .limit(LOTE)
            )
        ).all()
        if not filas:
            return cuenta
        cambios = []
        for id_, url, ancla, puntaje, estado, tipo in filas:
            nota = calificador.calificar(url, ancla)
            cuenta[nota.estado] += 1
            if (nota.puntaje, nota.estado, nota.tipo) != (puntaje, estado, tipo):
                cambios.append(
                    {
                        "id": id_,
                        "puntaje": nota.puntaje,
                        "estado": nota.estado,
                        "tipo": nota.tipo,
                        "motivo": nota.motivo,
                    }
                )
        if cambios:
            await sesion.execute(update(Candidato), cambios)
            cuenta["cambiados"] += len(cambios)
        ultimo = filas[-1][0]
