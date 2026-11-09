"""Estado del proveedor de IA y prueba de ida y vuelta."""

from typing import Any

from fastapi import APIRouter

from docubot import ia
from docubot.ajustes import obtener_ajustes

ruta = APIRouter(prefix="/api/ia", tags=["ia"])


async def salud() -> dict[str, Any]:
    ajustes = obtener_ajustes().ia
    if ajustes.proveedor == "ninguno":
        return {"proveedor": "ninguno", "ok": None, "detalle": "sin IA configurada: no se hacen fichas"}
    try:
        proveedor = ia.obtener()
    except Exception as error:
        return {"proveedor": ajustes.proveedor, "ok": False, "detalle": str(error)}
    return {"proveedor": proveedor.nombre, "vision": proveedor.vision and ajustes.vision} | await proveedor.salud()


async def probar() -> dict[str, Any]:
    datos = await salud()
    if datos.get("ok") is False or datos["proveedor"] == "ninguno":
        return datos
    try:
        r = await ia.obtener().completar("Responde exactamente lo que se te pide.", "Di exactamente: HOLA")
        datos |= {"eco": r.texto.strip()[:100], "segundos": r.segundos, "modelo_respuesta": r.modelo}
        datos["ok"] = "HOLA" in r.texto.upper()
    except Exception as error:
        datos |= {"ok": False, "detalle": f"{type(error).__name__}: {error}"}
    return datos


@ruta.get("/salud")
async def ruta_salud() -> dict[str, Any]:
    return await salud()


@ruta.post("/probar")
async def ruta_probar() -> dict[str, Any]:
    return await probar()
