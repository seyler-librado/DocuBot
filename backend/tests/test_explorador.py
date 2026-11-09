"""El explorador contra un sitio simulado completo."""

import httpx
from simulado import Servidor, html, pdf

from docubot.ajustes import AjustesRed
from docubot.descubrimiento.explorador import Explorador
from docubot.perfiles.esquema import Perfil
from docubot.red.cliente import Cliente

M = "https://muni.gob.mx"

PERFIL = Perfil.model_validate(
    {
        "nombre": "prueba",
        "descubrimiento": {
            "fuentes": [{"tipo": "semillas", "urls": [f"{M}/"]}],
            "exploracion": {"profundidad": 2, "max_paginas": 20, "secciones_prioritarias": ["transparencia"]},
        },
        "documentos": {
            "tipos": {
                "PLAN": {"nombre": "Plan", "palabras": ["plan"]},
                "REGLAMENTO": {"nombre": "Reglamento", "patrones": ["reglamento"]},
            }
        },
    }
)


def cliente(servidor: Servidor) -> Cliente:
    ajustes = AjustesRed(user_agent="DocuBot/test", peticiones_por_segundo_por_dominio=1000, reintentos=0)
    return Cliente(ajustes, transporte=httpx.MockTransport(servidor), espera_base=0.01)


def sitio_completo() -> Servidor:
    return Servidor(
        {
            f"{M}/robots.txt": httpx.Response(200, text=f"User-agent: *\nDisallow: /privado\nSitemap: {M}/mapa.xml"),
            f"{M}/": html(
                ("/transparencia", "Transparencia"),
                ("/noticias/1", "Noticia"),
                ("/docs/Plan_Municipal_2024.pdf", "Plan municipal"),
                ("https://drive.google.com/file/d/ABC/view", "Plan de desarrollo (Drive)"),
                ("https://drive.google.com/file/d/ZZZ/view", "Fotos del evento"),
                ("https://www.facebook.com/muni", "Facebook"),
                ("mailto:a@muni.gob.mx", "correo"),
                ("/descargar.php?id=7", "Reglamento de construcción"),
                ("/ver?doc=9", "Programa"),
                ("/privado/x", "Privado"),
                ("https://otro.gob.mx/pagina", "Otro sitio"),
            ),
            f"{M}/transparencia": html(("/transparencia/planes", "Planes"), ("atlas.pdf", "Atlas")),
            f"{M}/transparencia/planes": html(("/muy/hondo", "Más"), ("/docs/hondo.pdf", "Plan hondo")),
            f"{M}/noticias/1": html(),
            f"{M}/descargar.php": httpx.Response(200, headers={"Content-Type": "application/pdf"}),
            f"{M}/ver": pdf(),
            f"{M}/mapa.xml": httpx.Response(
                200,
                headers={"Content-Type": "application/xml"},
                text=f"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>{M}/sitemap-doc.pdf</loc></url><url><loc>{M}/pagina-sitemap</loc></url></urlset>""",
            ),
            f"{M}/pagina-sitemap": html(("/otro.pdf", "Otro")),
        }
    )


async def test_explora_sitio_completo():
    s = sitio_completo()
    async with cliente(s) as c:
        r = await Explorador(c, PERFIL).explorar("muni.gob.mx")
    docs = {d.url: d for d in r.documentos}

    assert r.estado == "explorado" and r.url_final == f"{M}/"
    assert set(docs) == {
        f"{M}/docs/Plan_Municipal_2024.pdf",
        "https://drive.google.com/uc?export=download&id=ABC",
        f"{M}/descargar.php?id=7",
        f"{M}/ver?doc=9",
        f"{M}/atlas.pdf",  # relativo a /transparencia, que no lleva barra final
        f"{M}/docs/hondo.pdf",
        f"{M}/sitemap-doc.pdf",
        f"{M}/otro.pdf",
    }
    assert docs[f"{M}/descargar.php?id=7"].verificado == "head"
    assert docs[f"{M}/ver?doc=9"].verificado == "get"
    assert docs[f"{M}/sitemap-doc.pdf"].verificado == "sitemap"
    assert docs["https://drive.google.com/uc?export=download&id=ABC"].externo
    assert docs[f"{M}/docs/hondo.pdf"].pagina_origen == f"{M}/transparencia/planes"
    assert docs[f"{M}/docs/Plan_Municipal_2024.pdf"].ancla == "Plan municipal"

    pedidas = s.urls()
    assert f"{M}/muy/hondo" not in pedidas  # más allá de la profundidad
    assert f"{M}/privado/x" not in pedidas  # robots.txt
    assert not any("facebook" in u or "otro.gob.mx" in u or "drive.google" in u for u in pedidas)
    assert r.urls_sitemap == 2 and r.heads == 1
    # la sección prioritaria se visita antes que las noticias
    assert pedidas.index(f"{M}/transparencia") < pedidas.index(f"{M}/noticias/1")


async def test_semillas_sin_portada():
    s = Servidor(
        {
            "https://m2.gob.mx/docs/lista": html(("a.pdf", "Plan A")),
            "https://m2.gob.mx/b.pdf": pdf(),
        }
    )
    async with cliente(s) as c:
        r = await Explorador(c, PERFIL).explorar(
            "m2.gob.mx", ["https://m2.gob.mx/docs/lista", "https://m2.gob.mx/b.pdf"]
        )
    assert r.estado == "explorado"
    assert {d.url for d in r.documentos} == {"https://m2.gob.mx/docs/a.pdf", "https://m2.gob.mx/b.pdf"}


async def test_sitios_problematicos():
    casos = {
        "redes.gob.mx": (
            {"https://redes.gob.mx/": httpx.Response(301, headers={"Location": "https://www.facebook.com/x"})},
            "redes_sociales",
        ),
        "caido.gob.mx": ({"https://caido.gob.mx/": httpx.ConnectError("no")}, "sin_respuesta"),
        "venta.gob.mx": ({"https://venta.gob.mx/": html(extra="<h1>This domain is for sale</h1>")}, "estacionado"),
        "cerrado.gob.mx": (
            {"https://cerrado.gob.mx/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /")},
            "bloqueado",
        ),
    }
    for dominio, (rutas, esperado) in casos.items():
        async with cliente(Servidor(rutas)) as c:
            r = await Explorador(c, PERFIL).explorar(dominio)
        assert r.estado == esperado, dominio


async def test_respeta_maximo_de_paginas():
    rutas = {f"{M}/": html(*[(f"/p{i}", f"página {i}") for i in range(30)])}
    rutas |= {f"{M}/p{i}": html((f"/d{i}.pdf", "plan")) for i in range(30)}
    perfil = PERFIL.model_copy(deep=True)
    perfil.descubrimiento.exploracion.max_paginas = 5
    perfil.descubrimiento.exploracion.sitemap = False
    s = Servidor(rutas)
    async with cliente(s) as c:
        r = await Explorador(c, perfil).explorar("muni.gob.mx")
    assert r.paginas == 5 and len(r.documentos) == 4
