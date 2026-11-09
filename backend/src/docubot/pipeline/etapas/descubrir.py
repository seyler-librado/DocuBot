"""Etapa descubrir: corre una fuente del perfil (o una parte de ella)."""

from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Corrida, Tarea
from docubot.descubrimiento.contexto import Contexto
from docubot.descubrimiento.fuentes import FUENTES
from docubot.pipeline import corridas


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    corrida = await sesion.get(Corrida, tarea.corrida_id)
    perfil = corridas.perfil_de(corrida)
    fuente = perfil.descubrimiento.fuentes[tarea.carga["fuente"]]
    ctx = Contexto(sesion, corrida, perfil, corridas.carpeta_de(corrida))
    await sesion.commit()  # no dejar la transacción abierta mientras se espera a la red
    await FUENTES[fuente.tipo](ctx, fuente, tarea.carga)
