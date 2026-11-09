"""Cliente HTTP contra servidores simulados (httpx.MockTransport): sin red real."""

import asyncio
import gzip
import ssl
import time

import httpx
import pytest
from simulado import Servidor

from docubot.ajustes import AjustesRed
from docubot.red.cliente import BloqueadoPorRobots, Cliente, DemasiadoGrande, ErrorRed, SinDNS

UA = "DocuBot/9.9 (+https://ejemplo.org/bot)"


def cliente(servidor: Servidor, *, sin_tls: Servidor | None = None, **red) -> Cliente:
    ajustes = AjustesRed(user_agent=UA, peticiones_por_segundo_por_dominio=1000, **red)
    return Cliente(
        ajustes,
        transporte=httpx.MockTransport(servidor),
        transporte_sin_tls=httpx.MockTransport(sin_tls) if sin_tls else None,
        espera_base=0.01,
    )


async def test_se_identifica_y_lee_robots_una_vez_por_sitio():
    s = Servidor(
        {
            "https://a.mx/robots.txt": httpx.Response(200, text="User-agent: *\nAllow: /"),
            "https://a.mx/uno": httpx.Response(200, text="uno"),
            "https://a.mx/dos": httpx.Response(200, text="dos"),
        }
    )
    async with cliente(s) as c:
        assert (await c.obtener("https://a.mx/uno")).text == "uno"
        assert (await c.obtener("https://a.mx/dos")).text == "dos"
    assert s.urls().count("https://a.mx/robots.txt") == 1
    assert all(p.headers["user-agent"] == UA for p in s.peticiones)


async def test_respeta_robots_para_su_nombre():
    robots = "User-agent: DocuBot\nDisallow: /privado\n\nUser-agent: *\nDisallow: /"
    s = Servidor(
        {
            "https://a.mx/robots.txt": httpx.Response(200, text=robots),
            "https://a.mx/publico.pdf": httpx.Response(200, content=b"%PDF"),
        }
    )
    async with cliente(s) as c:
        assert (await c.obtener("https://a.mx/publico.pdf")).content == b"%PDF"
        with pytest.raises(BloqueadoPorRobots):
            await c.obtener("https://a.mx/privado/x.pdf")
    assert "https://a.mx/privado/x.pdf" not in s.urls()


async def test_robots_404_permite_y_503_bloquea():
    s = Servidor(
        {
            "https://sin-robots.mx/x": httpx.Response(200, text="ok"),
            "https://caido.mx/robots.txt": httpx.Response(503),
            "https://caido.mx/x": httpx.Response(200, text="ok"),
        }
    )
    async with cliente(s, reintentos=0) as c:
        assert (await c.obtener("https://sin-robots.mx/x")).text == "ok"
        with pytest.raises(BloqueadoPorRobots):
            await c.obtener("https://caido.mx/x")


async def test_se_puede_desactivar_robots():
    s = Servidor({"https://a.mx/x": httpx.Response(200, text="ok")})
    async with cliente(s, respetar_robots=False) as c:
        assert (await c.obtener("https://a.mx/x")).text == "ok"
    assert s.urls() == ["https://a.mx/x"]


async def test_reintenta_503_con_retry_after_y_errores_de_conexion():
    s = Servidor(
        {
            "https://a.mx/x": [
                httpx.Response(503, headers={"Retry-After": "0"}),
                httpx.ConnectError("se cayó"),
                httpx.Response(200, text="por fin"),
            ],
        }
    )
    async with cliente(s, reintentos=3, respetar_robots=False) as c:
        assert (await c.obtener("https://a.mx/x")).text == "por fin"
    assert len(s.peticiones) == 3


async def test_se_rinde_tras_los_reintentos():
    s = Servidor({"https://a.mx/x": httpx.ConnectTimeout("lento")})
    async with cliente(s, reintentos=2, respetar_robots=False) as c:
        with pytest.raises(ErrorRed, match="3 intento"):
            await c.obtener("https://a.mx/x")
    # un 404 no se reintenta: se devuelve
    s404 = Servidor({})
    async with cliente(s404, reintentos=2, respetar_robots=False) as c:
        assert (await c.obtener("https://a.mx/nada")).status_code == 404
    assert len(s404.peticiones) == 1


async def test_ritmo_por_dominio():
    s = Servidor({f"https://{h}.mx/{i}": httpx.Response(200) for h in "ab" for i in range(3)})
    ajustes = AjustesRed(user_agent=UA, peticiones_por_segundo_por_dominio=20, respetar_robots=False)
    async with Cliente(ajustes, transporte=httpx.MockTransport(s)) as c:
        inicio = time.monotonic()
        await asyncio.gather(*(c.obtener(f"https://a.mx/{i}") for i in range(3)))
        mismo_sitio = time.monotonic() - inicio

        inicio = time.monotonic()
        await asyncio.gather(c.obtener("https://b.mx/0"), c.obtener("https://b.mx/1"))
        assert mismo_sitio >= 0.09  # 3 peticiones a 20/s: al menos 2 intervalos de 0.05 s


async def test_crawl_delay_del_sitio():
    s = Servidor(
        {
            "https://a.mx/robots.txt": httpx.Response(200, text="User-agent: *\nCrawl-delay: 0.2"),
            "https://a.mx/1": httpx.Response(200),
            "https://a.mx/2": httpx.Response(200),
        }
    )
    async with cliente(s) as c:
        await c.obtener("https://a.mx/1")
        inicio = time.monotonic()
        await c.obtener("https://a.mx/2")
        assert time.monotonic() - inicio >= 0.15


async def test_redireccion_revisa_robots_del_destino():
    s = Servidor(
        {
            "https://a.mx/doc": httpx.Response(302, headers={"Location": "https://b.mx/privado/doc.pdf"}),
            "https://b.mx/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /privado"),
        }
    )
    async with cliente(s) as c:
        with pytest.raises(BloqueadoPorRobots):
            await c.obtener("https://a.mx/doc")


async def test_redireccion_relativa_y_url_final():
    s = Servidor(
        {
            "https://a.mx/viejo": httpx.Response(301, headers={"Location": "/nuevo"}),
            "https://a.mx/nuevo": httpx.Response(200, text="aquí"),
        }
    )
    async with cliente(s, respetar_robots=False) as c:
        r = await c.obtener("https://a.mx/viejo")
    assert r.text == "aquí" and str(r.url) == "https://a.mx/nuevo"


async def test_corta_respuestas_demasiado_grandes():
    s = Servidor(
        {
            "https://a.mx/grande": httpx.Response(200, content=b"x" * 2000),
            "https://a.mx/mentiroso": httpx.Response(200, headers={"Content-Length": "999999"}, content=b"x"),
        }
    )
    async with cliente(s, respetar_robots=False) as c:
        with pytest.raises(DemasiadoGrande):
            await c.obtener("https://a.mx/grande", max_bytes=1000)
        with pytest.raises(DemasiadoGrande):
            await c.obtener("https://a.mx/mentiroso", max_bytes=1000)
        assert len((await c.obtener("https://a.mx/grande", max_bytes=5000)).content) == 2000


async def test_certificado_invalido_reintenta_sin_verificar():
    error_tls = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    error_tls.__cause__ = ssl.SSLCertVerificationError("vencido")
    seguro = Servidor({"https://viejo.gob.mx/x": error_tls})
    inseguro = Servidor({"https://viejo.gob.mx/x": httpx.Response(200, text="ok")})
    async with cliente(seguro, sin_tls=inseguro, respetar_robots=False) as c:
        assert (await c.obtener("https://viejo.gob.mx/x")).text == "ok"
        assert c.hosts_sin_tls == {"viejo.gob.mx"}
        await c.obtener("https://viejo.gob.mx/x")  # la segunda va directo sin verificar
    assert len(seguro.peticiones) == 1 and len(inseguro.peticiones) == 2

    seguro = Servidor({"https://viejo.gob.mx/x": error_tls})
    async with cliente(seguro, sin_tls=inseguro, respetar_robots=False, reintentar_sin_tls=False, reintentos=0) as c:
        with pytest.raises(ErrorRed):
            await c.obtener("https://viejo.gob.mx/x")


async def test_contenido_comprimido():
    s = Servidor(
        {
            "https://a.mx/gz": httpx.Response(
                200, headers={"Content-Encoding": "gzip"}, content=gzip.compress("¡hola!".encode())
            ),
        }
    )
    async with cliente(s, respetar_robots=False) as c:
        r = await c.obtener("https://a.mx/gz")
    assert r.text == "¡hola!"
    assert "content-encoding" not in r.headers


async def test_head():
    s = Servidor({"https://a.mx/x.pdf": httpx.Response(200, headers={"Content-Type": "application/pdf"})})
    async with cliente(s, respetar_robots=False) as c:
        r = await c.cabeza("https://a.mx/x.pdf")
    assert r.headers["content-type"] == "application/pdf"
    assert s.peticiones[0].method == "HEAD"


async def test_descargar_a_sumidero(tmp_path):
    from docubot.documentos.almacen import Almacen

    s = Servidor(
        {
            "https://a.mx/doc": httpx.Response(302, headers={"Location": "/doc.pdf"}),
            "https://a.mx/doc.pdf": httpx.Response(200, content=b"%PDF-1.4 datos %%EOF"),
            "https://a.mx/falta.pdf": httpx.Response(404, text="no hay"),
        }
    )
    almacen = Almacen(tmp_path)
    async with cliente(s, respetar_robots=False) as c:
        t = almacen.temporal()
        r = await c.descargar("https://a.mx/doc", t, max_bytes=1000)
        t.cerrar()
        assert r.status_code == 200 and str(r.url) == "https://a.mx/doc.pdf"
        assert t.ruta.read_bytes() == b"%PDF-1.4 datos %%EOF" and t.bytes == 20
        assert t.inicio.startswith(b"%PDF") and t.final.endswith(b"%%EOF")

        t2 = almacen.temporal()
        r = await c.descargar("https://a.mx/falta.pdf", t2, max_bytes=1000)
        t2.cerrar()
        assert r.status_code == 404 and t2.bytes == 0  # lo que no es 2xx no se escribe


async def test_dominio_inexistente_no_se_reintenta():
    import socket

    error = httpx.ConnectError("[Errno -2] Name or service not known")
    error.__cause__ = socket.gaierror(-2, "Name or service not known")
    s = Servidor({"https://muerto.gob.mx/x": error})
    async with cliente(s, reintentos=3, respetar_robots=False) as c:
        with pytest.raises(SinDNS, match="muerto.gob.mx no existe"):
            await c.obtener("https://muerto.gob.mx/x")
    assert len(s.peticiones) == 1
