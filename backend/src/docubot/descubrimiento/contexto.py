"""Lo que una fuente o la exploración necesitan para guardar lo que encuentran."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Candidato, Corrida, Sitio
from docubot.filtros.dominios import FiltroDominios
from docubot.filtros.puntaje import Calificador
from docubot.perfiles.esquema import Perfil
from docubot.pipeline import cola, corridas, descargas
from docubot.red import clientes
from docubot.red.cliente import Cliente
from docubot.red.urls import clave_url, host_de

log = logging.getLogger("docubot.descubrimiento")

MAX_SEMILLAS = 50
LOTE = 500


@dataclass
class NuevoCandidato:
    url: str
    fuente: str
    ancla: str | None = None
    pagina_origen: str | None = None
    profundidad: int | None = None
    sitio_id: int | None = None
    lugar: str | None = None  # clave del catálogo de geografía
    datos: dict[str, Any] = field(default_factory=dict)


def dominio_de(valor: str) -> str:
    """'https://www.Sitio.gob.mx/x' o 'sitio.gob.mx' → 'sitio.gob.mx'."""
    valor = valor.strip()
    host = host_de(valor if "://" in valor else f"http://{valor}")
    return host.removeprefix("www.")


class Contexto:
    def __init__(self, sesion: AsyncSession, corrida: Corrida, perfil: Perfil, carpeta: Path) -> None:
        self.sesion = sesion
        self.corrida = corrida
        self.perfil = perfil
        self.carpeta = carpeta
        d = perfil.descubrimiento.dominios
        self.filtro = FiltroDominios(d.permitir, d.bloquear)
        self.calificador = Calificador(perfil.documentos)
        self.referencia = corridas.referencia_de(corrida)

    @property
    def cliente_web(self) -> Cliente:
        red = self.perfil.red
        return clientes.web(red.peticiones_por_segundo_por_dominio, red.respetar_robots)

    @property
    def cliente_api(self) -> Cliente:
        return clientes.api()

    async def encolar(self, etapa: str, carga: dict[str, Any], prioridad: int = 0) -> None:
        await cola.encolar(self.sesion, etapa, carga, corrida_id=self.corrida.id, prioridad=prioridad)

    async def agregar_sitio(
        self,
        dominio_o_url: str,
        *,
        origen: str,
        semillas: list[str] | tuple[str, ...] = (),
        lugar: str | None = None,
    ) -> bool:
        """Registra un sitio para explorarlo en esta corrida. True si es nuevo en la corrida."""
        dominio = dominio_de(dominio_o_url)
        if not dominio or not self.filtro.permitido(dominio):
            return False
        consulta = insert(Sitio).values(dominio=dominio, origen=origen)
        consulta = consulta.on_conflict_do_update(
            index_elements=["dominio"], set_={"dominio": consulta.excluded.dominio}
        ).returning(Sitio.id)
        sitio_id = (await self.sesion.execute(consulta)).scalar_one()
        nuevo = (
            await self.sesion.execute(
                text(
                    """
                    INSERT INTO corrida_sitios (corrida_id, sitio_id, origen, semillas, lugar)
                    VALUES (:corrida, :sitio, :origen, CAST(:semillas AS jsonb), :lugar)
                    ON CONFLICT (corrida_id, sitio_id) DO UPDATE SET
                      semillas = CASE
                        WHEN jsonb_array_length(corrida_sitios.semillas) < :maximo
                        THEN corrida_sitios.semillas || EXCLUDED.semillas
                        ELSE corrida_sitios.semillas END,
                      lugar = COALESCE(corrida_sitios.lugar, EXCLUDED.lugar)
                    RETURNING (xmax = 0) AS nuevo
                    """
                ),
                {
                    "corrida": self.corrida.id,
                    "sitio": sitio_id,
                    "origen": origen,
                    "semillas": json.dumps(list(semillas)),
                    "lugar": lugar,
                    "maximo": MAX_SEMILLAS,
                },
            )
        ).scalar_one()
        if nuevo:
            await self.encolar("explorar", {"sitio_id": sitio_id})
        return bool(nuevo)

    async def agregar_candidatos(self, nuevos: list[NuevoCandidato]) -> int:
        """Guarda candidatos sin duplicar (por perfil y URL normalizada), con su puntaje.

        Los aceptados que no tienen documento se encolan para descarga (si la
        corrida descarga). Devuelve cuántos se enviaron.
        """
        filas: dict[str, dict[str, Any]] = {}
        for n in nuevos:
            clave = clave_url(n.url)
            if not clave or clave in filas:
                continue
            datos = dict(n.datos)
            if n.lugar:
                datos["lugar"] = n.lugar
            nota = self.calificador.calificar(n.url, n.ancla)
            if self.referencia is not None and not self.referencia.necesita_archivo:
                nuevo = self.referencia.es_nuevo(url=n.url, tipo=nota.tipo, lugar=n.lugar)
                if nuevo is not None:
                    datos["nuevo"] = nuevo
            filas[clave] = {
                "perfil_id": self.corrida.perfil_id,
                "corrida_id": self.corrida.id,
                "sitio_id": n.sitio_id,
                "url": n.url,
                "clave_url": clave,
                "fuente": n.fuente,
                "ancla": (n.ancla or None) and n.ancla[:1000],
                "pagina_origen": n.pagina_origen,
                "profundidad": n.profundidad,
                "tipo": nota.tipo,
                "puntaje": nota.puntaje,
                "estado": nota.estado,
                "motivo": nota.motivo,
                "datos": datos,
            }
        lista = list(filas.values())
        por_descargar: list[tuple[int, int]] = []
        for i in range(0, len(lista), LOTE):
            consulta = insert(Candidato).values(lista[i : i + LOTE])
            consulta = consulta.on_conflict_do_update(
                index_elements=["perfil_id", "clave_url"],
                set_={
                    # la última corrida que lo vio; lo ya conocido no se pierde
                    "corrida_id": consulta.excluded.corrida_id,
                    "actualizado": func.now(),
                    "ancla": func.coalesce(Candidato.ancla, consulta.excluded.ancla),
                    "sitio_id": func.coalesce(Candidato.sitio_id, consulta.excluded.sitio_id),
                    "tipo": func.coalesce(Candidato.tipo, consulta.excluded.tipo),
                    "pagina_origen": func.coalesce(Candidato.pagina_origen, consulta.excluded.pagina_origen),
                    "datos": consulta.excluded.datos.op("||")(Candidato.datos),
                    # si ahora califica mejor (p. ej. trae texto de enlace) se acepta;
                    # lo descargado o fallido no se toca
                    "puntaje": func.greatest(Candidato.puntaje, consulta.excluded.puntaje),
                    "estado": case(
                        (
                            Candidato.estado.in_(["nuevo", "rechazado"]) & (consulta.excluded.estado == "aceptado"),
                            "aceptado",
                        ),
                        (Candidato.estado == "nuevo", consulta.excluded.estado),
                        else_=Candidato.estado,
                    ),
                    "motivo": case(
                        (
                            consulta.excluded.puntaje > func.coalesce(Candidato.puntaje, -1),
                            consulta.excluded.motivo,
                        ),
                        else_=Candidato.motivo,
                    ),
                },
            ).returning(Candidato.id, Candidato.estado, Candidato.documento_id, Candidato.puntaje)
            for cid, estado, documento_id, puntaje in await self.sesion.execute(consulta):
                if estado == "aceptado" and documento_id is None:
                    por_descargar.append((cid, puntaje))
        if por_descargar and corridas.descarga_activa(self.corrida):
            await descargas.encolar(self.sesion, self.corrida.id, por_descargar)
        return len(lista)
