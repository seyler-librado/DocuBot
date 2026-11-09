"""Perfiles: listar, ver detalle con errores de validación, sincronizar con la base."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from docubot.ajustes import obtener_ajustes
from docubot.db.sesion import sesion_api
from docubot.perfiles import PerfilCargado, cargar_todos
from docubot.perfiles.sincronizar import sincronizar

ruta = APIRouter(prefix="/api/perfiles", tags=["perfiles"])


def _resumen(c: PerfilCargado) -> dict[str, Any]:
    carpeta = obtener_ajustes().carpeta_perfiles
    try:
        archivo = str(c.archivo.relative_to(carpeta))
    except ValueError:
        archivo = c.archivo.name
    datos: dict[str, Any] = {
        "nombre": c.nombre,
        "archivo": archivo,
        "valido": c.valido,
        "errores": c.errores,
    }
    if c.perfil is not None:
        p = c.perfil
        datos |= {
            "descripcion": p.descripcion,
            "fuentes": [f.tipo for f in p.descubrimiento.fuentes],
            "dominios": p.descubrimiento.dominios.permitir,
            "modo": p.documentos.modo,
            "tipos_documento": {k: t.nombre for k, t in p.documentos.tipos.items()},
            "campos": list(p.fichas.campos),
            "geografia": p.geografia is not None,
            "catalogo": p.geografia.identificador if p.geografia else None,
        }
    return datos


def _cargados() -> list[PerfilCargado]:
    return cargar_todos(obtener_ajustes().carpeta_perfiles)


@ruta.get("")
async def listar() -> list[dict[str, Any]]:
    return [_resumen(c) for c in _cargados()]


@ruta.get("/{nombre}")
async def detalle(nombre: str) -> dict[str, Any]:
    for c in _cargados():
        if c.nombre == nombre:
            datos = _resumen(c)
            datos["config"] = c.perfil.model_dump(mode="json") if c.perfil else None
            return datos
    raise HTTPException(404, f"no hay un perfil llamado '{nombre}'")


@ruta.get("/{nombre}/yaml", response_class=PlainTextResponse)
async def yaml_del_perfil(nombre: str) -> str:
    for c in _cargados():
        if c.nombre == nombre:
            return c.archivo.read_text(encoding="utf-8")
    raise HTTPException(404, f"no hay un perfil llamado '{nombre}'")


@ruta.post("/sincronizar")
async def sincronizar_perfiles(sesion: AsyncSession = Depends(sesion_api)) -> dict[str, Any]:
    resultado = await sincronizar(sesion, _cargados())
    await sesion.commit()
    return asdict(resultado)
