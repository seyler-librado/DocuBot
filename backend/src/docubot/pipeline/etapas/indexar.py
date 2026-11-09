"""Etapa indexar: parte el texto de un documento en fragmentos y guarda sus vectores (búsqueda por tema)."""

import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.ajustes import obtener_ajustes
from docubot.busqueda import embeddings
from docubot.busqueda.fragmentos import partir
from docubot.db.modelos import Fragmento, Tarea, Texto

log = logging.getLogger("docubot.indexar")


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    documento_id = tarea.carga["documento_id"]
    texto = await sesion.get(Texto, documento_id)
    if texto is None or texto.metodo != "texto" or not embeddings.activo():
        return
    a = obtener_ajustes().busqueda
    pedazos = partir(texto.contenido, a.tamano_fragmento, a.solape, a.max_fragmentos)
    await sesion.commit()  # calcular vectores toma tiempo: sin transacción abierta
    proveedor = embeddings.obtener()
    vectores = await proveedor.documentos([p.texto for p in pedazos]) if pedazos else []
    await sesion.execute(
        delete(Fragmento).where(Fragmento.documento_id == documento_id, Fragmento.modelo == proveedor.modelo)
    )
    sesion.add_all(
        Fragmento(
            documento_id=documento_id,
            orden=p.orden,
            pagina=p.pagina,
            texto=p.texto,
            modelo=proveedor.modelo,
            embedding=v,
        )
        for p, v in zip(pedazos, vectores, strict=True)
    )
    log.info("documento %s: %s fragmentos indexados", documento_id, len(pedazos))
