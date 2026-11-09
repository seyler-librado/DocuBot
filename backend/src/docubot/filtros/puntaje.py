"""Puntaje de un candidato (0 a 100) según el perfil.

En modo `palabras`:
    tipo en el nombre del archivo ......... 85
    tipo en el texto del enlace ........... 80
    tipo solo en la ruta o la consulta .... 50
    sin tipo .............................. 0
    + 10 si trae un año (1980-2035)
    - 15 si el nombre del archivo no dice nada y no hay texto de enlace
En modo `todos`, cualquier documento parte de 70.
Una palabra de `excluir` deja el puntaje en 0.

Queda aceptado si el puntaje llega a `documentos.puntaje_minimo`.
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from docubot.filtros.tipos import Clasificador, normalizar
from docubot.perfiles.esquema import Documentos

ANIO = re.compile(r"(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)")


@dataclass
class Calificacion:
    puntaje: int
    tipo: str | None
    motivo: str
    aceptado: bool

    @property
    def estado(self) -> str:
        return "aceptado" if self.aceptado else "rechazado"


def partes_de(url: str) -> tuple[str, str]:
    """(nombre del archivo sin extensión, resto de la ruta y consulta)."""
    p = urlsplit(url)
    ruta = PurePosixPath(unquote(p.path))
    return ruta.stem, f"{ruta.parent} {unquote(p.query)}"


class Calificador:
    def __init__(self, documentos: Documentos) -> None:
        self.documentos = documentos
        self.clasificador = Clasificador(documentos)
        self.minimo = documentos.puntaje_minimo

    def calificar(self, url: str, ancla: str | None = None) -> Calificacion:
        nombre, ruta = partes_de(url)
        excluida = self.clasificador.palabra_excluida(nombre, ancla)
        if excluida:
            return Calificacion(0, None, f"excluido por «{excluida}»", False)

        motivos: list[str] = []
        if self.documentos.modo == "todos":
            tipo = self.clasificador.tipo_de(nombre, ancla, ruta)
            puntaje = 70
            motivos.append("modo todos")
        elif tipo := self.clasificador.tipo_de(nombre):
            puntaje = 85
            motivos.append("tipo en el nombre del archivo")
        elif tipo := self.clasificador.tipo_de(ancla):
            puntaje = 80
            motivos.append("tipo en el texto del enlace")
        elif tipo := self.clasificador.tipo_de(ruta):
            puntaje = 50
            motivos.append("tipo solo en la ruta")
        else:
            return Calificacion(0, None, "no coincide con ningún tipo", False)

        if ANIO.search(f"{nombre} {ancla or ''}"):
            puntaje += 10
            motivos.append("con año")
        if len(normalizar(nombre)) < 4 and not ancla:
            puntaje -= 15
            motivos.append("nombre poco descriptivo")
        puntaje = max(0, min(100, puntaje))
        return Calificacion(puntaje, tipo, ", ".join(motivos), puntaje >= self.minimo)
