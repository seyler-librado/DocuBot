"""Referencia: lo que ya se tiene. Sirve para marcar como «nuevo» lo que no está ahí.

El CSV de referencia necesita las columnas que el perfil pone en `llave`, que
pueden ser:
    url     la URL del documento (se compara normalizada)
    tipo    la clave del tipo de documento (PMD, ATLAS...)
    lugar   la clave del lugar en el catálogo de geografía
    sha256  la huella del archivo (solo se puede comparar después de descargarlo)
"""

from pathlib import Path

from docubot.descubrimiento.variables import leer_csv
from docubot.perfiles.esquema import Referencia as ConfigReferencia
from docubot.red.urls import clave_url


def _normal(campo: str, valor: str | None) -> str | None:
    if valor is None or not str(valor).strip():
        return None
    valor = str(valor).strip()
    return clave_url(valor) if campo == "url" else valor.lower()


class Referencia:
    def __init__(self, config: ConfigReferencia, carpeta: Path) -> None:
        self.llave = list(config.llave)
        self.claves: set[tuple[str | None, ...]] = set()
        for fila in leer_csv(carpeta / config.archivo):
            clave = tuple(_normal(c, fila.get(c)) for c in self.llave)
            if all(v is not None for v in clave):
                self.claves.add(clave)

    @property
    def necesita_archivo(self) -> bool:
        return "sha256" in self.llave

    def es_nuevo(self, **valores: str | None) -> bool | None:
        """True si no está en la referencia; None si falta algún dato de la llave para saberlo."""
        clave = tuple(_normal(c, valores.get(c)) for c in self.llave)
        if any(v is None for v in clave):
            return None
        return clave not in self.claves
