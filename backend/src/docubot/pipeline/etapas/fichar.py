"""Etapa fichar: la IA lee el documento y llena los campos del perfil."""

import asyncio
import logging
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos, ia
from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Documento, Ficha, Tarea, Texto
from docubot.documentos import pdf
from docubot.documentos.almacen import Almacen
from docubot.ia import fichas as F
from docubot.ia.base import Desborde, ErrorIA
from docubot.pipeline import corridas, procesar
from docubot.pipeline.errores import ErrorPermanente

log = logging.getLogger("docubot.fichar")
RECORTES = 3  # si no cabe, se recorta el texto hasta 3 veces


async def _guardar(
    sesion: AsyncSession, documento_id: int, perfil_id: int, corrida_id: int | None = None, **valores
) -> None:
    consulta = insert(Ficha).values(documento_id=documento_id, perfil_id=perfil_id, **valores)
    consulta = consulta.on_conflict_do_update(
        index_elements=["documento_id", "perfil_id"],
        set_={k: consulta.excluded[k] for k in valores} | {"actualizado": func.now()},
    )
    await sesion.execute(consulta)
    campos = valores.get("campos") or {}
    titulo = next((v for k, v in campos.items() if k in ("titulo", "nombre", "title") and v), None)
    await eventos.publicar(
        sesion,
        "ficha",
        corrida_id=corrida_id,
        documento_id=documento_id,
        perfil_id=perfil_id,
        estado=valores.get("estado"),
        confianza=valores.get("confianza"),
        titulo=titulo,
    )


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    await _fichar(sesion, tarea)
    # con la ficha lista (la IA pudo decir el lugar), se ubica el documento
    documento_id, perfil_id = tarea.carga["documento_id"], tarea.carga["perfil_id"]
    perfil = await corridas.perfil_por_id(sesion, perfil_id)  # fichas y lugares siguen el perfil actual
    if perfil.geografia is not None:
        await procesar.encolar_ubicacion(sesion, documento_id, perfil_id, tarea.corrida_id)


async def _fichar(sesion: AsyncSession, tarea: Tarea) -> None:
    documento_id, perfil_id = tarea.carga["documento_id"], tarea.carga["perfil_id"]
    documento = await sesion.get(Documento, documento_id)
    texto = await sesion.get(Texto, documento_id)
    if documento is None:
        return
    if texto is None:
        raise ErrorPermanente("el documento todavía no tiene texto extraído")
    perfil = await corridas.perfil_por_id(sesion, perfil_id)  # fichas y lugares siguen el perfil actual
    tipos = (
        await sesion.scalars(
            select(Candidato.tipo).where(Candidato.documento_id == documento_id, Candidato.perfil_id == perfil_id)
        )
    ).all()
    tipo_esperado = Counter(t for t in tipos if t).most_common(1)[0][0] if any(tipos) else None
    ajustes = obtener_ajustes().ia
    proveedor = ia.obtener()

    if texto.metodo == "ilegible":
        await _guardar(
            sesion,
            documento_id,
            perfil_id,
            tarea.corrida_id,
            campos={},
            estado="ilegible",
            confianza=None,
            motivos=[texto.error or "no se pudo leer"],
            modelo=None,
            version_prompt=F.VERSION_PROMPT,
            control={"metodo": "ninguno"},
        )
        return

    imagenes: list[str] = []
    contenido = ""
    if texto.metodo == "texto":
        metodo = "texto"
        contenido = pdf.Extraccion.desde_contenido(texto.contenido).para_ia(ajustes.paginas, ajustes.max_caracteres)
    elif proveedor.vision and ajustes.vision:
        metodo = "imagen"
        ruta = Almacen(obtener_ajustes().almacen.carpeta).ruta(documento.ruta)
        imagenes = await asyncio.to_thread(pdf.imagenes, ruta, ajustes.paginas_imagen)
    else:
        await _guardar(
            sesion,
            documento_id,
            perfil_id,
            tarea.corrida_id,
            campos={},
            estado="ilegible",
            confianza=None,
            motivos=["está escaneado y el proveedor de IA no lee imágenes"],
            modelo=None,
            version_prompt=F.VERSION_PROMPT,
            control={"metodo": "ninguno"},
        )
        return
    await sesion.commit()  # no dejar la transacción abierta mientras responde la IA

    sistema = F.instrucciones(perfil)
    for recorte in range(RECORTES + 1):
        usuario = F.entrada_texto(contenido) if metodo == "texto" else F.entrada_imagenes(len(imagenes))
        try:
            respuesta = await proveedor.completar(sistema, usuario, imagenes)
            break
        except Desborde:
            if recorte == RECORTES:
                raise ErrorPermanente("el documento no cabe en el modelo aun recortado") from None
            if metodo == "texto":
                contenido = contenido[: int(len(contenido) * 0.7)]
            elif len(imagenes) > 1:
                imagenes = imagenes[:-1]
            else:
                raise ErrorPermanente("ni una sola página cabe en el modelo") from None

    datos = F.json_laxo(respuesta.texto)
    control = {
        "metodo": metodo,
        "proveedor": proveedor.nombre,
        "segundos": respuesta.segundos,
        "tokens_entrada": respuesta.tokens_entrada,
        "tokens_salida": respuesta.tokens_salida,
        "caracteres": len(contenido),
        "imagenes": len(imagenes),
        "tipo_esperado": tipo_esperado,
    }
    if datos is None:
        if tarea.intentos < tarea.max_intentos:
            raise ErrorIA(f"la respuesta no trae JSON: {respuesta.texto[:150]!r}")
        await _guardar(
            sesion,
            documento_id,
            perfil_id,
            tarea.corrida_id,
            campos={},
            estado="error",
            confianza=None,
            motivos=["la IA no devolvió una ficha legible"],
            modelo=respuesta.modelo or proveedor.nombre,
            version_prompt=F.VERSION_PROMPT,
            control=control | {"respuesta": respuesta.texto[:2000]},
        )
        return

    referencia_texto = texto.contenido if metodo == "texto" else ""
    v = F.validar(datos, perfil, referencia_texto)
    motivos = list(v.motivos)
    if aviso := F.contaminada(v.campos, perfil, referencia_texto):
        motivos.append(aviso)
    estado, confianza, motivos = F.calificar(motivos, metodo, v.tipo_ia, tipo_esperado)
    control["tipo_ia"] = v.tipo_ia
    await _guardar(
        sesion,
        documento_id,
        perfil_id,
        tarea.corrida_id,
        campos=v.campos,
        estado=estado,
        confianza=confianza,
        motivos=motivos,
        modelo=respuesta.modelo or proveedor.nombre,
        version_prompt=F.VERSION_PROMPT,
        control=control,
    )
    log.info(
        "ficha del documento %s (%s): %s, confianza %s en %.0fs%s",
        documento_id,
        metodo,
        estado,
        confianza,
        respuesta.segundos,
        f" — {'; '.join(motivos)}" if motivos else "",
    )
