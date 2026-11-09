"""Registro de etapas del pipeline.

Una etapa es una función async (sesion, tarea) -> None. Si lanza una excepción,
la tarea se reintenta; si termina, la tarea queda hecha. Cada etapa dice qué
campo de `trabajadores` (config/docubot.yaml) define cuántas corren a la vez.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from docubot.db.modelos import Tarea
from docubot.pipeline.etapas import descargar, descubrir, eco, explorar, extraer, fichar, indexar, ubicar

Funcion = Callable[[AsyncSession, Tarea], Awaitable[None]]


@dataclass(frozen=True)
class Etapa:
    nombre: str
    funcion: Funcion
    trabajadores: str | None  # campo de AjustesTrabajadores; None = siempre 1


ETAPAS: dict[str, Etapa] = {
    "eco": Etapa("eco", eco.ejecutar, None),
    "descubrir": Etapa("descubrir", descubrir.ejecutar, "descubrimiento"),
    "explorar": Etapa("explorar", explorar.ejecutar, "exploracion"),
    "descargar": Etapa("descargar", descargar.ejecutar, "descarga"),
    "extraer": Etapa("extraer", extraer.ejecutar, "extraccion"),
    "fichar": Etapa("fichar", fichar.ejecutar, "ia"),
    "ubicar": Etapa("ubicar", ubicar.ejecutar, "extraccion"),
    "indexar": Etapa("indexar", indexar.ejecutar, "extraccion"),
}
