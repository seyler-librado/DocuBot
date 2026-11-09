"""Etapa ubicar: decide dónde aplica un documento según el catálogo del perfil."""

import logging
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos
from docubot.db.modelos import Candidato, DocumentoLugar, Ficha, Tarea, Texto
from docubot.documentos import pdf
from docubot.geo.ubicar import decidir, indice_de
from docubot.pipeline import corridas
from docubot.pipeline.errores import ErrorPermanente

log = logging.getLogger("docubot.ubicar")
TITULOS = ("titulo", "nombre", "title")


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    documento_id, perfil_id = tarea.carga["documento_id"], tarea.carga["perfil_id"]
    perfil = await corridas.perfil_por_id(sesion, perfil_id)  # fichas y lugares siguen el perfil actual
    if perfil.geografia is None:
        return
    catalogo = perfil.geografia.identificador
    indice = await indice_de(sesion, catalogo)
    if indice is None:
        raise ErrorPermanente(
            f"el catálogo de lugares '{catalogo}' no está importado (docubot lugares importar {perfil.nombre})"
        )

    # lo que dice la fuente: la clave de lugar de las filas que encontraron el documento
    claves = [
        (datos or {}).get("lugar")
        for datos in await sesion.scalars(
            select(Candidato.datos).where(Candidato.documento_id == documento_id, Candidato.perfil_id == perfil_id)
        )
    ]
    clave_fuente = Counter(c for c in claves if c).most_common(1)[0][0] if any(claves) else None

    texto = await sesion.get(Texto, documento_id)
    contenido = (
        pdf.Extraccion.desde_contenido(texto.contenido).para_ia(12, 20000) if texto and texto.metodo == "texto" else ""
    )
    ficha = await sesion.scalar(select(Ficha).where(Ficha.documento_id == documento_id, Ficha.perfil_id == perfil_id))
    campos = ficha.campos if ficha else {}
    titulo = next((str(campos[k]) for k in TITULOS if campos.get(k)), "")
    tipos_lugar = [n for n, c in perfil.fichas.campos.items() if c.tipo == "lugar"]
    lugar_ia = " ".join(str(campos[n]) for n in tipos_lugar if campos.get(n))

    u = decidir(indice, clave_fuente, contenido, titulo=titulo, lugar_ia=lugar_ia)

    await sesion.execute(
        delete(DocumentoLugar).where(
            DocumentoLugar.documento_id == documento_id,
            DocumentoLugar.catalogo == catalogo,
            DocumentoLugar.origen != "manual",
        )
    )
    manual = await sesion.scalar(
        select(DocumentoLugar.id).where(
            DocumentoLugar.documento_id == documento_id,
            DocumentoLugar.catalogo == catalogo,
            DocumentoLugar.origen == "manual",
        )
    )
    if manual is None:  # lo que eligió una persona no se pisa
        sesion.add(
            DocumentoLugar(
                documento_id=documento_id,
                lugar_id=u.lugar_id,
                catalogo=catalogo,
                origen=u.origen,
                confianza=u.confianza,
                estado=u.estado,
                candidatos=u.candidatos,
            )
        )
    nombre = indice.por_id[u.lugar_id].nombre if u.lugar_id else None
    await eventos.publicar(
        sesion, "lugar", corrida_id=tarea.corrida_id, documento_id=documento_id, estado=u.estado, lugar=nombre
    )
    log.info("documento %s: %s (%s, %s)", documento_id, nombre or "sin lugar", u.origen, u.estado)
