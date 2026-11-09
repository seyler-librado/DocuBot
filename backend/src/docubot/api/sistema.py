"""Estado del sistema: base de datos, extensiones, migración y ajustes públicos."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import __version__
from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Corrida, Documento, Ficha, Perfil
from docubot.db.sesion import sesion_api
from docubot.eventos import difusor
from docubot.pipeline import cola

ruta = APIRouter(prefix="/api", tags=["sistema"])

CONSULTA_SALUD = text(
    """
    SELECT
      current_setting('server_version') AS postgres,
      (SELECT extversion FROM pg_extension WHERE extname = 'postgis') AS postgis,
      (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS vector,
      (SELECT version_num FROM alembic_version LIMIT 1) AS migracion
    """
)


@ruta.get("/salud")
async def salud(sesion: AsyncSession = Depends(sesion_api)) -> dict:
    try:
        fila = (await sesion.execute(CONSULTA_SALUD)).mappings().one()
        base = {"ok": True, **fila}
    except Exception as error:  # la API responde aunque la base no
        base = {"ok": False, "error": str(error).splitlines()[0]}
    return {"ok": base["ok"], "version": __version__, "base_datos": base}


@ruta.get("/ajustes")
async def ajustes() -> dict:
    return obtener_ajustes().publicos()


@ruta.get("/resumen")
async def resumen(sesion: AsyncSession = Depends(sesion_api)) -> dict:
    """Cifras generales para el panel."""
    documentos, peso = (await sesion.execute(select(func.count(), func.coalesce(func.sum(Documento.bytes), 0)))).one()
    fichas = {e: n for e, n in await sesion.execute(select(Ficha.estado, func.count()).group_by(Ficha.estado))}
    return {
        "perfiles": await sesion.scalar(select(func.count()).select_from(Perfil)),
        "corridas_activas": await sesion.scalar(select(func.count()).where(Corrida.estado == "corriendo")),
        "documentos": documentos,
        "bytes": int(peso),
        "fichas": fichas,
        "por_bajar": await sesion.scalar(
            select(func.count()).where(Candidato.estado == "aceptado", Candidato.documento_id.is_(None))
        ),
        "candidatos": await sesion.scalar(select(func.count()).select_from(Candidato)),
        "eventos_conectado": difusor.conectado,
    }


@ruta.get("/tareas/resumen")
async def resumen_tareas(sesion: AsyncSession = Depends(sesion_api)) -> dict:
    return await cola.resumen(sesion)
