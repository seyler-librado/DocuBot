"""Reconoce el tipo de documento de un enlace (URL + texto del enlace) según el perfil.

Los textos se normalizan antes de comparar: sin acentos, en minúsculas, con
%20, guiones, puntos y guiones bajos convertidos en espacios. Así
'PLAN_Municipal-de%20Desarrollo.pdf' coincide con el patrón 'plan\\s*municipal'.
"""

import re
import unicodedata
from urllib.parse import unquote

from docubot.perfiles.esquema import Documentos

SEPARADORES = re.compile(r"[_\-+./\\=&?:]+")
ESPACIOS = re.compile(r"\s+")


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar(texto: str) -> str:
    texto = sin_acentos(unquote(texto)).lower()
    texto = SEPARADORES.sub(" ", texto)
    return ESPACIOS.sub(" ", texto).strip()


class Clasificador:
    def __init__(self, documentos: Documentos) -> None:
        self.modo = documentos.modo
        self._tipos: list[tuple[str, list[re.Pattern[str]], list[str]]] = []
        for clave, tipo in documentos.tipos.items():
            patrones = [re.compile(sin_acentos(p), re.IGNORECASE) for p in tipo.patrones]
            palabras = [normalizar(p) for p in tipo.palabras]
            self._tipos.append((clave, patrones, palabras))
        self._excluir = [normalizar(p) for p in documentos.excluir if p.strip()]

    def tipo_de(self, *textos: str | None) -> str | None:
        """La clave del primer tipo que coincide, o None."""
        texto = normalizar(" ".join(t for t in textos if t))
        if not texto:
            return None
        for clave, patrones, palabras in self._tipos:
            if any(p.search(texto) for p in patrones) or any(
                re.search(rf"\b{re.escape(w)}\b", texto) for w in palabras
            ):
                return clave
        return None

    def palabra_excluida(self, *textos: str | None) -> str | None:
        texto = normalizar(" ".join(t for t in textos if t))
        return next((w for w in self._excluir if re.search(rf"\b{re.escape(w)}\b", texto)), None)

    def excluido(self, *textos: str | None) -> bool:
        return self.palabra_excluida(*textos) is not None

    def interesa(self, *textos: str | None) -> bool:
        """¿Vale la pena revisar este enlace? (en modo todos, cualquiera sirve)."""
        return self.modo == "todos" or self.tipo_de(*textos) is not None
