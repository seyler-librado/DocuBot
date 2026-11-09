"""Copia los perfiles válidos a la base de datos.

Los archivos YAML son la fuente de verdad; la base guarda la versión con la que
se hizo cada corrida. Un perfil cuyo archivo desaparece NO se borra de la base
(tiene candidatos, documentos y fichas asociados): solo se reporta.
"""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Perfil as PerfilBD
from docubot.perfiles.cargador import PerfilCargado


@dataclass
class ResultadoSincronizacion:
    creados: list[str] = field(default_factory=list)
    actualizados: list[str] = field(default_factory=list)
    sin_cambios: list[str] = field(default_factory=list)
    invalidos: dict[str, list[str]] = field(default_factory=dict)
    sin_archivo: list[str] = field(default_factory=list)


async def sincronizar(sesion: AsyncSession, cargados: list[PerfilCargado]) -> ResultadoSincronizacion:
    resultado = ResultadoSincronizacion()
    existentes = {p.nombre: p for p in (await sesion.scalars(select(PerfilBD))).all()}

    for c in cargados:
        if not c.valido:
            resultado.invalidos[c.nombre] = c.errores
            continue
        perfil = c.perfil
        assert perfil is not None
        fila = existentes.get(perfil.nombre)
        if fila is None:
            sesion.add(
                PerfilBD(
                    nombre=perfil.nombre,
                    descripcion=perfil.descripcion,
                    config=perfil.model_dump(mode="json"),
                    huella=c.huella,
                )
            )
            resultado.creados.append(perfil.nombre)
        elif fila.huella != c.huella:
            fila.descripcion = perfil.descripcion
            fila.config = perfil.model_dump(mode="json")
            fila.huella = c.huella
            fila.actualizado = func.now()
            resultado.actualizados.append(perfil.nombre)
        else:
            resultado.sin_cambios.append(perfil.nombre)

    en_archivos = {c.nombre for c in cargados}
    resultado.sin_archivo = sorted(set(existentes) - en_archivos)
    await sesion.flush()
    return resultado
