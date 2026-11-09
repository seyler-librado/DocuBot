"""Etapa explorar: recorre un sitio y guarda los documentos que encuentra."""

import logging

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos
from docubot.db.modelos import Corrida, CorridaSitio, Sitio, Tarea
from docubot.descubrimiento.contexto import Contexto, NuevoCandidato
from docubot.descubrimiento.explorador import Explorador
from docubot.pipeline import corridas

log = logging.getLogger("docubot.explorar")
_avisado_js: set[int] = set()


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    corrida = await sesion.get(Corrida, tarea.corrida_id)
    perfil = corridas.perfil_de(corrida)
    cs = await sesion.get(CorridaSitio, (corrida.id, tarea.carga["sitio_id"]))
    sitio = await sesion.get(Sitio, tarea.carga["sitio_id"])
    ctx = Contexto(sesion, corrida, perfil, corridas.carpeta_de(corrida))
    if perfil.descubrimiento.exploracion.javascript and corrida.id not in _avisado_js:
        _avisado_js.add(corrida.id)
        log.warning("exploracion.javascript todavía no está disponible; se explora sin navegador")
    semillas = list(cs.semillas)
    await sesion.commit()  # no dejar la transacción abierta mientras se explora

    r = await Explorador(ctx.cliente_web, perfil).explorar(sitio.dominio, semillas)

    await ctx.agregar_candidatos(
        [
            NuevoCandidato(
                d.url,
                "crawler",
                ancla=d.ancla,
                pagina_origen=d.pagina_origen,
                profundidad=d.profundidad,
                sitio_id=sitio.id,
                lugar=cs.lugar,
                datos={"verificado": d.verificado, "mime": d.mime, "externo": d.externo},
            )
            for d in r.documentos
        ]
    )
    cs.estado, cs.paginas, cs.documentos = r.estado, r.paginas, len(r.documentos)
    cs.segundos, cs.error, cs.terminado = r.segundos, r.error, func.now()
    sitio.estado, sitio.error, sitio.ultima_visita = r.estado, r.error, func.now()
    sitio.datos = {**sitio.datos, "url_final": r.url_final, "urls_sitemap": r.urls_sitemap}
    await eventos.publicar(
        sesion,
        "sitio",
        corrida_id=corrida.id,
        dominio=sitio.dominio,
        estado=r.estado,
        paginas=r.paginas,
        documentos=len(r.documentos),
    )
    log.info(
        "%s: %s, %s páginas, %s documentos en %.0fs",
        sitio.dominio,
        r.estado,
        r.paginas,
        len(r.documentos),
        r.segundos,
    )
