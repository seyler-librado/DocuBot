"""Texto de un PDF, a prueba de PDFs rotos.

- Se extrae el texto de todas las páginas (para la búsqueda), con un tope.
- Si casi no hay texto, el PDF está escaneado: la IA lo lee por imagen
  (ver `imagenes`).
- Si no abre (archivo dañado, protegido), se dice por qué.
pypdf primero; si no puede con el archivo, pypdfium2 (el motor de Chrome),
que tolera más PDFs rotos.
"""

import base64
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logging.getLogger("pypdf").setLevel(logging.ERROR)  # avisa por cada objeto raro

MIN_CARACTERES = 200  # por debajo, no hay con qué hacer una ficha: se lee por imagen
MAX_CARACTERES = 3_000_000
SEPARADOR = "\n\n[página {n}]\n"


@dataclass
class Extraccion:
    estado: str  # texto | escaneado | ilegible
    paginas: int = 0
    textos: list[str] = field(default_factory=list)  # uno por página
    error: str | None = None

    @property
    def caracteres(self) -> int:
        return sum(len(t) for t in self.textos)

    @property
    def contenido(self) -> str:
        return "".join(SEPARADOR.format(n=i + 1) + t for i, t in enumerate(self.textos) if t).strip()

    @classmethod
    def desde_contenido(cls, contenido: str, estado: str = "texto") -> "Extraccion":
        """Rehace las páginas a partir de lo guardado en la base (`contenido`)."""
        partes = re.split(r"(?:^|\n\n)\[página (\d+)\]\n", contenido or "")
        textos: dict[int, str] = {}
        for i in range(1, len(partes) - 1, 2):
            textos[int(partes[i]) - 1] = partes[i + 1]
        n = max(textos) + 1 if textos else 0
        return cls(estado, paginas=n, textos=[textos.get(i, "") for i in range(n)])

    def para_ia(self, paginas: int, max_caracteres: int) -> str:
        """Las primeras páginas (y, si casi no traen texto, las últimas: ahí suelen ir decretos y firmas)."""
        elegidas = list(range(min(len(self.textos), paginas)))
        if sum(len(self.textos[i]) for i in elegidas) < 80 * max(len(elegidas), 1) and len(self.textos) > paginas:
            elegidas += list(range(max(paginas, len(self.textos) - 3), len(self.textos)))
        texto = "".join(SEPARADOR.format(n=i + 1) + self.textos[i] for i in elegidas if self.textos[i]).strip()
        return texto[:max_caracteres]


def _limpia(t: str) -> str:
    t = t.replace("\x00", "")
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _con_pypdf(ruta: Path) -> list[str]:
    from pypdf import PdfReader

    with ruta.open("rb") as f:
        lector = PdfReader(f)
        if lector.is_encrypted:
            lector.decrypt("")
        textos, total = [], 0
        for pagina in lector.pages:
            try:
                t = _limpia(pagina.extract_text() or "")
            except Exception:  # una página mala no invalida las demás
                t = ""
            textos.append(t)
            total += len(t)
            if total > MAX_CARACTERES:
                break
        return textos


def _con_pdfium(ruta: Path) -> list[str]:
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(str(ruta))
    try:
        textos, total = [], 0
        for i in range(len(documento)):
            try:
                t = _limpia(documento[i].get_textpage().get_text_range())
            except Exception:
                t = ""
            textos.append(t)
            total += len(t)
            if total > MAX_CARACTERES:
                break
        return textos
    finally:
        documento.close()


def extraer(ruta: Path) -> Extraccion:
    ruta = Path(ruta)
    try:
        if ruta.stat().st_size == 0:
            return Extraccion("ilegible", error="archivo vacío")
    except OSError as error:
        return Extraccion("ilegible", error=str(error))
    try:
        textos = _con_pypdf(ruta)
    except Exception as error_pypdf:
        try:
            textos = _con_pdfium(ruta)
        except Exception:
            return Extraccion(
                "ilegible", error=f"no se pudo abrir el PDF: {type(error_pypdf).__name__}: {error_pypdf}"[:300]
            )
    e = Extraccion("texto", paginas=len(textos), textos=textos)
    if e.caracteres < MIN_CARACTERES:
        e.estado = "escaneado"
    return e


def portada(ruta: Path, ancho: int = 360, calidad: int = 78) -> bytes:
    """La primera página como JPEG (para la biblioteca)."""
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(str(ruta))
    try:
        pagina = documento[0]
        imagen = pagina.render(scale=ancho / pagina.get_width()).to_pil().convert("RGB")
        buf = io.BytesIO()
        imagen.save(buf, "JPEG", quality=calidad, optimize=True)
        return buf.getvalue()
    finally:
        documento.close()


def imagenes(ruta: Path, paginas: int = 3, lado: int = 1100, calidad: int = 80) -> list[str]:
    """Las primeras páginas como JPEG en base64 (para leerlas por visión)."""
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(str(ruta))
    salida = []
    try:
        for i in range(min(len(documento), paginas)):
            pagina = documento[i]
            escala = lado / max(pagina.get_size())
            imagen = pagina.render(scale=escala).to_pil().convert("RGB")
            buf = io.BytesIO()
            imagen.save(buf, "JPEG", quality=calidad)
            salida.append(base64.b64encode(buf.getvalue()).decode())
    finally:
        documento.close()
    return salida
