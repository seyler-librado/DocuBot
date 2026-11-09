"""Almacén de documentos por huella.

Cada archivo vive en  <carpeta>/ab/cd/<sha256>.<ext>  (las dos primeras parejas
de la huella reparten los archivos en subcarpetas). El mismo contenido bajado
de dos URLs se guarda una sola vez. Las descargas en curso van a <carpeta>/.tmp
para que mover el archivo terminado sea instantáneo (mismo disco).
"""

import hashlib
import os
import uuid
from pathlib import Path

VENTANA = 4096  # bytes que se guardan del inicio y del final para validar


class ArchivoTemporal:
    """Destino de una descarga: escribe a disco y calcula la huella al vuelo."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self._f = None
        self.reiniciar()

    def reiniciar(self) -> None:
        """Empieza de cero (p. ej. si se reintenta la descarga)."""
        self.cerrar()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.ruta.open("wb")
        self._sha = hashlib.sha256()
        self.bytes = 0
        self.inicio = b""
        self.final = b""

    def escribir(self, datos: bytes) -> None:
        self._f.write(datos)
        self._sha.update(datos)
        self.bytes += len(datos)
        if len(self.inicio) < VENTANA:
            self.inicio += datos[: VENTANA - len(self.inicio)]
        self.final = (self.final + datos)[-VENTANA:]

    @property
    def sha256(self) -> str:
        return self._sha.hexdigest()

    def cerrar(self) -> None:
        if self._f is not None and not self._f.closed:
            self._f.close()

    def borrar(self) -> None:
        self.cerrar()
        self.ruta.unlink(missing_ok=True)


class Almacen:
    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)

    def temporal(self) -> ArchivoTemporal:
        return ArchivoTemporal(self.carpeta / ".tmp" / f"{uuid.uuid4().hex}.part")

    @staticmethod
    def relativa(sha256: str, extension: str) -> str:
        return f"{sha256[:2]}/{sha256[2:4]}/{sha256}.{extension or 'bin'}"

    def ruta(self, relativa: str) -> Path:
        return self.carpeta / relativa

    def guardar(self, temporal: ArchivoTemporal, extension: str) -> str:
        """Mueve la descarga terminada a su lugar definitivo. Devuelve la ruta relativa."""
        temporal.cerrar()
        relativa = self.relativa(temporal.sha256, extension)
        destino = self.ruta(relativa)
        if destino.exists():
            temporal.borrar()  # ya lo teníamos
        else:
            destino.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporal.ruta, destino)
        return relativa
