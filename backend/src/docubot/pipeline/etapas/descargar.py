"""Etapa descargar: baja el documento de un candidato aceptado y lo guarda por su huella.

- Errores pasajeros (sin conexión, 5xx, 429): la tarea se reintenta.
- Errores definitivos (404, página HTML en lugar del documento, incompleto,
  demasiado grande, robots.txt): se intenta la copia del Internet Archive y,
  si tampoco sirve, el candidato queda `fallido` con su motivo.
"""

import logging
import mimetypes
from dataclasses import dataclass

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from docubot import eventos
from docubot.ajustes import obtener_ajustes
from docubot.db.modelos import Candidato, Corrida, Documento, Tarea
from docubot.descubrimiento.enlaces import extension, nombre_de_archivo
from docubot.documentos import validacion
from docubot.documentos.almacen import Almacen, ArchivoTemporal
from docubot.perfiles.esquema import Perfil
from docubot.pipeline import corridas, procesar
from docubot.red import clientes
from docubot.red.cliente import BloqueadoPorRobots, Cliente, DemasiadoGrande, ErrorRed, SinDNS

log = logging.getLogger("docubot.descargar")

MB = 1024 * 1024
WAYBACK = "https://web.archive.org/web/{fecha}id_/{url}"


class ErrorPasajero(Exception):
    """Vale la pena reintentar más tarde."""


@dataclass
class Bajada:
    archivo: ArchivoTemporal
    respuesta: httpx.Response | None = None
    extension: str = ""
    mime: str | None = None
    motivo: str | None = None  # None = salió bien
    pasajero: bool = False

    @property
    def ok(self) -> bool:
        return self.motivo is None


def _extension(url: str, respuesta: httpx.Response, extensiones: list[str]) -> str:
    ext = extension(url)
    if ext in extensiones:
        return ext
    nombre = nombre_de_archivo(respuesta.headers.get("content-disposition"))
    if nombre and "." in nombre:
        return nombre.rsplit(".", 1)[-1].lower()
    mime = respuesta.headers.get("content-type", "").split(";")[0].strip()
    adivinada = mimetypes.guess_extension(mime) if mime else None
    if adivinada and adivinada.lstrip(".") not in ("html", "htm", "bin"):
        return adivinada.lstrip(".")
    return extensiones[0] if len(extensiones) == 1 else (ext or "bin")


async def bajar(cliente: Cliente, url: str, almacen: Almacen, limite: int, extensiones: list[str]) -> Bajada:
    b = Bajada(almacen.temporal())
    try:
        r = await cliente.descargar(url, b.archivo, max_bytes=limite)
    except BloqueadoPorRobots:
        b.motivo = "robots.txt no permite descargarlo"
        return b
    except DemasiadoGrande:
        b.motivo = f"pesa más de {limite // MB} MB"
        return b
    except SinDNS as error:
        b.motivo = str(error)  # definitivo: se pasa directo al Internet Archive
        return b
    except ErrorRed as error:
        b.motivo, b.pasajero = str(error), True
        return b
    finally:
        b.archivo.cerrar()
    b.respuesta = r
    if r.status_code >= 400:
        b.motivo = f"el sitio respondió {r.status_code}"
        b.pasajero = r.status_code in (408, 425, 429) or r.status_code >= 500
        return b
    b.extension = _extension(str(r.url), r, extensiones)
    b.mime = r.headers.get("content-type", "").split(";")[0].strip() or None
    b.motivo = validacion.revisar(b.archivo, b.extension)
    return b


async def _perfil(sesion: AsyncSession, tarea: Tarea, candidato: Candidato) -> tuple[Perfil, Corrida | None]:
    corrida = await sesion.get(Corrida, tarea.corrida_id) if tarea.corrida_id else None
    if corrida is not None and corrida.perfil_id == candidato.perfil_id:
        return corridas.perfil_de(corrida), corrida
    return await corridas.perfil_por_id(sesion, candidato.perfil_id), corrida


async def ejecutar(sesion: AsyncSession, tarea: Tarea) -> None:
    candidato = await sesion.get(Candidato, tarea.carga["candidato_id"])
    if candidato is None or candidato.documento_id is not None:
        return
    perfil, corrida = await _perfil(sesion, tarea, candidato)
    ajustes = obtener_ajustes().almacen
    almacen = Almacen(ajustes.carpeta)
    limite = (perfil.documentos.tamano_max_mb or ajustes.tamano_max_mb) * MB
    extensiones = perfil.documentos.extensiones
    cliente = clientes.web(perfil.red.peticiones_por_segundo_por_dominio, perfil.red.respetar_robots)
    url = candidato.url
    ultimo_intento = tarea.intentos >= tarea.max_intentos
    await sesion.commit()  # no dejar la transacción abierta durante la descarga

    b = await bajar(cliente, url, almacen, limite, extensiones)
    respaldo = None
    if not b.ok and (not b.pasajero or ultimo_intento) and ajustes.respaldo_wayback and "web.archive.org" not in url:
        fecha = (candidato.datos or {}).get("wayback", "2")
        copia = await bajar(clientes.web(), WAYBACK.format(fecha=fecha, url=url), almacen, limite, extensiones)
        if copia.ok:
            b.archivo.borrar()
            b, respaldo = copia, "wayback"
        else:
            copia.archivo.borrar()

    if not b.ok:
        b.archivo.borrar()
        if b.pasajero and not ultimo_intento:
            raise ErrorPasajero(b.motivo)
        candidato.estado, candidato.motivo = "fallido", b.motivo
        await eventos.publicar(
            sesion, "descarga", corrida_id=tarea.corrida_id, estado="fallido", url=url, motivo=b.motivo
        )
        log.info("no se pudo bajar %s: %s", url, b.motivo)
        return

    sha = b.archivo.sha256
    tamano = b.archivo.bytes
    ruta = almacen.guardar(b.archivo, b.extension)
    consulta = insert(Documento).values(sha256=sha, ruta=ruta, bytes=tamano, mime=b.mime or "application/octet-stream")
    consulta = consulta.on_conflict_do_nothing(index_elements=["sha256"])
    await sesion.execute(consulta)
    documento_id = await sesion.scalar(select(Documento.id).where(Documento.sha256 == sha))

    datos = dict(candidato.datos or {})
    datos["url_final"] = str(b.respuesta.url)
    if respaldo:
        datos["respaldo"] = respaldo
    if corrida is not None:
        referencia = corridas.referencia_de(corrida)
        if referencia is not None and referencia.necesita_archivo:
            nuevo = referencia.es_nuevo(url=candidato.url, tipo=candidato.tipo, lugar=datos.get("lugar"), sha256=sha)
            if nuevo is not None:
                datos["nuevo"] = nuevo
    candidato.documento_id = documento_id
    candidato.estado = "descargado"
    candidato.motivo = None
    candidato.datos = datos
    candidato.actualizado = func.now()
    # lo que sigue: extraer el texto (si es un documento nuevo) o hacer la ficha de este perfil
    actual = await corridas.perfil_por_id(sesion, candidato.perfil_id)  # fichas y lugares: perfil actual
    await procesar.siguiente(sesion, documento_id, candidato.perfil_id, actual, tarea.corrida_id)
    await eventos.publicar(
        sesion,
        "descarga",
        corrida_id=tarea.corrida_id,
        estado="descargado",
        url=url,
        documento_id=documento_id,
        bytes=tamano,
        respaldo=respaldo,
    )
    log.info("bajado %s (%s KB)%s", url, tamano // 1024, " desde el Internet Archive" if respaldo else "")
