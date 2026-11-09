"""Etapa extraer: saca el texto de un documento y encola sus fichas."""

import asyncio
import logging

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Documento, Tarea, Texto
from docubot.documentos import pdf
from docubot.documentos.almacen import Almacen
from docubot.pipeline import corridas, procesar

log = logging.getLogger("docubot.extraer")


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    documento = await sesion.get(Documento, tarea.carga["documento_id"])
    if documento is None:
        return
    ruta = Almacen(obtener_ajustes().almacen.carpeta).ruta(documento.ruta)
    await sesion.commit()

    if not ruta.is_file():
        e = pdf.Extraccion("ilegible", error="el archivo ya no está en el almacén")
    elif ruta.suffix.lower() == ".pdf" or documento.mime == "application/pdf":
        e = await asyncio.to_thread(pdf.extraer, ruta)  # leer PDFs grandes no debe frenar a los demás
    else:
        e = pdf.Extraccion("ilegible", error=f"todavía no se extrae texto de archivos {ruta.suffix or documento.mime}")

    consulta = insert(Texto).values(
        documento_id=documento.id, contenido=e.contenido, metodo=e.estado, caracteres=e.caracteres, error=e.error
    )
    consulta = consulta.on_conflict_do_update(
        index_elements=["documento_id"],
        set_={k: consulta.excluded[k] for k in ("contenido", "metodo", "caracteres", "error")} | {"creado": func.now()},
    )
    await sesion.execute(consulta)
    documento.paginas, documento.estado = e.paginas, e.estado
    log.info("documento %s: %s, %s páginas, %s caracteres", documento.id, e.estado, e.paginas, e.caracteres)

    from docubot.busqueda import embeddings

    if e.estado == "texto" and embeddings.activo():  # vectores para la búsqueda por tema
        await procesar.encolar_indexado(sesion, documento.id, tarea.corrida_id)

    # una ficha por cada perfil que tiene este documento
    perfiles = (
        await sesion.scalars(select(Candidato.perfil_id).where(Candidato.documento_id == documento.id).distinct())
    ).all()
    for perfil_id in perfiles:
        perfil = await corridas.perfil_por_id(sesion, perfil_id)  # fichas y lugares siguen el perfil actual
        if procesar.hace_fichas(perfil):
            await procesar.encolar_ficha(sesion, documento.id, perfil_id, tarea.corrida_id)
        elif perfil.geografia is not None:  # sin IA, se ubica con el texto
            await procesar.encolar_ubicacion(sesion, documento.id, perfil_id, tarea.corrida_id)
