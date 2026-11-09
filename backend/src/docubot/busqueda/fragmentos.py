"""Parte el texto de un documento en fragmentos (con su página) para la búsqueda por tema."""

import re
from dataclasses import dataclass

from docubot.documentos.pdf import Extraccion


@dataclass
class Pedazo:
    orden: int
    pagina: int
    texto: str


def partir(contenido: str, tamano: int = 900, solape: int = 150, maximo: int = 400) -> list[Pedazo]:
    """Fragmentos de ~`tamano` caracteres que se enciman `solape`, sin cortar palabras ni cruzar páginas."""
    salida: list[Pedazo] = []
    for i, texto in enumerate(Extraccion.desde_contenido(contenido).textos):
        texto = re.sub(r"\s+", " ", texto).strip()
        inicio = 0
        while texto and inicio < len(texto) and len(salida) < maximo:
            fin = min(len(texto), inicio + tamano)
            if fin < len(texto):  # cortar en un espacio, no a media palabra
                espacio = texto.rfind(" ", inicio + tamano // 2, fin)
                fin = espacio if espacio > 0 else fin
            pedazo = texto[inicio:fin].strip()
            if len(pedazo) >= 40:  # los pedazos minúsculos (folios, encabezados sueltos) no aportan
                salida.append(Pedazo(len(salida), i + 1, pedazo))
            if fin >= len(texto):
                break
            inicio = max(fin - solape, inicio + 1)
        if len(salida) >= maximo:
            break
    return salida
