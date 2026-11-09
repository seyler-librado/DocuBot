"""Servidor web simulado para las pruebas (sin red real)."""

import httpx


def html(*enlaces: tuple[str, str], extra: str = "") -> httpx.Response:
    """Página HTML con enlaces [(href, texto)]."""
    cuerpo = "".join(f'<a href="{href}">{texto}</a>\n' for href, texto in enlaces)
    return httpx.Response(
        200, headers={"Content-Type": "text/html; charset=utf-8"}, text=f"<html><body>{cuerpo}{extra}</body></html>"
    )


def pdf(contenido: bytes = b"%PDF-1.4 prueba") -> httpx.Response:
    return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=contenido)


class Servidor:
    """Responde según un mapa {url: respuesta | lista de respuestas | función | excepción}.

    Busca primero la URL exacta y luego sin la consulta (?...). Lo que no está responde 404.
    """

    def __init__(self, rutas: dict):
        self.rutas = rutas
        self.peticiones: list[httpx.Request] = []

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        url = str(peticion.url)
        r = self.rutas.get(url, self.rutas.get(url.split("?", 1)[0]))
        if r is None:
            return httpx.Response(404, text="no")
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if callable(r) and not isinstance(r, httpx.Response):
            r = r(peticion)
        if isinstance(r, Exception):
            raise r
        return r

    def urls(self) -> list[str]:
        return [str(p.url) for p in self.peticiones]

    def pedidas(self, prefijo: str) -> list[str]:
        return [u for u in self.urls() if u.startswith(prefijo)]


def pdf_con_texto(paginas: list[str]) -> bytes:
    """Un PDF de verdad, con una página por texto (vacío = página sin texto, como escaneada)."""

    def escapa(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    n = len(paginas)
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(n))}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, texto in enumerate(paginas):
        lineas = " ".join(f"({escapa(linea)}) Tj T*" for linea in texto.split("\n")) if texto else ""
        flujo = f"BT /F1 11 Tf 50 750 Td 14 TL {lineas} ET".encode("latin-1")
        objetos.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
            ).encode()
        )
        objetos.append(b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream")
    salida = b"%PDF-1.4\n"
    posiciones = []
    for k, o in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % k + o + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return salida
