"""IA: proveedores intercambiables y generación de fichas.

El proveedor se elige en config/docubot.yaml (ia.proveedor) o con
DOCUBOT_IA__PROVEEDOR. Puede ser uno incluido (ollama, openai, openai_compat,
anthropic) o una extensión propia "archivo.py:Clase" en config/extensiones/.
"""

import importlib.util
import sys
from pathlib import Path

import httpx

from docubot.ajustes import AjustesIA, obtener_ajustes
from docubot.ia.base import Desborde, ErrorIA, ErrorIAPermanente, Proveedor, Respuesta
from docubot.ia.proveedores import INCLUIDOS

__all__ = ["Desborde", "ErrorIA", "ErrorIAPermanente", "Proveedor", "Respuesta", "activo", "obtener"]

_actual: Proveedor | None = None
_de_prueba: Proveedor | None = None


def activo() -> bool:
    """¿Hay un proveedor configurado?"""
    return _de_prueba is not None or obtener_ajustes().ia.proveedor != "ninguno"


def cargar_extension(especificacion: str, carpeta: Path) -> type[Proveedor]:
    """'mi_ia.py:MiIA' → la clase MiIA de config/extensiones/mi_ia.py."""
    archivo, clase = especificacion.split(":", 1)
    ruta = carpeta / archivo
    if not ruta.is_file():
        raise ErrorIAPermanente(f"no existe la extensión {ruta}")
    nombre = f"docubot_extension_{ruta.stem}"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    tipo = getattr(modulo, clase, None)
    if not (isinstance(tipo, type) and issubclass(tipo, Proveedor)):
        raise ErrorIAPermanente(f"{especificacion}: '{clase}' no es una clase de Proveedor")
    return tipo


def crear(ajustes: AjustesIA, transporte: httpx.AsyncBaseTransport | None = None) -> Proveedor:
    if ajustes.proveedor == "ninguno":
        raise ErrorIAPermanente("no hay proveedor de IA configurado (ia.proveedor en config/docubot.yaml)")
    if ajustes.proveedor in INCLUIDOS:
        return INCLUIDOS[ajustes.proveedor](ajustes, transporte)
    tipo = cargar_extension(ajustes.proveedor, obtener_ajustes().carpeta_extensiones)
    return tipo(ajustes, transporte)


def obtener() -> Proveedor:
    """El proveedor del proceso (se crea una vez)."""
    global _actual
    if _de_prueba is not None:
        return _de_prueba
    if _actual is None:
        _actual = crear(obtener_ajustes().ia)
    return _actual


def usar_proveedor(proveedor: Proveedor | None) -> None:
    """Pruebas: reemplaza el proveedor del proceso."""
    global _de_prueba
    _de_prueba = proveedor


async def cerrar() -> None:
    global _actual
    if _actual is not None:
        await _actual.cerrar()
        _actual = None
